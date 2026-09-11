"""
搜索工具（WebSearchTool）的单元测试（步骤 5）

测试重点：
  1. 能否把 Tavily 的返回结果，正确转换成 Citation 列表
  2. 没有 API Key 时是否明确报错
  3. 搜索出错时是否优雅返回空列表（而不是抛异常）

用 patch 替换掉 TavilyClient，测试就不需要真的调 API、也不消耗额度。
"""
from unittest.mock import patch

import pytest

from src.tools import WebSearchTool


def test_search_maps_results_to_citations():
    """Tavily 返回的每条结果，应被转换成 Citation。"""
    fake_response = {
        "results": [
            {"title": "标题1", "url": "https://a.com", "content": "内容1"},
            {"title": "标题2", "url": "https://b.com", "content": "内容2"},
        ]
    }
    with patch("src.tools.search.TavilyClient") as mock_client_class:
        mock_client_class.return_value.search.return_value = fake_response
        tool = WebSearchTool(api_key="fake-key")
        citations = tool.search("测试查询")

    assert len(citations) == 2
    assert citations[0].title == "标题1"
    assert citations[0].url == "https://a.com"
    assert citations[1].summary == "内容2"


def test_search_returns_empty_list_on_error():
    """搜索抛异常时应返回空列表，不向上抛。"""
    with patch("src.tools.search.TavilyClient") as mock_client_class:
        mock_client_class.return_value.search.side_effect = Exception("鉴权失败")
        tool = WebSearchTool(api_key="fake-key")
        assert tool.search("测试查询") == []


def test_missing_api_key_raises_value_error():
    """显式传入空 Key 时，应该直接报错（提示用户去配置）。"""
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        WebSearchTool(api_key="")


def test_search_handles_missing_fields_gracefully():
    """Tavily 返回的字段缺失时，应使用默认值而不是崩溃。"""
    fake_response = {"results": [{"content": "只有内容"}]}
    with patch("src.tools.search.TavilyClient") as mock_client_class:
        mock_client_class.return_value.search.return_value = fake_response
        tool = WebSearchTool(api_key="fake-key")
        citations = tool.search("测试查询")

    assert len(citations) == 1
    assert citations[0].title == "(无标题)"
    assert citations[0].url == ""


def test_search_respects_max_results_argument():
    """max_results 参数应被正确传给底层客户端。"""
    with patch("src.tools.search.TavilyClient") as mock_client_class:
        mock_client_class.return_value.search.return_value = {"results": []}
        tool = WebSearchTool(api_key="fake-key", max_results=3)
        tool.search("测试查询")

        # 检查底层调用时确实传了 max_results=3
        _, kwargs = mock_client_class.return_value.search.call_args
        assert kwargs["max_results"] == 3
