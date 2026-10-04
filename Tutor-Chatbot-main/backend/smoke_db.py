"""T3 持久化端到端验收：走真实 HTTP，覆盖 T3.6 五项能力 + /chat 落库 + 追问接续。

用法（需先启动后端）：
    python smoke_db.py                      # 默认问题「什么是死锁？」
    python smoke_db.py "TCP 为什么是三次握手？"

与 smoke_chat.py 的分工：
- smoke_chat.py：不带 classroom_id，验证纯对话链路（不落库）
- smoke_db.py  ：带 classroom_id，验证持久化链路（落库 + 从库里读回历史）

注意 /chat 有 10 次/分钟的限流，连续跑两次可能触发 429。
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
DEFAULT_QUESTION = "什么是死锁？"


def req(method, path, payload=None, stream=False, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        body = resp.read().decode()
        return body if stream else (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:200]}"
        )


def chat(message, classroom_id, user_id):
    """发一条消息，不传 history —— 历史必须能从数据库读回来才算真的持久化了。"""
    raw = req(
        "POST",
        "/chat",
        {
            "message": message,
            "classroom_id": classroom_id,
            "user_id": user_id,
            "history": [],
        },
        stream=True,
    )
    tokens, state = [], None
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        body = line[6:]
        if body == "[DONE]":
            break
        ev = json.loads(body)
        if ev.get("type") == "token":
            tokens.append(ev["content"])
        elif ev.get("type") == "state":
            state = ev
        elif ev.get("type") == "error":
            raise SystemExit("chat error: " + str(ev))
    return "".join(tokens), state


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    h = None
    for _ in range(25):
        try:
            h = req("GET", "/health")
            break
        except Exception:
            time.sleep(2)
    if h is None:
        raise SystemExit("后端未启动：先在 backend/ 下跑 uvicorn app:app")
    print("health:", h)
    if h.get("database") != "up":
        raise SystemExit(
            "数据库不可用（database=%s）。检查 backend/.env 的 MYSQL_* "
            "并确认 MySQL 服务已启动。" % h.get("database")
        )

    student = req("POST", "/users", {"username": "e2e_student", "role": "student"})
    teacher = req("POST", "/users", {"username": "e2e_teacher", "role": "teacher"})
    print("1. 创建用户:", student["username"], "/", teacher["username"])

    room = req(
        "POST",
        "/classrooms",
        {"name": "E2E 八股班", "subject": "cs", "description": "持久化验收"},
    )
    print("2. 创建课堂:", room)

    req(
        "POST",
        f"/classrooms/{room['id']}/members",
        {"user_id": teacher["id"], "role": "teacher"},
    )
    req(
        "POST",
        f"/classrooms/{room['id']}/members",
        {"user_id": student["id"], "role": "student"},
    )
    print("3. 加入课堂: 2 人")

    answer1, st1 = chat(question, room["id"], student["id"])
    print(f"4. 第1轮 {len(answer1)} 字, topic={st1 and st1.get('topic')}")
    print("   ", answer1[:60].replace("\n", " "))

    msgs = req("GET", f"/classrooms/{room['id']}/messages")
    print(f"5. 查询记录: {msgs['count']} 条 ->", [m["role"] for m in msgs["messages"]])
    assert msgs["count"] == 2, f"期望 2 条（提问+回答），实际 {msgs['count']}"
    assert [m["role"] for m in msgs["messages"]] == ["student", "assistant"]

    # 关键验收：追问不传 history、不传 topic，必须靠数据库里的历史接上上下文。
    answer2, st2 = chat("那怎么预防呢？", room["id"], student["id"])
    print(f"6. 第2轮（追问）{len(answer2)} 字, topic={st2 and st2.get('topic')}")
    print("   ", answer2[:60].replace("\n", " "))
    if not st2 or st2.get("topic") in (None, "", "unknown"):
        raise SystemExit(
            "追问被判成 unknown —— 说明从数据库读回的历史没有生效，"
            "检查 load_history 与 extract_topic_node 的上下文传递。"
        )

    msgs2 = req("GET", f"/classrooms/{room['id']}/messages")
    print(f"   记录累计: {msgs2['count']} 条")
    assert msgs2["count"] == 4, f"期望 4 条，实际 {msgs2['count']}"

    print("\nT3 持久化验收全部通过 ✓")


if __name__ == "__main__":
    main()
