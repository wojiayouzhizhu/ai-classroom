"""初始化数据库：建库 + 建表。

用法：
    python init_db.py

行为：
- 数据库不存在时自动创建（utf8mb4 / utf8mb4_unicode_ci）
- 已存在的表不会重复创建（create_all 是幂等的）
- 会打印每张表的结果，方便在 Navicat 里对照
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.models import (  # noqa: E402
    Classroom,
    ClassroomMember,
    LearningBehavior,
    Message,
    StudentProfile,
    User,
)
from db.session import Base, DATABASE_URL  # noqa: E402


def _server_url() -> tuple[str, str]:
    """拆出「不带库名的连接串」和「库名」，用于先建库再建表。"""
    db_name = os.getenv("MYSQL_DATABASE", "ai_classroom")
    url = DATABASE_URL
    # mysql+pymysql://user:pwd@host:port/ai_classroom?charset=utf8mb4
    #                                  ^ 到这里截断
    try:
        head, tail = url.split("?", 1)
    except ValueError:
        head, tail = url, ""
    slash = head.rfind("/")
    if slash == -1:
        raise SystemExit(f"DATABASE_URL 缺少数据库名：{url}")
    root_url = head[:slash] + "/"
    if tail:
        root_url += "?" + tail
    return root_url, db_name


def create_database_if_missing() -> None:
    root_url, db_name = _server_url()
    engine = create_engine(root_url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
        print(f"数据库 `{db_name}` 已就绪（utf8mb4）")
    except (OperationalError, ProgrammingError) as exc:
        raise SystemExit(
            f"无法创建/连接数据库 `{db_name}`：{exc}\n"
            "请检查 backend/.env 里的 MYSQL_* 配置，并确认 MySQL 服务已启动。"
        ) from exc
    finally:
        engine.dispose()


def ensure_new_columns() -> None:
    """给已存在的表补列。

    `create_all()` 只对「不存在的表」生效，表在而列缺失它不管。
    后期每次给模型加字段，都要在这里同步登记一条 ALTER，否则线上
    表结构会和代码里的模型悄悄偏离（读出来是 None，写入直接报错）。
    """
    from sqlalchemy import inspect

    from db.session import engine

    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns("messages")}

    additions = []
    if "topic" not in existing:
        additions.append("ADD COLUMN topic VARCHAR(64) NULL")
    if "hint_level" not in existing:
        additions.append("ADD COLUMN hint_level INT NOT NULL DEFAULT 0")

    if not additions:
        return
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE messages " + ", ".join(additions)))
        conn.commit()
    print("messages 表补充列：", ", ".join(additions))


def create_tables() -> None:
    from db.session import engine

    if engine is None:
        raise SystemExit("engine 未创建，请检查 backend/.env 的 MYSQL_* 配置")

    Base.metadata.create_all(engine)
    ensure_new_columns()
    print("数据表已创建：")
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(c.name for c in table.columns)
        print(f"  - {table.name}: {len(table.columns)} 列 [{cols}]")


def verify() -> None:
    """建完立刻读一遍，确认表真的落在 MySQL 里（而不是只在 SQLAlchemy 元数据里）。"""
    from db.session import engine

    with engine.connect() as conn:
        rows = conn.execute(text("SHOW TABLES")).fetchall()
    names = sorted(r[0] for r in rows)
    print("\nMySQL 中实际存在的表：", names)

    # 导入即注册：create_all 只认已经被 import 过的模型类，
    # 新增表忘了在这里登记，表就不会被建出来（代码里却能用，伪成功）。
    expected = {
        "users",
        "classrooms",
        "classroom_members",
        "messages",
        "student_profiles",
        "learning_behaviors",
    }
    missing = expected - set(names)
    if missing:
        raise SystemExit(f"以下表未创建成功：{sorted(missing)}")
    print("六张表全部就绪 ✓")


def main() -> None:
    print(f"连接串：{DATABASE_URL.replace(os.getenv('MYSQL_PASSWORD', ''), '***')}")
    create_database_if_missing()
    create_tables()
    verify()
    print("\n下一步：python seed_demo.py   # T3.6 五项验收")


if __name__ == "__main__":
    main()
