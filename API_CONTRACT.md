# AI Classroom 前后端接口契约

> **用途**：T8 前后端联调的唯一依据。后端已冻结，前端按本文档对接。
> **后端版本**：提交 `5ea03ed`（T0–T7 全部完成）
> **生成日期**：2026-10-05

---

## 0. 通用约定

| 项 | 值 |
|---|---|
| Base URL（本地） | `http://127.0.0.1:8000` |
| Swagger 自动文档 | `http://127.0.0.1:8000/docs` |
| 编码 | 全部 UTF-8，请求体 `Content-Type: application/json` |
| CORS | 已开启。后端读环境变量 `ALLOWED_ORIGINS`，默认 `["http://localhost:3000"]`，methods / headers 全开，`allow_credentials=true` |
| 错误响应体 | `{"detail": "错误描述（英文）"}` |
| 数据库未配置时 | 需要数据库的接口一律返回 **503**，`detail` 提示去填 `MYSQL_*` |

**限流**：命中限流返回 **429**。注意限流的计数键是**客户端 IP**（`get_remote_address`），不是用户 ID——同一个局域网内多个人会共享同一个额度。

| 接口 | 限额 |
|---|---|
| `POST /chat` | 10 次 / 分钟 |
| `POST /resources/ppt-outline` | 5 次 / 分钟 |
| `POST /upload` | 3 次 / 小时 |
| 其余接口 | 不限 |

---

## 1. 必须先在 Dictionary 上对齐的三个概念

这三个词后端有明确语义，**跟日常理解不完全一样**，对齐之前不要开工。

### `classroom_id` + `user_id` —— 「要不要落库」的开关

`POST /chat` 是否读写数据库，取决于请求里**有没有同时带这两个字段**：

| 传参情况 | 行为 |
|---|---|
| 两个都传 | 校验成员身份 → 恢复历史 → 恢复教学状态 → 落库提问和回答 → 沉淀画像 |
| 只传 `classroom_id` | **不落库**（`SessionLocal` 为空时同样不落库），也不校验身份 |
| 两个都不传 | 退化为纯内存对话，旧前端行为不变 |

> ⚠️ 前端**必须在第一次 `/chat` 之前**先建好 user / classroom / membership，否则消息不会持久化，刷新页面聊天记录就没了。

### `hint_level` —— 讲解深度，不是启发级别

取值 `0–3`，**每一层都会直接给答案**，区别只在展开程度：

| level | 讲法 |
|---|---|
| 0 | 一句话结论 |
| 1 | 面试标准答案（分点、可背诵、200 字内） |
| 2 | 展开原理：为什么是这样，底层机制与设计取舍 |
| 3 | 原理 + 具体例子 + 一个面试追问方向 |

服务端字段 `hint_level` 是**技术产物**，前端**不需要展示成"难度 0/1/2/3"**给学生看，它只用于 debugging。

### `role` —— 一个人有两个 role

`users.role` 是全局身份，`classroom_members.role` 是**这个课堂里**的身份。同一个人在 A 课堂是学生、在 B 课堂可以是教师。**权限判定一律看课堂里的 role。**

---

## 2. 接口总表（共 16 个）

| # | 方法 | 路径 | 用途 | 前端谁用 |
|---|---|---|---|---|
| 1 | POST | `/chat` | 学生提问，SSE 流式返回回答 | 学生 |
| 2 | GET | `/health` | 健康检查 | 双方 |
| 3 | POST | `/users` | 创建用户（幂等） | 双方 |
| 4 | POST | `/classrooms` | 创建课堂 | 教师 |
| 5 | POST | `/classrooms/{id}/members` | 加入课堂 | 双方 |
| 6 | GET | `/classrooms/{id}` | 课堂详情 | 双方 |
| 7 | GET | `/classrooms/{id}/members` | 成员列表 | 教师 |
| 8 | GET | `/classrooms/{id}/messages` | 聊天记录（全课堂） | 双方 |
| 9 | GET | `/students/{id}/profile` | 读画像 | 双方 |
| 10 | PUT | `/students/{id}/profile` | 手工修正画像 | 调试用 |
| 11 | GET | `/students/{id}/behaviors` | 学习行为流水 | 调试 / 教师 |
| 12 | GET | `/students/{id}/prompt-preview` | 预览讲法（不花额度） | 调试用 |
| 13 | POST | `/resources/ppt-outline` | **教师**备课，生成大纲 + pptx | 教师 |
| 14 | GET | `/resources/files/{file_name}` | 下载生成的 pptx | 教师 |
| 15 | POST | `/upload` | 上传 PDF 建临时问答库 | 可选 |
| 16 | DELETE | `/sessions/{session_id}` | 销毁上传的临时会话 | 可选 |

