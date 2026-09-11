"""
ReAct 循环核心模块（步骤 4 + 步骤 5）

ReAct = Reasoning（思考）+ Acting（行动）
循环结构：Thought → Action → Observation →（重复，直到 finish）

这个模块实现 ResearchAgent，是 Agent 的"大脑"：
  1. 制定研究计划（Planning）：把大主题拆成子问题（步骤 3 的 ResearchPlan）
  2. 任务分解（Task Decomposition）：逐个处理每个子问题
  3. 对每个子问题跑一轮 ReAct 循环：
     - Thought：让 LLM 思考下一步做什么
     - Action：LLM 决定"继续搜索"还是"结束"
     - Observation：执行动作后的观察结果
  4. 循环直到 LLM 说"finish"，或达到最大循环次数（防止死循环）
  5. 汇总所有子问题的答案，生成带 [n] 引用编号的研究报告（步骤 5）

步骤 5 相比步骤 4 的关键变化：
  步骤 4：_mock_search() —— 让 LLM"假装"搜索，结果不可信，只为理解循环机制
  步骤 5：_web_search()  —— 调用真实搜索（Tavily）+ 抓取网页正文，结果可溯源
"""
from src.config import get_settings
from src.llm.client import LLMClient
from src.models import AgentAction, ResearchPlan
from src.tools import MockSearchTool, SourceRegistry, WebFetcher, WebSearchTool
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 系统提示词：告诉 LLM 在 ReAct 循环中扮演什么角色、遵循什么规则
REACT_SYSTEM_PROMPT = (
    "你是一名严谨的研究助手，正在用 ReAct 循环研究一个子问题。"
    "每一步你都要先思考（thought），再决定行动（action）："
    "如果现有信息不足以回答子问题，就选择 search 并给出精准的搜索关键词；"
    "如果信息已经足够，就选择 finish 并在 answer 里给出完整、有条理的回答。"
    "输出内容中请使用中文引号「」或“”，不要使用英文双引号，以免 JSON 解析出错。"
)

# 撰写报告时的系统提示词，重点是"只能引用给定的来源编号，不许编造"
REPORT_SYSTEM_PROMPT = (
    "你是一名专业的研究报告撰写者。"
    "你只能使用用户提供的来源编号来标注引用，绝对不要编造不存在的编号或链接。"
    "如果某个结论没有对应来源，就如实陈述，不要强行加引用。"
)


