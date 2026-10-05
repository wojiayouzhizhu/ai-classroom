# AI Classroom

面向计算机八股 / 面试知识学习的 AI 智能教学系统。一个教室 + 一个学科，
支持学生提问、AI 基于知识库作答、教师生成教学资源。

## 功能

- 学生：加入教室、聊天提问、历史记录、基于个人画像的个性化回答
- 教师：创建教室、查看成员与聊天、输入主题生成 PPT 大纲
- AI：Teaching Agent（学生问答）+ Teacher Resource Agent（资源生成）
- 知识库：Markdown 文档 → 分块 → Embedding → 向量检索，保留四级 metadata
- 学生画像：规则型可解释画像（level / preference / mastery / weak_points），影响 Prompt

## 技术栈

- 前端：Next.js + TypeScript
- 后端：FastAPI + LangGraph + LangChain
- 数据：MySQL + ChromaDB
- 模型：DeepSeek（`deepseek-flash`，走 OpenAI 兼容接口）
- 测试：unittest

## 目录结构

```text
REQUIREMENTS.md / DEVELOPMENT.md / DEVELOPMENT_PLAN.md   需求与开发计划
tutorial.md                                             后端源码课程（改造记录）
knowledge/cs/{os,network}/                              八股知识库文档（8 篇）
Tutor-Chatbot-main/backend/                             后端（FastAPI + LangGraph）
Tutor-Chatbot-main/frontend/                            前端（Next.js）
```

后端与前端都在 `Tutor-Chatbot-main/` 下——这是开源原项目的目录名，保留原样以便对照上游改动。

## 快速开始

```bash
cd Tutor-Chatbot-main/backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env        # 填 LLM_API_KEY（DeepSeek）与 MYSQL_* 配置

python init_db.py          # 建库建表（需本机 MySQL 已启动）
python build_kb.py         # 构建八股知识库（首次会下载中文 embedding 模型）
uvicorn app:app --reload   # 起服务，默认 8000
```

前端：

```bash
cd Tutor-Chatbot-main/frontend
npm install && npm run dev
```

> 构建知识库时若下载模型失败，加两个环境变量走镜像并禁用符号链接：
> `HF_ENDPOINT=https://hf-mirror.com`、`HF_HUB_DISABLE_SYMLINKS=1`（Windows 必加）。

## 验证

```bash
cd Tutor-Chatbot-main/backend
python run_tests.py        # 纯逻辑测试，不花钱不联网（81 例）
python smoke_chat.py       # 真实调用 LLM，验多轮讲解深度递进
python smoke_db.py         # 验持久化与成员校验（需服务在跑）
python smoke_profile.py    # 验学生画像自动沉淀（需服务在跑）
python smoke_personalize.py # 验同一道题在两种画像下讲法不同（需服务在跑）
python smoke_resource.py   # 验教师备课大纲与 .pptx 生成（需服务在跑）
```

各接口有独立限流（`/chat` 10 次/分钟、`/resources/ppt-outline` 5 次/分钟），
同一脚本一分钟内别连着跑两遍。

## 当前进度

按 `DEVELOPMENT_PLAN.md` 的十二个阶段推进，已完成前八个：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 三 | 八股知识库（操作系统 + 计算机网络） | ✅ |
| 四 | MySQL 持久化（六张表） | ✅ |
| 五 | 教室 / 成员 / 角色 + 教学状态落库 | ✅ |
| 六 | StudentProfile 学生画像 | ✅ |
| 七 | 个性化 Prompt（画像 + RAG + 问题 组合进提示词） | ✅ |
| 八 | Teacher Resource Agent（备课大纲 JSON + .pptx） | ✅ |
| 九 | 前后端联调（接口契约见 `API_CONTRACT.md`） | 待前端 |
| 十~十二 | 测试、性能记录、项目整理 | 收尾 |

改造过程与踩坑记录在 `tutorial.md`，每一阶段一个 git 提交。

阶段性的开发总结见 `PROJECT_REPORT.md`：记录了 T0–T7 遇到的 10 个设计问题
（含选型理由）、11 个 bug（含根因与修复理由）、6 张表的设计取舍，以及核心
算法与验证体系。

## 二次开发声明

本项目基于开源项目 Tutor-Chatbot 二次开发。原项目提供了 Chat、Agent、RAG
基础能力；本人在其基础上新增了：

- 学生画像模块（StudentProfile）及其对 Prompt 的影响链路
- Teacher Resource Agent 与教学资源生成接口
- 计算机八股知识库的 metadata 设计与检索优化
- 教室 / 成员 / 角色区分相关 API 与数据表

同时移除了原项目的 Judge0 代码执行链路（与八股问答场景无关），
并把苏格拉底式启发提示改为中文八股讲解式（按讲解深度分四层）。

## 文档

- [需求说明](REQUIREMENTS.md)
- [开发说明](DEVELOPMENT.md)
- [开发计划](DEVELOPMENT_PLAN.md)
- [后端源码课程](tutorial.md)
