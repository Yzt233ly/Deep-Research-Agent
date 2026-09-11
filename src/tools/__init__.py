# tools 包：Agent 可调用的"工具"（步骤 5）
# 通过 __init__.py 统一导出，让外部能简洁地导入：
#   from src.tools import WebSearchTool, WebFetcher, SourceRegistry
from src.tools.fetcher import WebFetcher
from src.tools.mock_search import MockSearchTool
from src.tools.search import WebSearchTool
from src.tools.sources import SourceRegistry

__all__ = [
    "WebSearchTool",
    "WebFetcher",
    "SourceRegistry",
    "MockSearchTool",
]
