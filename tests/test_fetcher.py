"""
网页抓取工具（WebFetcher）的单元测试（步骤 5）

测试重点：
  1. 能否从 HTML 里提取出正文
  2. 是否剔除 <script> 等噪声标签
  3. 网络出错时能否优雅返回空字符串（而不是抛异常）

用 patch 替换掉 requests.get，测试就不需要真的联网。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.tools import WebFetcher


def _make_response(html: str) -> MagicMock:
    """构造一个假的 requests 响应对象。"""
    response = MagicMock()
    response.text = html
    response.apparent_encoding = "utf-8"
    response.raise_for_status.return_value = None  # 模拟"状态码正常"
    return response


def test_fetch_extracts_visible_text_and_drops_scripts():
    """正文应被提取，<script> 内容应被剔除。"""
    html = """
    <html><body>
        <script>console.log('这段不该出现')</script>
        <nav>导航栏也不该出现</nav>
        <p>这是网页的正文内容。</p>
    </body></html>
    """
    with patch("src.tools.fetcher.requests.get", return_value=_make_response(html)):
        text = WebFetcher().fetch("https://example.com")

    assert "这是网页的正文内容。" in text
    assert "这段不该出现" not in text   # script 被剔除
    assert "导航栏也不该出现" not in text  # nav 被剔除


def test_fetch_returns_empty_string_on_network_error():
    """网络异常时应优雅返回空字符串，不抛异常。"""
    with patch("src.tools.fetcher.requests.get", side_effect=Exception("网络炸了")):
        assert WebFetcher().fetch("https://example.com") == ""


def test_fetch_returns_empty_string_for_empty_url():
    """空 URL 直接返回空字符串，不应该发起请求。"""
    with patch("src.tools.fetcher.requests.get") as mock_get:
        assert WebFetcher().fetch("") == ""
        mock_get.assert_not_called()


def test_fetch_truncates_long_text():
    """超长正文应按 max_chars 截断。"""
    long_html = f"<html><body><p>{'啊' * 5000}</p></body></html>"
    with patch("src.tools.fetcher.requests.get", return_value=_make_response(long_html)):
        text = WebFetcher(max_chars=100).fetch("https://example.com")

    assert len(text) == 100


@pytest.mark.parametrize("bad_url", ["https://404.com", "https://403.com"])
def test_fetch_returns_empty_when_status_code_error(bad_url):
    """HTTP 状态码异常（404/403）时应返回空字符串。"""
    response = _make_response("<html></html>")
    response.raise_for_status.side_effect = Exception("404 Not Found")
    with patch("src.tools.fetcher.requests.get", return_value=response):
        assert WebFetcher().fetch(bad_url) == ""
