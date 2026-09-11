"""页面的数据转换与日志桥接，单独拆出以便不启动网页也能测试。"""
import logging
import threading
from contextlib import contextmanager
from collections.abc import Callable, Iterator

from src.agent import ResearchAgent
from src.config import get_settings
from src.models import ResearchPlan


def create_agent() -> ResearchAgent:
    """点击生成时才创建客户端；浏览页面不会调用模型。"""
    if not get_settings().openai_api_key.strip():
        raise ValueError("请先在项目 .env 中配置 OPENAI_API_KEY，再重启页面服务")
    return ResearchAgent()


def plan_from_rows(rows: list[dict], approach: str) -> ResearchPlan:
    """把表格数据还原为模型，并在调用收费接口前校验用户输入。"""
    if not rows:
        raise ValueError("请至少保留一个子问题")
    questions = []
    for index, row in enumerate(rows, 1):
        question = row.get("question")
        priority = row.get("priority")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"第 {index} 行：子问题不能为空，请填写或删除该行")
        # 编辑器的数值可能是浮点数；允许 3.0，但不把 3.5 静默截断成 3。
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise ValueError(f"第 {index} 行：优先级必须是 1 到 5 的整数")
        if priority not in (1, 2, 3, 4, 5):
            raise ValueError(f"第 {index} 行：优先级必须是 1 到 5 的整数")
        questions.append({"question": question.strip(), "priority": int(priority)})
    if not approach.strip():
        raise ValueError("请填写整体研究思路")
    return ResearchPlan(sub_questions=questions, overall_approach=approach.strip())


def report_markdown(result: dict) -> str:
    """参考文献由实际登记结果拼接，下载内容与页面报告一致。"""
    references = "\n".join(
        f"[{i}] {source.title} — {source.url}"
        for i, source in enumerate(result["sources"], 1)
    )
    return result.get("report", "") + "\n\n## 参考文献\n\n" + (references or "本次没有外部来源。")


def safe_error(exc: Exception) -> str:
    """错误可见，但不把配置中的 API Key 暴露在页面或日志里。"""
    message = str(exc)
    settings = get_settings()
    for secret in (settings.openai_api_key, settings.tavily_api_key):
        if secret:
            message = message.replace(secret, "[已隐藏]")
    return message


@contextmanager
def capture_logs(lines: list[str], render: Callable[[str], None]) -> Iterator[None]:
    """只收集本次同步执行的日志；无论成功失败都移除 handler。"""
    owner = threading.get_ident()

    class PageHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Streamlit 各会话在不同线程执行。不能将全局日志直接发往某个页面。
            if record.thread != owner:
                return
            lines.append(safe_error(Exception(self.format(record))))
            del lines[:-1000]
            render("\n".join(lines))

    handler = PageHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    # 项目 logger 关闭了 propagate，挂在 root 上收不到，需要逐个挂。
    loggers = [value for name, value in list(logging.Logger.manager.loggerDict.items())
               if name.startswith("src.") and isinstance(value, logging.Logger)]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()
