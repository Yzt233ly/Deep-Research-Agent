"""
网页正文抓取工具（步骤 5）

作用：给一个网址，把网页的"正文文字"提取出来。

为什么需要它？
  搜索引擎返回的往往只是一两句话的摘要，信息量有限。
  如果 Agent 只能看到摘要，最后写出的报告就会很肤浅。
  抓取正文能让 Agent 读到更完整的信息，报告质量会明显提升。

实现思路（三步）：
  1. requests 发 HTTP 请求，拿到网页的 HTML 源码
  2. BeautifulSoup 解析 HTML，去掉脚本/样式/导航等"噪声标签"
  3. 提取纯文本，并截断到指定长度（防止上下文爆炸、也防止拖慢速度）

注意：这是"简化版"的正文提取。
  生产级方案常用 trafilatura 这类专门库，提取效果更好但依赖更重。
  这里用 requests + BeautifulSoup，更适合新手理解"网页抓取"的完整过程。
"""
import requests
from bs4 import BeautifulSoup

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 有些网站会拒绝"没有浏览器标识"的请求，伪装成浏览器能提高成功率
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# 这些标签里的内容通常是"噪声"（导航、广告、脚本），不是正文，需要剔除
_NOISE_TAGS = ["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]


class WebFetcher:
    """抓取网页并提取正文文字。"""

    def __init__(self, timeout: int | None = None, max_chars: int | None = None) -> None:
        settings = get_settings()
        self.timeout = timeout or settings.fetch_timeout
        self.max_chars = max_chars or settings.fetch_max_chars

    def fetch(self, url: str) -> str:
        """
        抓取指定网址的正文。

        参数：
          url: 网页地址
        返回：
          正文纯文本（已截断到 max_chars）；失败时返回空字符串
        """
        if not url:
            return ""

        try:
            response = requests.get(url, headers=_HEADERS, timeout=self.timeout)
            # raise_for_status：如果状态码是 4xx/5xx（如 404、403），抛出异常
            response.raise_for_status()
        except Exception as exc:
            # 很多网站有反爬机制，抓取失败是"常态"而不是"异常"，
            # 所以这里只记一条警告日志，返回空字符串，不影响整体流程。
            logger.debug("  [抓取失败] %s（%s）", url, exc)
            return ""

        try:
            # 中文网页常见编码问题是乱码，用 apparent_encoding 让 requests 自动猜编码
            response.encoding = response.apparent_encoding or response.encoding

            soup = BeautifulSoup(response.text, "html.parser")

            # 先删掉噪声标签（decompose 会把这个标签及其子内容从树里移除）
            for tag in soup(_NOISE_TAGS):
                tag.decompose()

            # get_text(separator="\n") 把 HTML 标签之间的文字用换行拼起来
            text = soup.get_text(separator="\n")

            # 逐行去掉空白，并丢掉空行（HTML 里常有大量缩进空白）
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = "\n".join(lines)

            # 截断，防止一篇超长网页把 LLM 的上下文窗口撑爆
            return text[: self.max_chars]
        except Exception as exc:
            logger.debug("  [解析失败] %s（%s）", url, exc)
            return ""
