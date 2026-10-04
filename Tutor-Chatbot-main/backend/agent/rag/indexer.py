import os
from functools import lru_cache
from pathlib import Path

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document


# 中文八股知识库必须用中文 embedding：原项目的 bge-small-en-v1.5 是英文模型，
# 对中文语义的区分能力很差，检索会召回一堆不相关的片段。
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

SUBJECT = "计算机八股"

CATEGORY_NAMES = {
    "os": "操作系统",
    "network": "计算机网络",
    "cpp": "C/C++",
    "embedded": "嵌入式",
}


@lru_cache(maxsize=1)
def get_embeddings() -> FastEmbedEmbeddings:
    return FastEmbedEmbeddings(model_name=EMBED_MODEL)


def get_markdown_splitter() -> RecursiveCharacterTextSplitter:
    """中文友好的切分：优先按 Markdown 标题切，再按段落，最后按句号。"""
    return RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        add_start_index=True,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", "；", ""],
    )


def load_markdown_documents(knowledge_dir: str) -> list[Document]:
    """递归读取目录下所有 .md，按文件生成带 metadata 的 Document。

    metadata 结构（对应 DEVELOPMENT_PLAN T2.3）：
        subject  学科，目前固定「计算机八股」
        category 分类，取自子目录名（os → 操作系统）
        topic    知识点，取自文件的一级标题
        source   相对路径，便于溯源
    """
    root = Path(knowledge_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"知识目录不存在：{knowledge_dir}")

    documents = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        relative = path.relative_to(root)
        # knowledge/cs/os/deadlock.md → category 取文件所在目录名「os」
        category_key = (
            relative.parts[-2] if len(relative.parts) >= 2 else ""
        )
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "subject": SUBJECT,
                    "category": CATEGORY_NAMES.get(category_key, category_key),
                    "topic": title or path.stem,
                    "source": str(relative).replace("\\", "/"),
                },
            )
        )
    return documents


def build_knowledge_index(
    knowledge_dir: str,
    collection_name: str = "cs_basics",
    persist_directory: str | None = None,
) -> Chroma:
    """把知识目录构建成常驻向量库。

    与 PDF 上传的会话级索引不同，这个库是跨请求复用的，
    persist_directory 给了就落盘，重启进程不用重建。
    """
    documents = load_markdown_documents(knowledge_dir)
    if not documents:
        raise ValueError(f"知识目录里没有找到 .md 文件：{knowledge_dir}")

    chunks = get_markdown_splitter().split_documents(documents)
    for chunk in chunks:
        # 让每个切片带上所属知识点，检索结果才能说清"这段讲的是哪个知识点"
        chunk.metadata.setdefault("topic", chunk.metadata.get("topic", ""))

    kwargs = {"collection_name": collection_name}
    if persist_directory:
        kwargs["persist_directory"] = persist_directory

    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        **kwargs,
    )


def load_knowledge_index(
    collection_name: str = "cs_basics",
    persist_directory: str = "",
) -> Chroma | None:
    """加载已持久化的知识库；不存在则返回 None（调用方要兜底）。"""
    if not persist_directory or not Path(persist_directory).exists():
        return None
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        persist_directory=persist_directory,
    )


def build_index(file_path: str, collection_name: str) -> Chroma:
    """Load PDF, split into chunks, embed and store in memory.

    保留原逻辑：学生上传的 PDF 仍然是会话级的、内存里的临时索引，
    与常驻知识库是两套独立的 collection。
    """

    # PDF load
    loader = PyPDFLoader(file_path)
    documents = loader.load()

    # Split to chunks

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        page_index = int(chunk.metadata.get("page", 0))
        page_text = documents[page_index].page_content
        start = int(chunk.metadata.get("start_index", 0))

        chunk.metadata.update(
            section="body",
            page_number=page_index + 1,
            line_start=page_text.count("\n", 0, start) + 1,
            line_end=page_text.count("\n", 0, start)
            + chunk.page_content.count("\n")
            + 1,
        )

    first_page = documents[0].page_content
    front_matter = Document(
        page_content=(
            "DOCUMENT FRONT MATTER: title, authors, affiliations and abstract.\n\n"
            + first_page
        ),
        metadata={
            "section": "front_matter",
            "page_number": 1,
            "line_start": 1,
            "line_end": first_page.count("\n") + 1,
        },
    )

    chunks.append(front_matter)
    # Embed and store in memory
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        collection_name=collection_name,
    )
    return vectorstore
