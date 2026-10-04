import asyncio
from dataclasses import dataclass
import json
import os
from functools import lru_cache
from pathlib import Path
import tempfile
import time
from typing import List
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent.graph import assessment_graph, get_llm, get_model
from agent.rag.indexer import build_index, load_knowledge_index
from agent.rag.retriever import get_knowledge_context, get_relevant_context
from agent.state import ChatRequest, HistoryMessage, HINT_STRATEGIES, TutorState

load_dotenv()

MAX_UPLOAD_BYTES = max(
    1,
    int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
)
MAX_DOCUMENT_SESSIONS = max(1, int(os.getenv("MAX_DOCUMENT_SESSIONS", "100")))
SESSION_TTL_SECONDS = max(1, int(os.getenv("SESSION_TTL_SECONDS", "3600")))

# 常驻八股知识库：构建一次落盘，之后所有请求共享
KNOWLEDGE_PERSIST_DIR = os.getenv(
    "KNOWLEDGE_PERSIST_DIR",
    str(Path(__file__).resolve().parent / "chroma_kb"),
)
KNOWLEDGE_COLLECTION = os.getenv("KNOWLEDGE_COLLECTION", "cs_basics")


@lru_cache(maxsize=1)
def get_knowledge_store():
    """返回常驻知识库；还没构建过时返回 None，检索函数会兜底返回空串。"""
    return load_knowledge_index(KNOWLEDGE_COLLECTION, KNOWLEDGE_PERSIST_DIR)

RAG_GROUNDING_RULES = """知识库资料使用要求：
- 涉及资料内容的结论，优先依据下面提供的资料片段回答。
- 资料没覆盖的部分，可以用你自己的知识补充，但要说清这是补充内容。
- 不要编造资料中不存在的来源、页码、链接或原文。
- 如果资料与常识冲突，以资料为准，并指出这个差异。"""

limiter = Limiter(key_func=get_remote_address)


@dataclass
class DocumentSession:
    vectorstore: object
    created_at: float


