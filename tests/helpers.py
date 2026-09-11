"""
测试用的"假对象"（步骤 6）

为什么需要假对象（Mock / Fake）？
  LLM 调用有两个大问题：
    1. 慢 —— 每次要等几秒
    2. 贵 —— 每次都花钱
  如果测试真的去调 LLM，那"跑一次测试"就变成"花钱等半分钟"，完全没法用。
  所以测试里用"假对象"替代真对象：行为可控、瞬间返回、零成本。

这里准备三个假对象，接口和真实对象完全一致：
  - FakeLLMClient  ：替代 LLMClient（不联网，按 schema 返回预设数据）
  - FakeSearchTool ：替代 WebSearchTool（不联网，返回固定搜索结果）
  - FakeFetcher    ：替代 WebFetcher（不联网，返回固定正文）
"""
from src.models import (
    AgentAction,
    Citation,
    ExtractedFacts,
    ReflectionResult,
    ResearchPlan,
    SubQuestion,
)


class FakeLLMClient:
    """假的 LLM 客户端：按传入的 schema 返回预设数据，完全不联网。"""

    def __init__(
        self,
        actions: list[AgentAction] | None = None,
        reflections: list[ReflectionResult] | None = None,
        plan: ResearchPlan | None = None,
        facts: list[str] | None = None,
    ) -> None:
        # actions：AgentAction 队列，按顺序"消费"（模拟 ReAct 的多轮决策）
        self._actions = list(actions) if actions else []
        # reflections：反思结果队列，按顺序"消费"（模拟每轮的自我评估）
        self._reflections = list(reflections) if reflections else []
        self._plan = plan
        self._facts = facts if facts is not None else ["事实A", "事实B"]

        # 记录调用过程，方便测试断言"到底调了几次、传了什么"
        self.chat_prompts: list[str] = []
        self.structured_schemas: list[type] = []

    def chat(self, prompt: str, system: str | None = None) -> str:
        self.chat_prompts.append(prompt)
        return f"【假回答】{prompt[:20]}"

    def generate_structured(self, prompt: str, schema: type, system: str | None = None):
        self.structured_schemas.append(schema)

        if schema is ResearchPlan:
            return self._plan or ResearchPlan(
                sub_questions=[SubQuestion(question="子问题1", priority=5)],
                overall_approach="总体研究思路",
            )

        if schema is AgentAction:
            if self._actions:
                return self._actions.pop(0)
            # 队列用完后默认"收尾"，避免测试陷入死循环
            return AgentAction(thought="资料已足够", action="finish", answer="兜底答案")

        if schema is ReflectionResult:
            if self._reflections:
                return self._reflections.pop(0)
            # 默认"资料已足够"
            return ReflectionResult(is_sufficient=True, reason="资料足够", missing="无")

        if schema is ExtractedFacts:
            return ExtractedFacts(facts=list(self._facts))

        raise AssertionError(f"FakeLLMClient 遇到未预期的 schema：{schema}")


class FakeSearchTool:
    """假的搜索工具：返回固定的一组搜索结果，不联网。"""

    def __init__(self, citations: list[Citation] | None = None) -> None:
        self.citations = (
            citations
            if citations is not None
            else [
                Citation(title="文章A", url="https://example.com/a", summary="A的摘要"),
                Citation(title="文章B", url="https://example.com/b", summary="B的摘要"),
            ]
        )
        # 记录每次搜索用的关键词，方便断言
        self.queries: list[str] = []

    def search(self, query: str) -> list[Citation]:
        self.queries.append(query)
        return list(self.citations)


class FakeFetcher:
    """假的网页抓取工具：直接返回固定正文，不联网。"""

    def __init__(self, text: str = "这是一段网页正文内容。") -> None:
        self.text = text
        self.urls: list[str] = []

    def fetch(self, url: str) -> str:
        self.urls.append(url)
        return self.text
