"""
ResearchAgent 主流程的单元测试（步骤 6）

这是本项目最重要的测试：**不联网、不花钱**，就能验证整条 Agent 流程。

做法：把三个"真对象"全部替换成 tests/helpers.py 里的假对象
  - FakeLLMClient  替代 LLMClient
  - FakeSearchTool 替代 WebSearchTool
  - FakeFetcher    替代 WebFetcher

覆盖的场景：
  1. 压缩器 / 反思器是否正确装配
  2. 反思判定"资料足够"→ 是否提前结束并基于事实作答
  3. 反思判定"资料不足"→ 是否继续循环，直到 LLM 说 finish
  4. 去重是否生效（重复来源不再重复登记、不再重复提取事实）
  5. 达到最大循环次数时是否有兜底答案
"""
from src.agent import ContextCompressor, Reflector, ResearchAgent
from src.models import AgentAction, Citation, ReflectionResult
from tests.helpers import FakeFetcher, FakeLLMClient, FakeSearchTool


def _build_agent(llm: FakeLLMClient, search: FakeSearchTool | None = None) -> ResearchAgent:
    """构造一个"全假"的 Agent（不联网、不花钱）。"""
    return ResearchAgent(
        llm_client=llm,
        search_tool=search or FakeSearchTool(),
        fetcher=FakeFetcher(),
    )


def test_components_are_wired():
    """压缩器与反思器应该在构造 Agent 时被自动装配好。"""
    agent = _build_agent(FakeLLMClient())

    assert isinstance(agent.compressor, ContextCompressor)
    assert isinstance(agent.reflector, Reflector)
    # 它们应该复用同一个 LLM 客户端（这样费用统计才统一）
    assert agent.compressor.llm is agent.llm
    assert agent.reflector.llm is agent.llm


def test_reflection_sufficient_ends_search_early():
    """反思判定资料足够时，应提前结束搜索，并把收集到的事实带出来。"""
    llm = FakeLLMClient(
        # 只准备一个 search 动作：如果流程还需要更多轮，就会因为"没动作"而走兜底 finish
        actions=[AgentAction(thought="先搜索", action="search", search_query="测试关键词")],
        reflections=[ReflectionResult(is_sufficient=True, reason="资料已足够", missing="无")],
        facts=["事实1", "事实2"],
    )
    agent = _build_agent(llm)

    result = agent.research("测试主题", with_report=False)

    # 假搜索工具每次返回 2 条结果，每条压缩出 2 条事实 → 共 4 条
    assert len(result["sources"]) == 2
    assert len(result["notes"]) == 4
    assert len(result["answers"]) == 1
    # 反思判定足够 → 答案由 _answer_from_notes 生成（走的是 chat）
    assert "假回答" in result["answers"][0][1]


def test_reflection_insufficient_continues_until_finish():
    """反思判定资料不足时，应继续下一轮，直到 LLM 主动 finish。"""
    llm = FakeLLMClient(
        actions=[
            AgentAction(thought="先搜索", action="search", search_query="第一轮"),
            AgentAction(thought="够了", action="finish", answer="最终答案"),
        ],
        reflections=[
            ReflectionResult(
                is_sufficient=False, reason="还缺信息", missing="缺少对比数据", suggested_query="第二轮"
            )
        ],
    )
    agent = _build_agent(llm)

    result = agent.research("测试主题", with_report=False)

    # 答案应来自 LLM 的 finish 分支
    assert result["answers"][0][1] == "最终答案"
    # 只搜了一轮，所以来源数是 2
    assert len(result["sources"]) == 2


def test_duplicate_sources_are_skipped():
    """同一批搜索结果重复出现时，第二轮应全部被去重跳过。"""
    # FakeSearchTool 每次返回相同的两条结果 → 第二轮必然全部重复
    llm = FakeLLMClient(
        actions=[
            AgentAction(thought="搜第一轮", action="search", search_query="q1"),
            AgentAction(thought="搜第二轮", action="search", search_query="q2"),
            AgentAction(thought="够了", action="finish", answer="答案"),
        ],
        reflections=[
            ReflectionResult(is_sufficient=False, reason="缺", missing="x"),
            ReflectionResult(is_sufficient=False, reason="缺", missing="y"),
        ],
    )
    agent = _build_agent(llm)

    result = agent.research("测试主题", with_report=False)

    # 虽然搜了两轮，但来源只有 2 条（第二轮全被去重）
    assert len(result["sources"]) == 2
    # 事实数也没有翻倍（第二轮没有新增任何事实）
    assert len(result["notes"]) == 4


def test_dedup_by_title_with_different_url():
    """URL 不同但标题相同的来源，也应被去重跳过。"""
    llm = FakeLLMClient(
        actions=[
            AgentAction(thought="搜", action="search", search_query="q"),
            AgentAction(thought="够了", action="finish", answer="答案"),
        ],
        reflections=[ReflectionResult(is_sufficient=False, reason="缺", missing="x")],
    )
    # 两条结果标题相同（仅标点/空格不同）、URL 不同
    search = FakeSearchTool(
        citations=[
            Citation(title="AI Agent 的未来！", url="https://a.com", summary="A"),
            Citation(title="AI agent的未来", url="https://b.com", summary="B"),
        ]
    )
    agent = _build_agent(llm, search=search)

    agent.research("测试主题", with_report=False)

    # 第二条因标题重复被跳过 → 只登记了 1 条来源
    assert len(agent.registry) == 1


def test_max_iterations_fallback_produces_answer():
    """达到最大循环次数仍未结束时，应有兜底答案（不能卡死）。"""
    llm = FakeLLMClient(
        actions=[AgentAction(thought="一直搜", action="search", search_query="q")],
        reflections=[ReflectionResult(is_sufficient=False, reason="永远不够", missing="x")],
    )
    agent = _build_agent(llm)
    agent.max_iterations = 1  # 把循环上限压到 1 轮，方便测试兜底逻辑

    result = agent.research("测试主题", with_report=False)

    assert "假回答" in result["answers"][0][1]


def test_research_with_report_includes_report_text():
    """开启报告生成时，返回值里应包含报告正文。"""
    llm = FakeLLMClient(
        actions=[AgentAction(thought="搜", action="search", search_query="q")],
        reflections=[ReflectionResult(is_sufficient=True, reason="够了", missing="无")],
    )
    agent = _build_agent(llm)

    result = agent.research("测试主题", with_report=True)

    assert "report" in result
    assert "假回答" in result["report"]


def test_answer_from_notes_without_notes_returns_placeholder():
    """没有事实时，_answer_from_notes 应返回占位文案，而不是调用 LLM。"""
    agent = _build_agent(FakeLLMClient())

    assert agent._answer_from_notes("问题", []) == "（没有可用资料，无法回答）"


def test_search_failure_is_handled_gracefully():
    """搜索返回空结果时，流程不应崩溃，Observation 应给出说明。"""

    class EmptySearchTool:
        def search(self, query):
            return []

    llm = FakeLLMClient(
        actions=[AgentAction(thought="搜", action="search", search_query="q")],
        reflections=[ReflectionResult(is_sufficient=False, reason="缺", missing="x")],
    )
    agent = ResearchAgent(llm_client=llm, search_tool=EmptySearchTool(), fetcher=FakeFetcher())

    result = agent.research("测试主题", with_report=False)

    assert len(result["sources"]) == 0
    # 关键：流程没有崩溃，仍然返回了一个非空的答案
    assert result["answers"][0][1]
