"""数据访问函数（T3）。

把 SQL 细节收在这里，`app.py` 只调用语义化函数，不直接写查询。
所有函数都接受 `db=None`——数据库没配时静默跳过，不阻断对话。
"""

from __future__ import annotations

from typing import List, Sequence

from sqlalchemy import select

from agent.state import HistoryMessage
from db.models import Classroom, ClassroomMember, Message, User


def create_user(db, username: str, role: str = "student") -> User | None:
    if db is None:
        return None
    existing = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(username=username, role=role)
    db.add(user)
    db.flush()
    return user


def create_classroom(
    db, name: str, subject: str = "cs", description: str | None = None
) -> Classroom | None:
    if db is None:
        return None
    room = Classroom(name=name, subject=subject, description=description)
    db.add(room)
    db.flush()
    return room


def add_member(db, classroom_id: int, user_id: int, role: str) -> ClassroomMember | None:
    if db is None:
        return None
    existing = db.execute(
        select(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    member = ClassroomMember(classroom_id=classroom_id, user_id=user_id, role=role)
    db.add(member)
    db.flush()
    return member


def save_message(
    db, classroom_id: int, user_id: int | None, role: str, content: str
) -> Message | None:
    """落一条消息。assistant 的回复 user_id 为 None。"""
    if db is None or not content:
        return None
    message = Message(
        classroom_id=classroom_id,
        user_id=user_id,
        role=role,
        content=content,
    )
    db.add(message)
    db.flush()
    return message


def load_history(
    db, classroom_id: int, limit: int = 20
) -> List[HistoryMessage]:
    """从数据库读回最近的对话，转成 LangChain 能吃的 history。

    取最近 N 条后按 id 升序排列——先取末尾再反转，避免把最老的消息
    截掉（直接 order_by(id).limit(n) 拿到的是最早的 n 条）。
    """
    if db is None:
        return []
    rows = (
        db.execute(
            select(Message)
            .where(Message.classroom_id == classroom_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    ordered: Sequence[Message] = list(reversed(rows))
    return [
        HistoryMessage(
            role="user" if m.role in ("student", "teacher") else "assistant",
            content=m.content,
        )
        for m in ordered
    ]


def list_messages(db, classroom_id: int, limit: int = 100) -> List[Message]:
    if db is None:
        return []
    return list(
        db.execute(
            select(Message)
            .where(Message.classroom_id == classroom_id)
            .order_by(Message.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