app = FastAPI(title="CS Tutor Agent")
sessions: dict[str, DocumentSession] = {}
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = json.loads(
    os.getenv("ALLOWED_ORIGINS", '["http://localhost:3000"]')
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _delete_vectorstore(vectorstore: object) -> None:
    try:
        vectorstore.delete_collection()
    except Exception:
        # Session cleanup should not make an otherwise successful request fail.
        pass


def cleanup_expired_sessions(now: float | None = None) -> None:
    cutoff = (now if now is not None else time.monotonic()) - SESSION_TTL_SECONDS
    expired_ids = [
        session_id
        for session_id, session in sessions.items()
        if session.created_at <= cutoff
    ]
    for session_id in expired_ids:
        session = sessions.pop(session_id, None)
        if session is not None:
            _delete_vectorstore(session.vectorstore)


def evict_oldest_session_if_full() -> None:
    if len(sessions) < MAX_DOCUMENT_SESSIONS:
        return
    oldest_id = min(sessions, key=lambda key: sessions[key].created_at)
    session = sessions.pop(oldest_id)
    _delete_vectorstore(session.vectorstore)


def deserialize_history(
    history: List[HistoryMessage | dict],
) -> List[BaseMessage]:
    messages = []
    for item in history:
        if isinstance(item, HistoryMessage):
            role = item.role
            content = item.content
        else:
            role = item.get("role")
            content = item.get("content", "")

        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def add_rag_grounding(prompt: str, rag_context: str) -> str:
    if not rag_context:
        return prompt
    return (
        f"{prompt}\n\n"
        f"{RAG_GROUNDING_RULES}\n\n"
        "知识库资料：\n"
        f"{rag_context}"
    )


@app.post("/chat")
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    try:
        llm = get_llm(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await asyncio.to_thread(cleanup_expired_sessions)

    history = deserialize_history(body.history)
    new_message = HumanMessage(content=body.message)

    initial_state: TutorState = {
        "messages": history + [new_message],
        "topic": body.topic,
        "hint_level": body.hint_level,
        "misconception": body.misconception,
        "resolved": body.resolved,
        "llm": llm,
        "topic_changed": False,
    }

    try:
        assessment_state = await assessment_graph.ainvoke(initial_state)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The configured language model could not assess the message.",
        ) from exc

    # 两套检索来源：① 学生本次上传的 PDF（会话级、内存、一小时过期）
    #              ② 常驻八股知识库（跨请求共享、落盘）
    session = sessions.get(body.session_id) if body.session_id else None
    doc_context = (
        await asyncio.to_thread(
            get_relevant_context,
            session.vectorstore,
            body.message,
        )
        if session is not None
        else ""
    )
    kb_context = await asyncio.to_thread(
        get_knowledge_context,
        get_knowledge_store(),
        body.message,
    )
    rag_context = "\n\n---\n\n".join(x for x in (doc_context, kb_context) if x)

    if assessment_state["topic"] == "unknown":
        # 纯寒暄不该拿知识库去回答，只有学生上传过文档时才依据文档答
        if doc_context:

            async def doc_stream():
                try:
                    prompt = add_rag_grounding(
                        (
                            "你是计算机八股辅导助手。依据下面给出的知识库资料，"
                            "简洁、准确地回答学生的问题。\n\n"
                            f"学生提问：\n{body.message}"
                        ),
                        rag_context,
                    )

                    async for chunk in llm.astream([HumanMessage(content=prompt)]):
                        token = chunk.content
                        if token:
                            yield (
                                "data: "
                                f"{json.dumps({'type': 'token', 'content': token})}\n\n"
                            )
                    yield (
                        "data: "
                        f"{json.dumps({'type': 'state', 'topic': '', 'hint_level': 0, 'misconception': '', 'resolved': False})}\n\n"
                    )
                    yield "data: [DONE]\n\n"
                except Exception:
                    yield (
                        "data: "
                        f"{json.dumps({'type': 'error', 'content': 'The language model request failed.'})}\n\n"
                    )

            return StreamingResponse(doc_stream(), media_type="text/event-stream")

        async def unknown_stream():
            try:
                prompt = (
                    "你是计算机八股（面试知识点）辅导助手。学生还没说想学什么。"
                    "用中文简短打个招呼，并请他告诉你想了解哪个计算机知识点，"
                    "例如进程与线程、TCP 三次握手、MySQL 索引、垃圾回收等。"
                )
                async for chunk in llm.astream([HumanMessage(content=prompt)]):
                    token = chunk.content
                    if token:
                        yield (
                            "data: "
                            f"{json.dumps({'type': 'token', 'content': token})}\n\n"
                        )
                yield (
                    "data: "
                    f"{json.dumps({'type': 'state', 'topic': '', 'hint_level': 0, 'misconception': '', 'resolved': False})}\n\n"
                )
                yield "data: [DONE]\n\n"
            except Exception:
                yield (
                    "data: "
                    f"{json.dumps({'type': 'error', 'content': 'The language model request failed.'})}\n\n"
                )

        return StreamingResponse(unknown_stream(), media_type="text/event-stream")

    async def event_stream():
        try:
            strategy = HINT_STRATEGIES[assessment_state["hint_level"]]
            misconception_note = (
                "学生目前的具体理解偏差是："
                f"{assessment_state['misconception']}"
                "。讲解时优先纠正这一点。"
                if assessment_state["misconception"]
                else "目前还不知道学生的具体理解偏差，按常规讲法讲解。"
            )

            if assessment_state["resolved"]:
                system_content = (
                    "你是计算机八股（面试知识点）辅导助手。学生刚刚掌握了："
                    f"{assessment_state['topic']}\n"
                    "用中文给一句简短的肯定（1-2 句），点出这个知识点面试时"
                    "最值得记住的那一句话，然后问他要不要继续下一个知识点。"
                )
            else:
                system_content = f"""你是计算机八股（面试知识点）辅导助手，当前正在讲解：{assessment_state['topic']}

当前讲解深度要求：{strategy}

{misconception_note}

规则：
- 全程用中文回答，面向正在准备面试的学生。
- 可以直接给出答案，不需要反问、不需要启发式铺垫。
- 语言精炼，去掉寒暄和废话；能用分点就用分点。
- 涉及术语、定义、流程时，优先使用业界公认的标准说法。
- 讲解结束后，最多追问一句，确认学生是否理解。"""

            system_content = add_rag_grounding(system_content, rag_context)

            if body.provider == "gemini":
                messages = assessment_state["messages"]
                last_msg = messages[-1]
                messages = messages[:-1] + [
                    HumanMessage(
                        content=(
                            system_content
                            + "\n\nStudent message: "
                            + last_msg.content
                        )
                    )
                ]
            else:
                messages = [
                    SystemMessage(content=system_content),
                    *assessment_state["messages"],
                ]

            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    yield (
                        "data: "
                        f"{json.dumps({'type': 'token', 'content': token})}\n\n"
                    )

            yield (
                "data: "
                f"{json.dumps({'type': 'state', 'topic': assessment_state['topic'], 'hint_level': assessment_state['hint_level'], 'misconception': assessment_state['misconception'], 'resolved': assessment_state['resolved']})}\n\n"
            )
            yield "data: [DONE]\n\n"
        except Exception:
            yield (
                "data: "
                f"{json.dumps({'type': 'error', 'content': 'The tutor could not complete this response.'})}\n\n"
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
def health():
    provider = os.getenv("LLM_PROVIDER", "groq")
    return {
        "status": "ok",
        "provider": provider,
        "model": get_model(provider),
    }


@app.post("/upload")
@limiter.limit("3/hour")
async def upload_document(request: Request, file: UploadFile = File(...)):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    tmp_file_path = ""
    session_id = str(uuid.uuid4())
    collection_name = f"student_upload_{session_id.replace('-', '_')}"

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file_path = tmp_file.name
            total_bytes = 0
            header = b""

            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "PDF must be no larger than "
                            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                        ),
                    )
                if len(header) < 1024:
                    header += chunk[: 1024 - len(header)]
                tmp_file.write(chunk)

        if b"%PDF-" not in header:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid PDF.",
            )

        try:
            vectorstore = await asyncio.to_thread(
                build_index,
                tmp_file_path,
                collection_name,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail="The PDF could not be read or indexed.",
            ) from exc
    finally:
        await file.close()
        if tmp_file_path:
            try:
                os.unlink(tmp_file_path)
            except FileNotFoundError:
                pass

    await asyncio.to_thread(cleanup_expired_sessions)
    await asyncio.to_thread(evict_oldest_session_if_full)
    sessions[session_id] = DocumentSession(
        vectorstore=vectorstore,
        created_at=time.monotonic(),
    )

    return {
        "session_id": session_id,
        "message": "Document indexed successfully.",
    }


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_document_session(session_id: str) -> Response:
    session = sessions.pop(session_id, None)
    if session is not None:
        await asyncio.to_thread(_delete_vectorstore, session.vectorstore)
    return Response(status_code=204)
