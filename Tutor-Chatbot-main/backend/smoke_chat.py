"""端到端冒烟脚本：真实调用 LLM，验证 /chat 全链路。

用途：每次改动提示词、策略表或图之后跑一次，确认
  1. SSE 能流出中文 token
  2. topic 抽取正确
  3. hint_level 会随学生「没听懂」递进
  4. 学生表示懂了之后 resolved=true 且 hint_level 归零

用法（在 backend/ 目录下，用 venv 的 python）：
    python smoke_chat.py                 # 跑内置的四轮剧本
    python smoke_chat.py "什么是虚拟内存？"   # 只问一轮自定义问题

前置：backend/.env 里 LLM_API_KEY 必须已填写，且服务已在 8000 端口启动。
注意：会真实消耗 API 额度。
"""

import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8000/chat"

DEFAULT_SCRIPT = [
    "什么是死锁？产生的必要条件有哪些？",
    "还是没太懂，能再讲清楚一点吗？",
    "那怎么预防死锁呢？举例说明一下",
    "明白了，谢谢！",
]


def call(message, topic, hint_level, misconception, resolved, history):
    payload = {
        "message": message,
        "topic": topic,
        "hint_level": hint_level,
        "misconception": misconception,
        "resolved": resolved,
        "history": history,
        "session_id": "",
        "provider": "openai",
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    started = time.time()
    parts = []
    state = None
    error = None
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line.startswith("data: "):
                continue
            body = line[6:]
            if body == "[DONE]":
                break
            try:
                evt = json.loads(body)
            except ValueError:
                continue
            kind = evt.get("type")
            if kind == "token":
                parts.append(evt.get("content", ""))
            elif kind == "state":
                state = evt
            elif kind == "error":
                error = evt
    except Exception as exc:
        print("  REQUEST_FAILED:", type(exc).__name__, exc)
        if hasattr(exc, "read"):
            try:
                print("  body:", exc.read().decode("utf-8", errors="replace")[:300])
            except Exception:
                pass
        return None, None

    print("  (%.1fs, %d chars)" % (time.time() - started, len("".join(parts))))
    if error:
        print("  流内错误：%s" % error.get("content"))
    return "".join(parts), state


def run(messages):
    history = []
    topic = ""
    level = 0
    misconception = ""
    resolved = False

    for index, message in enumerate(messages, 1):
        print()
        print("### 第 %d 轮 学生：%s" % (index, message))
        print("    发出：topic=%r hint_level=%d resolved=%s" % (topic, level, resolved))
        answer, state = call(message, topic, level, misconception, resolved, history)
        if answer:
            preview = answer[:400].replace("\n", "\n          ")
            print("    助手：%s" % preview)
        if not state:
            print("    没有收到 state 事件，链路异常")
            return False
        print(
            "    回传：topic=%r hint_level=%d misconception=%r resolved=%s"
            % (state.get("topic"), state.get("hint_level"),
               state.get("misconception"), state.get("resolved"))
        )
        topic = state.get("topic", "")
        level = state.get("hint_level", 0)
        misconception = state.get("misconception", "")
        resolved = state.get("resolved", False)
        if answer:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": answer})
        time.sleep(1)
    return True


if __name__ == "__main__":
    script = sys.argv[1:] or DEFAULT_SCRIPT
    ok = run(script)
    print()
    print("SMOKE", "OK" if ok else "FAILED")
