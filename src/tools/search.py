"""
网页搜索工具（步骤 5）

作用：把一个"搜索关键词"变成一组真实的网页结果（标题 / 链接 / 摘要）。

为什么单独封装成工具类？
  Agent 的 ReAct 循环需要"行动（Action）"，而"搜索"就是最典型的行动。
  把搜索封装成一个类，好处是：
    1. 接口统一：Agent 只管调用 search()，不关心底层是 Tavily 还是别的引擎
    2. 方便替换：以后想换成 Serper / Bing / 博查，只改这一个文件
    3. 方便测试：测试时可以注入一个"假搜索工具"，不真的发网络请求

本文件用的是 Tavily：
  它是专为 LLM Agent 设计的搜索 API，直接返回"干净的正文摘要"，
  不像传统搜索引擎那样要自己解析 HTML，非常适合新手。
"""
from tavily import TavilyClient

from src.config import get_settings
from src.models import Citation
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WebSearchTool:
    """基于 Tavily API 的真实网页搜索工具。"""

    def __init__(self, api_key: str | None = None, max_results: int | None = None) -> None:
        """
        参数：
          api_key: Tavily Key；不传则从配置（.env）里读
          max_results: 每次搜索最多返回几条结果；不传则从配置里读
        """
        settings = get_settings()
        self.api_key = api_key or settings.tavily_api_key
        self.max_results = max_results or settings.search_max_results

        if not self.api_key:
            # 没有 Key 时直接报错，让调用方知道"真实搜索不可用"
            # （Agent 会捕获这个情况并退化为模拟搜索，见 researcher.py）
            raise ValueError("未配置 TAVILY_API_KEY，无法使用真实搜索")

        # TavilyClient 是官方 SDK，内部封装了 HTTP 请求与鉴权
        self._client = TavilyClient(api_key=self.api_key)

    def search(self, query: str) -> list[Citation]:
        """
        执行一次搜索，返回引用列表。

        参数：
          query: 搜索关键词
        返回：
          list[Citation]，每条包含标题、链接、摘要；
          搜索失败时返回空列表（不抛异常，让 Agent 循环能继续往下走）
        """
        logger.info("  [搜索] %s", query)

        try:
            # Tavily 的 search 方法返回一个 dict，结构大致为：
            #   {"results": [{"title": ..., "url": ..., "content": ...}, ...]}
            response = self._client.search(
                query=query,
                max_results=self.max_results,
                search_depth="basic",  # basic 更快更省额度，advanced 更全但慢
            )
        except Exception as exc:
            # 网络抖动、额度用尽、Key 失效等都可能抛异常。
            # 这里"吞掉"异常并返回空列表，是为了让 ReAct 循环不至于因为一次搜索失败就整个崩掉。
            logger.warning("  [搜索失败] %s", exc)
            return []

        citations: list[Citation] = []
        for item in response.get("results", []):
            citations.append(
                Citation(
                    title=item.get("title", "") or "(无标题)",
                    url=item.get("url", "") or "",
                    summary=(item.get("content", "") or "")[:300],  # 摘要截断，避免过长
                )
            )

        logger.info("  [搜索] 命中 %d 条结果", len(citations))
        return citations
