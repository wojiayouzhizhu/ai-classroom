from langchain_core.messages import BaseMessage

from typing import Annotated, Any, List, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


# 讲解深度四层：面向「计算机八股 / 面试知识点」学习场景。
# 与苏格拉底式的「启发到第几级」不同，这里每一层都允许给答案，
# 区别只在展开的程度——学生来这里是背八股的，捂着答案不给没有意义。
HINT_STRATEGIES = {
    0: "先用一句话给出结论，让学生知道这个知识点的标准答案是什么。不要展开原理，不要举例子。",
    1: "给出面试里的标准答案：条理清晰、分点列出、可以直接背诵那种。篇幅控制在 200 字以内，不要深入底层原理。",
    2: "在标准答案的基础上展开原理：讲清楚「为什么是这样」，涉及哪些底层机制、数据结构或设计取舍。允许适当加长。",
    3: "先讲透原理，再配一个具体例子 or 场景帮助理解，最后抛一个面试常见追问方向，让学生自查是否真的掌握。",
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
