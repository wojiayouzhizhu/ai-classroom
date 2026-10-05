"""数据访问函数（T3）。

把 SQL 细节收在这里，`app.py` 只调用语义化函数，不直接写查询。
所有函数都接受 `db=None`——数据库没配时静默跳过，不阻断对话。
"""

from __future__ import annotations

from typing import List, Sequence

from sqlalchemy import or_, select, true
from sqlalchemy.orm import joinedload

from agent.state import HistoryMessage
from db.models import Classroom, ClassroomMember, Message, User


def _owned_by(user_id: int | None):
    """筛出「属于这个学生」的消息。

    user_id 为空表示不按人过滤（旧行为，前端只传 session_id 时仍是课堂粒度）。

    为什么要兼容 user_id IS NULL：T6 之前 assistant 回复不记归属，
    库里已经攒了一批 NULL 的老消息。一刀切按 user_id 精确匹配会把它们
    全部过滤掉，升级后学生的上下文凭空断掉一截。折中做法是老数据当作
    公共消息继续可见，新数据（都带 user_id）严格按学生隔离。
    """
    if user_id is None:
        return true()
    return or_(Message.user_id == user_id, Message.user_id.is_(None))


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
    db,
    classroom_id: int,
    user_id: int | None,
    role: str,
    content: str,
    topic: str | None = None,
    hint_level: int = 0,
) -> Message | None:
    """落一条消息。

    topic / hint_level 只对 assistant 消息有意义：记录「这次回答讲的是
    哪个知识点、讲到第几层」，下一次请求据此恢复状态。

    assistant 回复也要记 user_id（T6 改）：它表示「这条回复是给谁的」。
    原来一律写 None，导致同一个课堂里所有学生的对话混在一起分不开，
    状态恢复只能按课堂粒度，多人课堂必然串台。
    """
    if db is None or not content:
        return None
    message = Message(
        classroom_id=classroom_id,
        user_id=user_id,
        role=role,
        content=content,
        topic=topic,
        hint_level=hint_level,
    )
    db.add(message)
    db.flush()
    return message


def load_last_state(
    db, classroom_id: int, user_id: int | None = None
) -> tuple[str, int]:
    """取这个学生在这个课堂里最后一条「有效教学状态」。

    服务端是状态的唯一真相源：只要落了 classroom_id，就不再信客户端
    回传的 topic / hint_level，一律从这里恢复。这样刷新页面、换设备、
    甚至前端压根不传状态，多轮讲解深度都不会断。

    必须按学生隔离（T6 修）。原先只按课堂取最后一条，同一个课堂里
    A 在学死锁、B 在学 TCP，两人的状态会互相覆盖：B 提问时恢复出的是
    A 的 topic，讲解深度直接串台。表现是新学生第一次提问就拿到
    hint_level=2 的长篇大论——他其实什么都没问过。
    """
    if db is None:
        return "", 0
    row = (
        db.execute(
            select(Message)
            .where(
                Message.classroom_id == classroom_id,
                _owned_by(user_id),
                Message.topic.isnot(None),
                Message.topic != "",
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return "", 0
    return row.topic or "", row.hint_level or 0


def is_member(db, classroom_id: int, user_id: int | None) -> bool:
    """这个人是否真的在这个课堂里（T4.4：后端必须知道「谁」）。"""
    if db is None or user_id is None:
        return False
    return (
        db.execute(
            select(ClassroomMember).where(
                ClassroomMember.classroom_id == classroom_id,
                ClassroomMember.user_id == user_id,
            )
        )
        .scalars()
        .first()
        is not None
    )


def load_history(
    db, classroom_id: int, user_id: int | None = None, limit: int = 20
) -> List[HistoryMessage]:
    """从数据库读回这个学生最近的对话，转成 LangChain 能吃的 history。

    取最近 N 条后按 id 升序排列——先取末尾再反转，避免把最老的消息
    截掉（直接 order_by(id).limit(n) 拿到的是最早的 n 条）。

    同样按学生隔离（T6 修）：喂给模型的上下文里如果混着别人的问答，
    「追问」「还是不懂」这些指代就没法判断，评估节点会以为这个学生
    已经听了好几轮还没懂，一上来就把讲解深度抬上去。
    教师要看全课堂的对话请用 list_messages。
    """
    if db is None:
        return []
    rows = (
        db.execute(
            select(Message)
            .where(Message.classroom_id == classroom_id, _owned_by(user_id))
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
    """课堂全量消息（群聊视图），按 id 升序。

    预加载 user：调用方（app.py 的 api_list_messages）要用 m.user.username
    给每条消息标出发言人。不预加载的话，每条消息都会各触发一次延迟查询
    （100 条消息 = 101 次 SQL），而且在 session 关闭后再访问会直接抛
    DetachedInstanceError —— 500。
    """
    if db is None:
        return []
    return list(
        db.execute(
            select(Message)
            .where(Message.classroom_id == classroom_id)
            .options(joinedload(Message.user))
            .order_by(Message.id)
            .limit(limit)
        )
        .unique()
        .scalars()
        .all()
    )
