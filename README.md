# Deep Research Agent

> 一个用 **原生 Python + LangChain** 从零手写的自主研究智能体（Autonomous Research Agent）。
>
> 给它一个研究主题，它会自动**制定研究计划 → 拆解子问题 → 反思式循环搜索 → 抓取网页 → 压缩信息 → 生成带引用来源的研究报告**。

本项目是一个**面向学习者的分步实战项目**：不直接调用 LangChain 的高阶封装，而是手写 ReAct 循环、工具调用、引用溯源等核心环节，把每个概念都"拆开看一遍"，理解 Agent 到底是怎么运转的。

---

## 功能特性

| 特性 | 说明 |
| --- | --- |
| 自动规划 | 把宽泛主题拆解成带优先级的子问题（Planning + Task Decomposition） |
| ReAct 循环 | 手写 `Thought → Action → Observation` 循环，边想边做 |
| 真实搜索 | 接入 Tavily 搜索 API，获取真实网页结果 |
| 网页抓取 | `requests` + `BeautifulSoup` 提取网页正文 |
| 上下文压缩 | 把网页长文提炼成 3~5 条关键事实，避免上下文爆炸 |
| 反思机制 | Agent 自我评估"资料够不够"，够了提前收尾、不够则精准续搜 |
| 引用溯源 | 报告里的论断带 `[n]` 编号，文末附真实参考文献列表 |
| 结果去重 | 相同 URL 或相同标题的来源自动跳过 |
| 成本统计 | 记录每次调用的 token 与费用，心里有数 |
| 失败重试 | 网络抖动 / 限流时自动重试，不轻易崩溃 |
| 单元测试 | `pytest` + Mock，**不花一分钱**就能跑完整测试 |
| 网页界面 | Streamlit 展示计划、运行日志、研究结果及 Markdown 下载 |
| 人工确认 | 生成计划后暂停，可增删子问题、修改优先级与整体思路，确认后执行 |

---

## 技术栈

- **语言**：Python 3.11+
- **LLM 框架**：LangChain（`langchain`、`langchain-openai`）
- **模型服务**：DeepSeek（走 OpenAI 兼容协议，换成 GPT / 通义 / 智谱只需改 `.env`）
- **数据结构**：Pydantic + Structured Output（结构化输出）
- **搜索**：Tavily API
- **抓取**：requests + BeautifulSoup4
- **可靠性**：tenacity（重试）、json-repair（修复 LLM 生成的不合规 JSON）
- **配置**：pydantic-settings（`.env` 管理）
- **测试**：pytest + unittest.mock

---

## 项目结构

```text
deep-research-agent/
├── src/
│   ├── config.py            # 配置管理（读取 .env）
│   ├── main.py              # 基础演示入口
│   ├── demo_react.py        # ★ 主入口：跑一次完整研究
│   ├── agent/               # Agent 核心逻辑
│   │   ├── researcher.py    #   ReAct 循环 + 报告生成
│   │   ├── compressor.py    #   上下文压缩（长文 → 关键事实）
│   │   └── reflector.py     #   反思（自我评估资料是否足够）
│   ├── llm/
│   │   └── client.py        # LLM 调用封装（重试 / 结构化输出 / 费用统计）
│   ├── models/
│   │   └── schemas.py       # Pydantic 数据模型
│   ├── tools/               # Agent 可调用的工具
│   │   ├── search.py        #   真实搜索（Tavily）
│   │   ├── fetcher.py       #   网页正文抓取
│   │   ├── sources.py       #   来源登记（编号 + 去重）
│   │   └── mock_search.py   #   模拟搜索（无 Key 时的降级方案）
│   └── utils/
│       └── logger.py        # 统一日志
├── tests/                   # 单元测试（Mock，不花钱）
├── .env.example             # 配置模板
├── requirements.txt
├── pytest.ini
└── 开发路线.md               # 分步学习路线
```

---

## 快速开始

### 1. 安装依赖

```powershell
# 创建并激活虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

复制配置模板并填入你的 Key：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```text
# 必填：DeepSeek API Key（https://platform.deepseek.com）
OPENAI_API_KEY=sk-你的key