---

## 3. 逐接口详解

### 3.1 `POST /chat` —— 核心接口

**请求体**

```json
{
  "message": "死锁产生的四个必要条件是什么？",
  "classroom_id": 1,
  "user_id": 3,
  "topic": "",
  "hint_level": 0,
  "misconception": "",
  "resolved": false,
  "history": [],
  "session_id": "",
  "provider": "openai"
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `message` | string | ✅ | 1–1000 字符 | 学生本轮提问 |
| `classroom_id` | int \| null | ➖ | — | 传了才落库 |
| `user_id` | int \| null | ➖ | — | 与上面成对出现 |
| `topic` | string | ❌ | ≤100 | **会被服务端覆盖**，见下方注意事项 |
| `hint_level` | int | ❌ | 0–3 | **会被服务端覆盖** |
| `misconception` | string | ❌ | ≤500 | 同上 |
| `resolved` | bool | ❌ | — | 同上 |
| `history` | array | ❌ | ≤50 条 | 走 DB 时前端**可以不传**，服务端自己加载 |
| `session_id` | string | ❌ | — | 只有上传过 PDF 才用得到 |
| `provider` | string | ❌ | ollama/groq/gemini/openai，默认 `openai` | 前端**不要传**，保持默认 |

> 请求模型开了 `extra="forbid"`，**多传一个未知字段会直接 422**。

**响应：`text/event-stream`（SSE）**，不是一个 JSON。

```
data: {"type": "token", "content": "死锁"}\n\n
data: {"type": "token", "content": "产生"}\n\n
...
data: {"type": "state", "topic": "死锁", "hint_level": 0, "misconception": "", "resolved": false, "personalized": true}\n\n
data: [DONE]\n\n
```

| 事件 | 时机 | 载荷 |
|---|---|---|
| `token` | 逐字流式输出 | `{"type":"token","content":"片段"}` |
| `state` | 流结束时**最后一条** | `topic` / `hint_level` / `misconception` / `resolved` / `personalized` |
| `error` | 流中途失败 | `{"type":"error","content":"..."}` |
| `[DONE]` | 结束标记，**字面量，不是 JSON** | — |

> ⚠️ **最关键的一条**：回答过程中的错误是**走 SSE 事件体里的 `type=error`**，不是 HTTP 状态码。HTTP 状态码在流开始时就已经是 200 了。前端**必须**在 SSE 解析循环里处理 `error`，否则 LLM 挂掉时界面会转圈到天荒地老。

HTTP 层面的错误码：

| 码 | 原因 |
|---|---|
| 403 | 传了 `classroom_id` 但该 `user_id` 不是这个课堂的成员 |
| 422 | 字段校验失败（含多传字段） |
| 429 | 限流（10 次/分钟，按 IP） |
| 502 | LLM 评估节点调用失败 |
| 503 | `provider` 对应的环境没配好 |

**前端解析参考**

```ts
const res = await fetch(`${BASE}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message, classroom_id, user_id }),
});

const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";
let answer = "";
let state = null;

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const lines = buffer.split("\n\n");
  buffer = lines.pop() ?? "";

  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6).trim();
    if (payload === "[DONE]") return { answer, state };
    const evt = JSON.parse(payload);
    if (evt.type === "token") answer += evt.content;
    else if (evt.type === "state") state = evt;
    else if (evt.type === "error") throw new Error(evt.content);
  }
}
```

---

### 3.2 用户 / 课堂 / 成员

#### `POST /users` → 201

```json
// request
{ "username": "张三", "role": "student" }      // role: student | teacher，默认 student
// response
{ "id": 1, "username": "张三", "role": "student" }
```

`username` 唯一。**重名不会报错，会直接返回已有那条记录**（幂等创建），前端重复提交不会产生脏数据。

#### `POST /classrooms` → 201

```json
// request
{ "name": "计网八股冲刺班", "subject": "cs", "description": "可选" }
// response
{ "id": 1, "name": "计网八股冲刺班", "subject": "cs", "description": "可选" }
```

#### `POST /classrooms/{classroom_id}/members` → 201

```json
// request
{ "user_id": 3, "role": "student" }
// response
{ "id": 5, "classroom_id": 1, "user_id": 3, "role": "student" }
```

重复添加同一人不会报错（联合唯一约束），返回已有记录。
错误：课堂不存在 → 404；用户不存在 → 404。

#### `GET /classrooms/{classroom_id}` → 200

```json
{ "id": 1, "name": "计网八股冲刺班", "subject": "cs", "description": "可选" }
```

不存在 → 404。

#### `GET /classrooms/{classroom_id}/members` → 200

```json
{
  "classroom_id": 1,
  "count": 2,
  "members": [
    { "user_id": 1, "username": "王老师", "role": "teacher" },
    { "user_id": 3, "username": "张三", "role": "student" }
  ]
}
```

> AI **不在成员列表里**。它以 `messages.role = "assistant"` 参与对话，不占 user_id。

#### `GET /classrooms/{classroom_id}/messages` → 200

聊天室主数据源。`limit` 默认 100，最大 500。

```json
{
  "classroom_id": 1,
  "count": 3,
  "messages": [
    {
      "id": 12,
      "user_id": 3,
      "username": "张三",
      "role": "student",
      "content": "死锁的四个必要条件是什么？",
      "topic": null,
      "hint_level": 0,
      "created_at": "2026-10-05T15:20:33"
    },
    {
      "id": 13,
      "user_id": 3,
      "username": "张三",
      "role": "assistant",
      "content": "互斥、占有且等待……",
      "topic": "死锁",
      "hint_level": 0,
      "created_at": "2026-10-05T15:20:41"
    }
  ]
}
```

**字段说明**（这几个容易误解）：

- `username`：AI 的回复为 `null`；学生/教师消息为真实用户名。聊天室用它区分发言人。
- `role`：`student` / `assistant` / `teacher`。**注意 AI 是 `assistant` 不是 `teacher`**。
- `user_id`：在 assistant 消息上表示「这条回复是给谁的」，以便在多人课堂里区分对话线。
- `topic` / `hint_level`：只对 assistant 消息有意义，学生消息为 `null` / `0`。

> 这个端点返回**整个课堂的全量对话**（群聊视图），不按学生过滤——这是刻意为之，产品决策是「一个课堂 = 一个群」。

---

### 3.3 学生画像

#### `GET /students/{user_id}/profile`

`classroom_id` 是**可选 query 参数**，但**带不带返回的形状不一样**，这是最容易踩的坑：

**不带 `classroom_id`** → 返回列表包装：
```json
{ "user_id": 3, "count": 1, "profiles": [ {...画像对象...} ] }
```

**带 `classroom_id`** → 直接返回单个画像对象：
```json
{
  "user_id": 3,
  "classroom_id": 1,
  "overall_level": "beginner",
  "learning_preference": "倾向于先要结论再展开原理",
  "knowledge_mastery": { "死锁": 0.3, "TCP 三次握手": 0.8 },
  "weak_points": ["把死锁理解成进程死循环"],
  "mastery_average": 0.55,
  "topic_count": 2,
  "updated_at": "2026-10-05T15:20:41"
}
```

前端要用的是第二种。用户不存在 → 404；带 `classroom_id` 但没画像 → **404**（要判断是否有对话过）。

#### `PUT /students/{user_id}/profile` → 200

```json
// request（只传要改的字段）
{
  "classroom_id": 1,
  "knowledge_mastery": { "死锁": 0.9 }
}
```

`classroom_id` **必填**。只覆盖传了的字段。`knowledge_mastery` 的值会被钳制到 `[0, 1]` 并保留两位小数。
改了 `knowledge_mastery` 但没传 `overall_level` 时，服务端会自动重算等级。返回完整画像对象（同上）。

> 这是**调试/应急**接口，正常流程不调——画像是每轮对话自动沉淀的。

#### `GET /students/{user_id}/behaviors` → 200

`classroom_id` 可选，`limit` 默认 50 最大 500，按时间倒序。

```json
{
  "user_id": 3,
  "count": 2,
  "behaviors": [
    { "id": 7, "classroom_id": 1, "topic": "死锁", "action": "mastered", "hint_level": 1, "created_at": "..." },
    { "id": 6, "classroom_id": 1, "topic": "死锁", "action": "repeat_question", "hint_level": 2, "created_at": "..." }
  ]
}
```

`action` 取值：`ask_question` / `repeat_question` / `request_explanation` / `mastered`。

#### `GET /students/{user_id}/prompt-preview` → 200

`classroom_id` **必填**，另有 `topic`、`hint_level`(0–3)。

```json
{
  "user_id": 3,
  "classroom_id": 1,
  "topic": "死锁",
  "hint_level": 0,
  "start_level_suggested": 1,
  "effective_hint_level": 1,
  "strategy": "给出面试里的标准答案……",
  "personalized": true,
  "profile_brief": "该学生整体水平 beginner……",
  "profile": { ...完整画像对象... }
}
```

**不消耗 LLM 额度**，调提示词时用它迭代。新学生（`personalized=false`）时 `profile_brief` 为空串、`profile` 为 `null`。

---

### 3.4 教师备课

#### `POST /resources/ppt-outline` → 200

```json
// request
{ "topic": "TCP 三次握手", "classroom_id": 1, "teacher_id": 1, "audience": "" }
```

`audience` 可填 `""` / `beginner` / `intermediate` / `advanced`，留空让模型自己判断。`topic` 最长 100 字符。

```json
// response
{
  "topic": "TCP 三次握手",
  "classroom_id": 1,
  "audience": "",
  "retrieved": true,
  "outline": {
    "title": "TCP 三次握手",
    "objectives": ["理解为什么需要三次而不是两次"],
    "sections": [
      { "title": "为什么是三次", "points": ["确认双方收发能力正常"] }
    ],
    "section_titles": ["为什么是三次"],
    "key_points": ["SYN / SYN-ACK / ACK"],
    "examples": ["WireShark 抓包示意"],
    "questions": ["为什么不是两次？"],
    "summary": ["三次握手的本质是双向确认"]
  },
  "file_path": "D:\\...\\backend\\generated\\TCP_三次握手_xxx.pptx",
  "file_name": "TCP_三次握手_xxx.pptx",
  "download_url": "/resources/files/TCP_三次握手_xxx.pptx"
}
```

`sections` 是 `{title, points}` 对象数组；`section_titles` 是给前端快速渲染目录用的扁平数组（同一份数据的两种形态）。

错误码：

| 码 | 原因 |
|---|---|
| 403 | 不是该课堂成员，或在该课堂的身份不是 `teacher` |
| 404 | 用户 / 课堂不存在 |
| 429 | 超过 5 次/分钟 |
| 502 | LLM 调用失败，**或模型返回了空壳大纲** —— 提示模型偶发，前端要允许重试 |

> `file_path` 是服务端绝对路径，**前端不要用**，下载一律走 `download_url`（相对路径，拼 Base URL）。
> `.pptx` 渲染失败时 `file_name` / `download_url` 会是 `null`，但大纲照常返回——大纲是主产物，PPT 是附赠。

#### `GET /resources/files/{file_name}` → 200

返回二进制 pptx 文件，`Content-Type` 为 pptx MIME。不存在 → 404。
`file_name` 直接拼在 URL 里，**中文文件名需要 `encodeURIComponent`**。

---

### 3.5 文档上传（可选功能）

#### `POST /upload` → 200

`multipart/form-data`，字段名 `file`，只接受 PDF。

```json
{ "session_id": "3f2a...-...", "message": "Document indexed successfully." }
```

拿到 `session_id` 后传给 `/chat` 的 `session_id` 字段，回答会基于这份 PDF。

限制：单文件 ≤ 10MB，3 次/小时。**会话存在内存里，1 小时过期，服务重启即丢，最多同时保留 100 个。**

错误：非 PDF → 400；文件头不是 `%PDF-` → 400；超过大小 → 413；解析失败 → 422。

#### `DELETE /sessions/{session_id}` → 204

主动销毁会话，无响应体。

---

### 3.6 `GET /health` → 200

```json
{ "status": "ok", "provider": "openai", "model": "deepseek-flash", "database": "up" }
```

`database` 取值：`up` / `down` / `disabled`（未配 `MYSQL_*`）。
**建议前端启动时打一次**：`database` 不是 `up` 时聊天记录不会落库，应给用户提示。

---

## 4. 前端接入流程

### 学生端

```
1. POST /users          { username, role:"student" }        → 拿到 user_id
2. POST /classrooms/{cid}/members { user_id }               → 加入课堂（cid 由产品决定，MVP 可写死）
3. GET  /classrooms/{cid}/messages                          → 渲染历史聊天记录
4. POST /chat           { message, classroom_id, user_id }  → SSE 流式渲染回答
5. 回答结束后可以再拉一次 messages，或直接把 assistant 消息 push 进本地列表
```

> 第 5 步两种方式都行。差别是：重新拉 `messages` 拿到的 `id` 和 `created_at` 是权威的，本地 push 则省一次请求。**建议响应结束后统一重新拉一次**，避免本地列表与服务端不一致。

### 教师端

```
1. POST /users          { username, role:"teacher" }
2. POST /classrooms     { name, subject:"cs" }              → 拿到 classroom_id
3. POST /classrooms/{cid}/members { user_id, role:"teacher" } → 必须显式以 teacher 身份加入
4. GET  /classrooms/{cid}/members                           → 查看学生名单
5. POST /resources/ppt-outline { topic, classroom_id, teacher_id } → 渲染大纲 / 下载 pptx
```

> ⚠️ 第 3 步容易漏。**创建课堂并不会自动把创建者加为成员**，教师必须显式 `POST members` 且 `role="teacher"`，否则第 5 步会被 403。

---

## 5. 联调注意事项（按踩坑概率排序）

1. **`/chat` 的错误在 SSE 流里，不在 HTTP 状态码上。** 必须在 SSE 循环里处理 `type=error`。
2. **`(classroom_id, user_id)` 必须成对传**，缺一个就静默不落库，不报错——表现为"刷新页面记录全没了"。
3. **客户端回传的 `topic` / `hint_level` / `misconception` / `resolved` 一律被服务端覆盖。** 服务端是状态的唯一真相源。前端不用维护这几个值的本地状态，也不用回传。
4. **限流按 IP 计数**，不是按用户。本机联调时前端和后端同一 IP，10 次/分钟的 `/chat` 额度很容易打满（表现为 429）。调试期可临时关。
5. **`GET /students/{id}/profile` 带不带 `classroom_id` 返回结构不同**（对象 vs 列表包装），必须分支处理。
6. **请求体不能多字段**（`extra="forbid"`），多传一个就 422。后端加字段不会通知，所以别写死 request 类型，留宽松。
7. **`role` 有两个来源**：`users.role` 是全局，`classroom_members.role` 是课堂内。权限看后者。
8. **AI 消息的 `role` 是 `assistant`**，不是 `teacher`；它的 `username` 是 `null`。
9. **聊天室是全课堂共享的**（不按学生隔离上下文）。这是产品决策：B 能看到 A 的问答并接力追问。
10. **`download_url` 是相对路径**，要拼 Base URL；中文文件名要 `encodeURIComponent`。
11. **`provider` 字段别传**，保持默认 `openai`（实际指向 DeepSeek 兼容端点）。传了别的会因为环境没配而 503。
12. **PPT 生成是慢操作**（一次真实 LLM 调用，通常 10–30 秒），教师要有一眼可见的 loading 态。

---

## 6. 后端已知遗留（不影响联调，但需要知道）

| 项 | 影响 |
|---|---|
| `requirements.txt` 落后于 T7，缺 `python-pptx` / `lxml` / `XlsxWriter` | 换机器部署会缺依赖，**不影响本机** |
| `weak_points` 可能存在语义重复的条目 | 画像展示时可能看到相似描述出现多次 |
| 备课暂不看课堂学生画像 | `audience` 需教师手工选择 |
| 上传文档的会话存在内存里 | 服务重启后 `session_id` 失效，前端取到也无妨（会退化成不检索文档） |
| `db/repository.py` 中 `load_history` 的 docstring 写着"按学生隔离" | 与实际调用不符：`/chat` 调用时**刻意不传 `user_id`**（群聊共享上下文）。注释过时，以本文为准 |
