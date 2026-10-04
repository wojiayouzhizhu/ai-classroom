"""AI Classroom 使用的提示词模板。

- 对话链路：EXTRACT_TOPIC / ASSESS_UNDERSTANDING 被 agent/graph.py 引用
- 备课链路（T7）：PPT_OUTLINE_PROMPT 被 agent/resource_agent.py 引用
- 回答阶段的策略表在 agent/state.py 的 HINT_STRATEGIES，
  提示拼装在 app.py（历史原因：RESPOND/CONGRATS 在 app.py 内联拼接）
"""


EXTRACT_TOPIC_PROMPT = """你是计算机八股（面试知识点）辅导助手。从用户消息中抽取他正在问的知识点名称。

当前知识点：{current_topic}

近期对话（用来判断追问指代的是哪个知识点）：
{conversation}

示例：
    - "讲讲进程和线程的区别" -> "进程与线程的区别"
    - "什么是死锁？" -> "死锁"
    - "TCP 三次握手到底在握什么" -> "TCP 三次握手"
    - "MySQL 索引为什么会失效" -> "MySQL 索引失效"
    - "你好呀" -> "unknown"
    - "我想学操作系统" -> "操作系统"
    - （当前知识点=死锁）"那怎么预防呢？" -> "same"
    - （当前知识点=unknown、近期对话在讲死锁）"那怎么预防呢？" -> "死锁"

规则：
- 只要消息涉及任何计算机 / 编程 / 面试知识点，就返回该知识点名称（用中文，简短）。
- 如果这条消息是对当前知识点的追问、回答、补充或确认，只返回 "same"。
- 但如果「当前知识点」是 unknown，就先从近期对话推断他在问什么，直接返回那个知识点名称。
  追问（"那怎么预防呢""为什么""举个例子"）脱离上下文没有意义，必须结合近期对话判断。
- 只有当最新消息和近期对话都纯属寒暄、完全没有任何技术内容时，才返回 "unknown"。
- 不要返回 "unknown" / "same" / 知识点名之外的任何文字，也不要加标点、引号或 markdown。

用户最新消息：{latest_message}"""


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


PPT_OUTLINE_PROMPT = """你是计算机八股（面试知识点）课程的备课助手。请为教师准备一份关于「{topic}」的课堂讲义大纲。

{audience_line}
知识库资料（有则优先依据，没有就用你自己的知识，但不要编造来源）：
{context}

只返回 JSON，结构如下：
{{
  "title": "本讲标题",
  "objectives": ["教学目标 1", "教学目标 2"],
  "sections": [
    {{"title": "章节标题", "points": ["该章节要点 1", "要点 2"]}}
  ],
  "key_points": ["面试常考要点 1", "要点 2"],
  "examples": ["例子或场景 1", "例子 2"],
  "questions": ["课堂上可提问的问题 1", "问题 2"],
  "summary": ["一句话总结 1", "总结 2"]
}}

规则：
- 全部用中文，面向正在准备面试的学生。
- sections 给 3-5 个章节，每章 2-4 个要点，按「是什么 → 为什么 → 怎么用 → 面试怎么考」的顺序组织。
- key_points 是面试最常问、最值得背下来的点，不要和 sections 要点重复罗列。
- examples 要具体：给场景、代码或数值，不要只写「举个死锁的例子」。
- questions 是教师课堂上用来确认学生是否真懂的追问，要有区分度。
- summary 控制在 2-3 条，每条一句话能说完。
- 不要编造资料中不存在的来源、页码或链接。
- 只返回 JSON 对象，不要任何其他文字。"""
