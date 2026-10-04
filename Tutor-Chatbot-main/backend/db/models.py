"""ORM 模型（T3 四张核心表 + T5 画像两张表）。

字段严格按 DEVELOPMENT.md 第 6 节与 DEVELOPMENT_PLAN T3.2–T3.5 定义。

一处主动设计：`Message.user_id` 允许为空。
因为 assistant 的回复不属于任何用户，强行造一个「AI 用户」反而会污染
User 表和角色语义。

T5 的两张表都挂在「学生 × 课堂」上而不是只挂学生：
本系统是一个教室 + 一个学科，同一个人在不同课堂里的掌握程度不该互相污染。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


class User(Base):
    """用户：学生或教师。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="student")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    memberships: Mapped[list["ClassroomMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.id} {self.username} ({self.role})>"


class Classroom(Base):
    """课堂：一个教室 + 一个学科。"""

    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(64), nullable=False, default="cs")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    members: Mapped[list["ClassroomMember"]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Classroom {self.id} {self.name} ({self.subject})>"


class ClassroomMember(Base):
    """课堂成员：谁在哪个课堂里，以什么身份。"""

    __tablename__ = "classroom_members"
    __table_args__ = (
        UniqueConstraint("classroom_id", "user_id", name="uq_classroom_user"),
        Index("idx_member_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="student")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    classroom: Mapped["Classroom"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        return f"<ClassroomMember classroom={self.classroom_id} user={self.user_id}>"


class Message(Base):
    """聊天记录。

    role: student / assistant / teacher
    user_id: assistant 消息为 NULL
    """

    __tablename__ = "messages"
    __table_args__ = (Index("idx_message_classroom", "classroom_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # T4：教学状态随消息落库。原来 topic / hint_level 只在客户端内存中，
    # 刷新页面就归零、多轮递进断掉。现在每次回答把当时的知识点与讲解深度
    # 一并写进来，下次请求从最后一条消息恢复——服务端成为状态的唯一真相源。
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hint_level: Mapped[int] = mapped_column(nullable=False, default=0)

    classroom: Mapped["Classroom"] = relationship(back_populates="messages")
    user: Mapped["User | None"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} classroom={self.classroom_id} role={self.role}>"


class StudentProfile(Base):
    """学生画像（T5）：一个人在某个课堂里学到哪了、卡在哪了。

    不是手工填的表，而是每轮对话自动沉淀出来的：
    - knowledge_mastery：知识点 -> 0~1 掌握度，答对往上走、讲透还没懂往下走
    - weak_points：模型抓到的具体误解，一句话一条
    - overall_level：由掌握度均值推导，不让学生自己填
    - learning_preference：由学习行为统计推导

    PUT 接口允许老师/学生手工修正，但下一次对话又会按新证据继续更新。
    """

    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "classroom_id", name="uq_profile_user_classroom"),
        Index("idx_profile_classroom", "classroom_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    overall_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="beginner"
    )
    learning_preference: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    # {"死锁": 0.3, "TCP 三次握手": 0.8}
    knowledge_mastery: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    # ["把死锁理解成进程死循环", "以为 TCP 握手是为了协商端口"]
    weak_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship()
    classroom: Mapped["Classroom"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<StudentProfile user={self.user_id} "
            f"classroom={self.classroom_id} level={self.overall_level}>"
        )


class LearningBehavior(Base):
    """学习行为流水（T5.3）：ask_question / repeat_question / request_explanation。

    画像里的 learning_preference 就是从这张表统计出来的——
    只留结论会丢掉推导依据，留着流水才能回头解释「为什么判定他是 beginner」。
    """

    __tablename__ = "learning_behaviors"
    __table_args__ = (
        Index("idx_behavior_user_topic", "user_id", "topic"),
        Index("idx_behavior_classroom", "classroom_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    hint_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship()
    classroom: Mapped["Classroom"] = relationship()

    def __repr__(self) -> str:
        return f"<LearningBehavior user={self.user_id} {self.action} {self.topic}>"
