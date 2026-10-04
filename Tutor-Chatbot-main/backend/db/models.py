"""ORM 模型（T3 四张核心表）。

字段严格按 DEVELOPMENT.md 第 6 节与 DEVELOPMENT_PLAN T3.2–T3.5 定义，
不提前加 StudentProfile / LearningRecord —— 那些是 T5/T6 的事。

一处主动设计：`Message.user_id` 允许为空。
因为 assistant 的回复不属于任何用户，强行造一个「AI 用户」反而会污染
User 表和角色语义。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
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

    classroom: Mapped["Classroom"] = relationship(back_populates="messages")
    user: Mapped["User | None"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} classroom={self.classroom_id} role={self.role}>"
