"""
模拟搜索工具（步骤 4 用；步骤 5 中作为"降级方案"保留）

作用：没有配置真实搜索 API（Tavily）时，让 LLM 假装搜索引擎，生成一段"看起来像搜索结果"的文字。

为什么要保留它？
  1. 步骤 4 学 ReAct 循环时，用它可以专注理解循环机制，不被网络请求干扰
  2. 如果学习者暂时不想注册 Tavily，程序也能跑通完整流程（只是结果不可信）

重要提醒：
  模拟搜索生成的"结果"是 LLM 编的，不是真实资料！
  所以它只能用来"体验流程"，绝不能用来生成正式的研究报告。
"""
from src.llm.client import LLMClient
from src.models import Citation


class MockSearchTool:
    """用 LLM 模拟的搜索工具（接口与 WebSearchTool 完全一致）。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    def search(self, query: str) -> list[Citation]:
        """让 LLM 生成一段模拟的搜索摘要，包装成一条 Citation 返回。"""
        text = self.llm.chat(
            f"请针对下面的搜索词，生成 2-3 条相关且具体的信息摘要（模拟搜索引擎返回）：\n{query}",
            system="你是一个搜索引擎，根据用户的搜索词返回相关、具体、有信息量的摘要。",
        )
        # 用 mock:// 前缀标注这是模拟来源，避免被误当成真实链接
        return [
            Citation(
                title=f"（模拟）{query}",
                url="mock://llm-simulated",
                summary=text[:300],
            )
        ]
