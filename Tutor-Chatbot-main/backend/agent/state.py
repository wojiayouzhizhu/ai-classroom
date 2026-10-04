from langchain_core.messages import BaseMessage

from typing import Annotated, Any, List, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


HINT_STRATEGIES = {
    0:"Use a real-world analogy to explain the concept. Then ask a broad open question to probe understanding. Do NOT give the answer.",
    1:"Give a narrower hint that points directly at the gap in their understanding. Ask a more specific follow-up question. Do NOT give the answer.",
    2:"Ask a leading question that almost gives the answer away. The user should be able to complete the thought themselves. Do NOT give the answer.",
    3:"The user has struggled enough. Clearly reveal and explain the answer. Then summarize the key insight they should take away.",
}

# This is the state schema for our tutor agent. It includes the conversation history (messages), the current topic being discussed, the hint level (which determines the strategy for the next hint), any specific misconception identified, and whether the student's confusion has been resolved. The messages field is annotated with add_messages to allow the graph to automatically append new messages to the history as we generate responses.
class TutorState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    topic: str
    hint_level: int
    misconception: str
    resolved: bool
    llm: Any
    topic_changed: NotRequired[bool]


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=1000)
    topic: str = Field(default="", max_length=100)
    hint_level: int = Field(default=0, ge=0, le=3)
    misconception: str = Field(default="", max_length=500)
    resolved: bool = False
    history: List[HistoryMessage] = Field(default_factory=list, max_length=50)
    session_id: str = Field(default="", max_length=36)
    provider: Literal["ollama", "groq", "gemini", "openai"] = "openai"
