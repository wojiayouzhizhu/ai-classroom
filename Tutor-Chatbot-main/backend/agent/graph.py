import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field, StrictBool, ValidationError

from .state import TutorState

from .prompts import EXTRACT_TOPIC_PROMPT, ASSESS_UNDERSTANDING_PROMPT

load_dotenv()

DEFAULT_MODELS = {
    "ollama": "llama3.2",
    "groq": "openai/gpt-oss-120b",
    "gemini": "gemini-2.5-flash-lite",
    "openai": "glm-4.7-flash",
}


def get_model(provider: str) -> str | None:
    configured_provider = os.getenv("LLM_PROVIDER")
    configured_model = os.getenv("LLM_MODEL")
    return (
        os.getenv(f"{provider.upper()}_MODEL")
        or (configured_model if configured_provider == provider else None)
        or DEFAULT_MODELS.get(provider)
    )


def get_llm(provider: str | None = None):
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "groq")

    model = get_model(provider)

    if provider == "ollama":
        return ChatOllama(model=model, temperature=0.4)
    if provider == "groq":
        from langchain_groq import ChatGroq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured. Add it to backend/.env "
                "and restart the backend."
            )
        return ChatGroq(model=model, temperature=0.4, groq_api_key=api_key)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError(
                "GOOGLE_API_KEY is not configured. Add it to backend/.env "
                "and restart the backend."
            )
        return ChatGoogleGenerativeAI(model=model, temperature=0.4)

    if provider == "openai":
        # Generic OpenAI-compatible endpoint (Zhipu GLM, SiliconFlow,
        # DashScope, DeepSeek...). Configure via LLM_API_KEY / LLM_BASE_URL.
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise ValueError(
                "LLM_API_KEY is not configured. Add it to backend/.env "
                "and restart the backend."
            )
        return ChatOpenAI(
            model=model,
            temperature=0.4,
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL") or None,
        )

    raise ValueError(f"Unknown provider: {provider}")


class AssessmentResult(BaseModel):
    resolved: StrictBool
    hint_level: int = Field(ge=0, le=3)
    misconception: str = Field(default="", max_length=500)


def parse_assessment_result(raw: str) -> AssessmentResult:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return AssessmentResult.model_validate(json.loads(cleaned))


async def extract_topic_node(state: TutorState) -> dict:
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    latest_message = user_messages[-1].content

    current_topic = state["topic"] or "unknown"
    prompt = EXTRACT_TOPIC_PROMPT.format(
        current_topic=current_topic,
        latest_message=latest_message,
    )

    response = await state["llm"].ainvoke([HumanMessage(content=prompt)])
    result = response.content.strip()
    if result.lower() == "same":
        return {}

    topic = result.lower()
    if topic in ["unknown", "none", "no topic", "not mentioned"]:
        if current_topic != "unknown":
            return {}
        return {
            "topic": "unknown",
            "hint_level": 0,
            "misconception": "",
            "resolved": False,
        }

    if topic == current_topic.lower():
        return {}

    return {
        "topic": topic,
        "hint_level": 0,
        "misconception": "",
        "resolved": False,
        "topic_changed": True,
    }


async def assess_understanding_node(state: TutorState) -> dict:
    if state.get("topic_changed", False):
        return {"hint_level": 0, "misconception": "", "resolved": False}

    if state["topic"] == "unknown":
        return {"hint_level": 0, "misconception": "", "resolved": False}

    if len(state["messages"]) < 2:
        return {"hint_level": 0, "misconception": "", "resolved": False}

    history_text = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Tutor'}: {m.content}"
        for m in state["messages"]
    )
    prompt = ASSESS_UNDERSTANDING_PROMPT.format(
        topic=state["topic"],
        history_text=history_text,
        hint_level=state["hint_level"],
    )

    response = await state["llm"].ainvoke([HumanMessage(content=prompt)])

    try:
        assessment = parse_assessment_result(response.content)

        if assessment.resolved:
            return {
                "resolved": True,
                "hint_level": 0,
                "misconception": "",
            }

        return {
            "resolved": False,
            "hint_level": max(state["hint_level"], assessment.hint_level),
            "misconception": assessment.misconception,
        }
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError):
        return {
            "resolved": False,
            "hint_level": state["hint_level"],
            "misconception": state["misconception"],
        }

def build_assessment_graph() -> StateGraph:
    workflow = StateGraph(TutorState)

    workflow.add_node("extract_topic", extract_topic_node)
    workflow.add_node("assess_understanding", assess_understanding_node)

    workflow.set_entry_point("extract_topic")
    workflow.add_edge("extract_topic", "assess_understanding")
    workflow.add_edge("assess_understanding", END)

    return workflow.compile()

assessment_graph = build_assessment_graph()