class ResearchAgent:
    """研究型 Agent：制定计划，对每个子问题执行 ReAct 循环，最后汇总成带引用的报告。"""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        search_tool=None,
        fetcher: WebFetcher | None = None,
    ) -> None:
        """
        参数：
          llm_client: LLM 客户端；不传则自己创建（依赖注入，方便测试时传假对象）
          search_tool: 搜索工具；不传则自动选择（有 Tavily Key 用真实搜索，否则用模拟搜索）
          fetcher: 网页抓取工具；不传则用默认的 WebFetcher
        """
        settings = get_settings()
        self.llm = llm_client or LLMClient()
        self.max_iterations = settings.max_iterations
        self.fetch_top_n = settings.fetch_top_n  # 每次搜索抓取前 N 条网页正文

        # 搜索工具：默认自动选择。显式传入则用传入的（方便测试或强制用模拟搜索）
        self.search_tool = search_tool or self._default_search_tool()

        # 抓取工具：用来获取网页正文（注意 fetcher 是可选依赖，允许传 None 表示不抓取）
        self.fetcher = fetcher if fetcher is not None else WebFetcher()

        # 引用登记处：记录本次研究用到的所有来源，负责编号与去重
        # 每次 research() 开始时会重置，避免多次研究之间互相污染
        self.registry = SourceRegistry()

    # ==================== 对外主流程 ====================

    def research(self, topic: str, with_report: bool = True) -> dict:
        """
        研究一个主题，返回结果字典。

        参数：
          topic: 研究主题
          with_report: 是否在最后生成一份带引用的研究报告（默认 True）

        返回：
          {
            "topic": 主题,
            "plan": ResearchPlan 对象,
            "answers": [(子问题, 答案), ...],
            "sources": [Citation, ...],       # 本次研究引用到的所有来源
            "report": 报告正文（with_report=False 时不含此键）,
          }
        """
        logger.info("========== 研究开始：%s ==========", topic)
        logger.info("搜索模式：%s", type(self.search_tool).__name__)

        # 每次研究前重置来源登记处，保证编号从 [1] 重新开始
        self.registry = SourceRegistry()

        # 第一步：规划（Planning）—— 把大主题拆成子问题
        plan = self._make_plan(topic)

        # 第二步：任务分解 + 逐个执行（Task Decomposition）
        answers: list[tuple[str, str]] = []
        total = len(plan.sub_questions)
        for i, sq in enumerate(plan.sub_questions, 1):
            logger.info("---------- 子问题 %d/%d：%s ----------", i, total, sq.question)
            answer = self._run_react(sq.question)
            answers.append((sq.question, answer))

        logger.info("========== 所有子问题已回答完毕，共 %d 个 ==========", len(answers))

        result = {
            "topic": topic,
            "plan": plan,
            "answers": answers,
            "sources": self.registry.items(),
        }

        # 第三步：汇总成带引用的报告（步骤 5 新增）
        if with_report:
            result["report"] = self._write_report(topic, answers)

        return result

    # ==================== 内部方法：初始化相关 ====================

    def _default_search_tool(self):
        """
        自动选择搜索工具：
          - 配置了 TAVILY_API_KEY → 用真实的 WebSearchTool
          - 没配置 → 退化为 MockSearchTool（LLM 模拟），并给出明确警告
        """
        if get_settings().tavily_api_key:
            return WebSearchTool()

        logger.warning(
            "未配置 TAVILY_API_KEY，将使用【模拟搜索】（结果是 LLM 编的，不可信，仅用于体验流程）"
        )
        return MockSearchTool(self.llm)

    # ==================== 内部方法：规划与循环 ====================

    def _make_plan(self, topic: str) -> ResearchPlan:
        """制定研究计划：把宽泛主题拆解成若干子问题（复用步骤 3 的结构化输出）。"""
        logger.info("正在制定研究计划...")
        plan = self.llm.generate_structured(
            topic,
            ResearchPlan,
            system="你是一名专业的研究规划助手，负责把研究主题拆解成可执行的子问题。"
            "子问题内容中请使用中文引号「」或“”，不要使用英文双引号。",
        )
        logger.info("计划生成成功，共拆解出 %d 个子问题", len(plan.sub_questions))
        return plan

    def _run_react(self, question: str) -> str:
        """
        对单个子问题执行 ReAct 循环，返回最终答案。

        循环逻辑：
          每一轮：
            1. 让 LLM 输出 Thought + Action
            2. 如果 action == "finish"：返回 answer，循环结束
            3. 如果 action == "search"：真实搜索 + 抓取，得到 Observation
            4. 把 Observation 追加到上下文，进入下一轮
          直到 LLM 说 finish，或达到最大循环次数（兜底强制收尾）
        """
        # 用列表记录每一步的观察结果，作为下一轮 LLM 的"上下文/记忆"
        observations: list[str] = []

        for step in range(1, self.max_iterations + 1):
            # 构造 prompt：把子问题 + 已观察到的信息一起喂给 LLM
            prompt = self._build_react_prompt(question, observations)

            # 让 LLM 输出 Thought + Action（结构化输出，复用步骤 3 的能力）
            action = self.llm.generate_structured(prompt, AgentAction, system=REACT_SYSTEM_PROMPT)

            # 打印 Thought（思考）—— 这就是 ReAct 里的 Reasoning
            logger.info("  [第 %d 步] Thought: %s", step, action.thought)

            # 根据 action 分支处理 —— 这就是 ReAct 里的 Acting
            if action.action == "finish":
                logger.info("  [第 %d 步] Action: finish（信息已足够，结束）", step)
                return action.answer or ""

            # action == "search"：真实搜索 + 抓取网页正文，得到观察结果
            query = action.search_query or question
            logger.info("  [第 %d 步] Action: search(%s)", step, query)

            observation = self._web_search(query)
            logger.info("  [第 %d 步] Observation: %s", step, observation)

            # 把这次观察结果记下来，供下一轮 LLM 参考（这就是"上下文记忆"）
            observations.append(f"搜索「{query}」的结果：\n{observation}")

        # 走到这里说明达到最大循环次数仍没 finish，强制收尾
        logger.warning("  ⚠ 达到最大循环次数 %d，强制生成答案", self.max_iterations)
        return self._force_answer(question, observations)

    def _build_react_prompt(self, question: str, observations: list[str]) -> str:
        """构造每轮 ReAct 的 prompt：子问题 + 已有的观察信息。"""
        if not observations:
            context = "（还没有任何信息，请先搜索）"
        else:
            # 把历史观察逐条列出，作为 LLM 的"记忆"
            context = "\n".join(f"- {obs}" for obs in observations)

        return (
            f"当前要研究的子问题是：\n{question}\n\n"
            f"目前已收集到的信息：\n{context}\n\n"
            f"请决定下一步：信息不够就 search，信息足够就 finish 并给出答案。"
        )

    # ==================== 内部方法：搜索与抓取（步骤 5 核心）====================

    def _web_search(self, query: str) -> str:
        """
        执行一次"真实搜索 + 网页抓取"，返回给 LLM 看的 Observation 文本。

        流程：
          1. 调用搜索工具，拿到若干条结果（Citation）
          2. 每条结果到引用登记处登记，拿到一个 [n] 编号
          3. 对前 fetch_top_n 条结果，抓取网页正文（信息更完整）
          4. 把结果拼成一段文字作为 Observation 返回

        返回的文本里带 [n] 编号，这样 LLM 在写答案时就能"顺手"引用编号，
        最终报告里的 [n] 也就能和文末参考文献对应上。
        """
        citations = self.search_tool.search(query)
        if not citations:
            return "（本次搜索没有返回结果）"

        parts: list[str] = []
        for index, citation in enumerate(citations):
            # 登记来源：同一个 URL 只会拿到同一个编号（去重）
            number = self.registry.add(citation)

            # 默认用搜索摘要；对前 N 条尝试抓取正文，拿到更完整的内容
            snippet = citation.summary
            if index < self.fetch_top_n and citation.url.startswith("http"):
                full_text = self.fetcher.fetch(citation.url)
                if full_text:
                    snippet = full_text  # WebFetcher 内部已按 fetch_max_chars 截断

            parts.append(f"[{number}] {citation.title}\n链接：{citation.url}\n内容：{snippet}")

        return "\n\n".join(parts)

    def _force_answer(self, question: str, observations: list[str]) -> str:
        """循环超限时的兜底：直接让 LLM 基于已有信息给出答案。"""
        context = "\n".join(f"- {obs}" for obs in observations) if observations else "（无）"
        return self.llm.chat(
            f"请基于以下信息，直接回答子问题：\n{question}\n\n已有信息：\n{context}",
            system="你是一名研究助手，请基于给定信息给出尽可能完整的回答。",
        )

    # ==================== 内部方法：报告生成（步骤 5 核心）====================

    def _write_report(self, topic: str, answers: list[tuple[str, str]]) -> str:
        """
        把所有子问题的答案汇总成一份完整的研究报告。

        关键设计：报告里的引用编号 [n] 由"来源登记处"决定（真实链接），
        而不是让 LLM 自己编。这样能保证 [n] 和文末参考文献严格对应。

        注意：这里只生成"报告正文"，文末的参考文献列表由调用方
        （demo 脚本）根据 result["sources"] 打印，避免 LLM 编造链接。
        """
        logger.info("正在汇总生成研究报告...")

        sources = self.registry.items()
        if sources:
            # 把已登记来源列成清单，编号与报告正文里的 [n] 一致
            source_lines = "\n".join(f"[{i}] {c.title} —— {c.url}" for i, c in enumerate(sources, 1))
        else:
            source_lines = "（本次研究没有检索到外部来源）"

        # 把各子问题的答案整理成一段材料
        answer_lines = "\n\n".join(f"【子问题】{q}\n【结论】{a}" for q, a in answers)

        prompt = (
            f"研究主题：{topic}\n\n"
            f"以下是各子问题的研究结论：\n{answer_lines}\n\n"
            f"以下是本次研究可引用的来源清单（编号已经固定，不要新增或改动）：\n{source_lines}\n\n"
            f"请基于以上材料写一份结构化的研究报告，要求：\n"
            f"1. 有清晰的总标题和若干小节；\n"
            f"2. 关键论断后面用 [编号] 标注来源，编号必须来自上面的清单；\n"
            f"3. 不要编造清单之外的编号，也不要编造链接。"
        )

        return self.llm.chat(prompt, system=REPORT_SYSTEM_PROMPT)