# 选填：Tavily 搜索 Key（https://tavily.com 免费注册，1000 次/月）
# 不填也能跑，但会退化成"LLM 模拟搜索"，结果不可信
TAVILY_API_KEY=tvly-你的key
```

> `.env` 已被 `.gitignore` 忽略，不会被提交到 GitHub，请放心填写。

### 3. 运行

网页入口（在项目根目录运行）：

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

打开终端显示的本地网址，输入主题并点击「生成研究计划」。这一步仅调用规划模型，
不会开始搜索。表格支持增删改子问题，优先级为 1–5，数字越大越先执行；相同优先级
保持表格顺序。编辑整体思路后点击「确认并开始研究」，Agent 会直接执行确认后的计划。

完成后可以查看报告、参考文献、关键事实、子问题答案、日志与累计费用，并下载附参考文献
的 Markdown。普通页面交互不会重新研究。执行失败会保留计划，可以再次确认重试；重试会
从研究阶段开头执行，已产生的费用仍计入累计统计。更换主题或重新生成计划会清除旧结果。
会话仅保存在当前浏览器连接中，刷新浏览器或重启服务后需要重新开始。

HITL（Human-in-the-Loop）的接入点位于 `ResearchAgent` 的两个公开方法之间：

```python
plan = agent.make_plan(topic)                 # 只生成计划
# 网页在这里等待用户编辑和确认，不需要 input() 或后台等待循环
result = agent.research_from_plan(topic, plan) # 执行确认后的计划
```

`app.py` 负责页面和会话状态，`src/ui/support.py` 负责表格校验、日志桥接与下载内容。
日志按当前执行线程隔离，结束后自动移除监听。页面最多保留最近 1000 条日志。
页面相关行为通过 Streamlit 官方 AppTest 配合 Fake/Mock 验证，不调用真实模型。

原命令行入口仍可一键研究：

```powershell
# 用默认主题
python -m src.demo_react

# 自定义研究主题
python -m src.demo_react "帮我研究未来几年 AI Agent 的发展趋势"
```

运行后你会看到：

1. 完整的 `Thought / Action / Observation / 反思` 过程日志
2. 一份带 `[1] [2]` 引用标注的**研究报告**
3. 文末的**参考文献**列表（真实链接）
4. 本次研究的**总 token 与费用**

---

## 运行测试

```powershell
python -m pytest
```

测试全部使用**假对象（Fake/Mock）**替代 LLM 与网络请求，因此：

- 不需要 API Key
- 不消耗任何费用
- 几秒内跑完

---

## 工作流程

```text
用户输入研究主题
      │
      ▼
① 制定研究计划 ──────────── 拆解成若干子问题（Planning）
      │
      ▼
② 对每个子问题执行 ReAct 循环
      │
      ├─ Thought       LLM 思考下一步做什么
      ├─ Action        LLM 决定：搜索 or 结束
      ├─ Observation   真实搜索 → 去重 → 抓取正文 → 压缩成关键事实
      └─ Reflection    自我评估：资料够了吗？不够就带着建议继续搜
      │
      ▼
③ 汇总生成研究报告 ──────── 带 [n] 引用编号
      │
      ▼
④ 输出报告 + 参考文献 + 费用统计
```

---

## 学习路线

本项目按 6 个步骤逐步构建，每一步都有明确的「完成标志」：

| 步骤 | 内容 | 核心知识点 |
| --- | --- | --- |
| 1 | 项目骨架与工程化基础 | 目录结构、配置管理、日志 |
| 2 | LLM 封装层 | 重试、Token 统计、类型注解 |
| 3 | 数据模型与结构化输出 | Pydantic、Structured Output |
| 4 | ReAct 循环核心 | ReAct、Planning、任务分解 |
| 5 | 搜索、抓取与引用溯源 | Tool Calling、Web Scraping、Citation |
| 6 | Agent 智能化 + 打磨发布 | 上下文压缩、反思、去重、单元测试 |

> 下一步计划：用 **LangGraph** 把整条流程用「图（State / Node / Edge）」重构一遍，体会"为什么需要编排框架"。

---

## 费用提示

每次完整研究大约会产生数十次 LLM 调用（规划 + 多轮循环 + 压缩 + 反思 + 报告）。想省钱可以：

- 调小 `.env` 里的 `MAX_ITERATIONS`（减少每轮循环次数）
- 调小 `FETCH_TOP_N`（减少网页抓取与压缩次数）
- 调小 `SEARCH_MAX_RESULTS`（每次搜索取更少结果）
- 使用主题更聚焦的研究问题（减少子问题数量）

---

## 说明

本项目为**学习目的**而写，代码中保留了大量中文注释，用于解释"为什么这么写"。生产环境使用还需补充：权限控制、缓存、异步并发、可观测性等能力。
