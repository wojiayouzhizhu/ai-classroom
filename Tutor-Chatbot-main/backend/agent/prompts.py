"""AI Classroom 使用的提示词模板。

只保留真正被 agent/graph.py 引用的两个模板；
回答阶段的策略表在 agent/state.py 的 HINT_STRATEGIES，
提示拼装在 app.py（历史原因：RESPOND/CONGRATS 在 app.py 内联拼接）。
"""


EXTRACT_TOPIC_PROMPT = """你是计算机八股（面试知识点）辅导助手。从用户消息中抽取他正在问的知识点名称。

当前知识点：{current_topic}

示例：
    - "讲讲进程和线程的区别" -> "进程与线程的区别"
    - "什么是死锁？" -> "死锁"
    - "TCP 三次握手到底在握什么" -> "TCP 三次握手"
    - "MySQL 索引为什么会失效" -> "MySQL 索引失效"
    - "你好呀" -> "unknown"
    - "我想学操作系统" -> "操作系统"

规则：
- 只要消息涉及任何计算机 / 编程 / 面试知识点，就返回该知识点名称（用中文，简短）。
- 如果这条消息是对当前知识点的追问、回答、补充或确认，只返回 "same"。
- 只有当消息纯属寒暄、完全没有任何技术内容时，才返回 "unknown"。
- 不要返回 "unknown" 之外 / "same" 之外的解释文字，也不要加标点、引号或 markdown。

用户消息：{latest_message}"""


ASSESS_UNDERSTANDING_PROMPT = """你在评估一名正在准备面试的学生对知识点「{topic}」的掌握情况。

对话记录：
{history_text}

当前讲解深度：{hint_level}（0=一句话结论, 1=面试标准答案, 2=原理展开, 3=举例+追问）

只返回 JSON，且必须包含这三个字段：
{{
  "resolved": true/false,
  "hint_level": 0-3,
  "misconception": "..."
}}

规则：
- 重要：根据完整对话从零重新评估，不要假定学生此前的错误理解仍然存在。
- 学生能复述出该知识点的关键结论，或说对了要点，就可以判定 resolved=true。
- 学生连续两轮表示"不知道""没听过"，立刻提高 hint_level。
- 上一轮讲解后学生仍然明显没懂，提高 hint_level。
- 当前问题没解决之前，不要降低 hint_level。
- resolved=true 时，hint_level 设为 0、misconception 设为空字符串，让下一个知识点重新开始。
- misconception 用中文一句话概括学生具体哪里理解错了；学生没有明显错误时填空字符串。
- 只返回 JSON 对象，不要任何其他文字。"""
