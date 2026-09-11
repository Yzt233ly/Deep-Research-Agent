"""验证表格校验、下载来源及日志隔离，不需要 Streamlit 服务。"""
import logging
from threading import Thread

import pytest

from src.models import Citation
from src.ui.support import capture_logs, plan_from_rows, report_markdown
from src.utils.logger import get_logger


@pytest.mark.parametrize("rows", [[], [{"question": " ", "priority": 2}],
    [{"question": "问题", "priority": None}], [{"question": "问题", "priority": 2.5}],
    [{"question": "问题", "priority": 6}], [{"question": "问题", "priority": True}]])
def test_editor_rejects_invalid_rows(rows):
    with pytest.raises(ValueError):
        plan_from_rows(rows, "思路")


def test_editor_accepts_added_rows_and_integer_float():
    plan = plan_from_rows([{"question": " 新问题 ", "priority": 3.0}], " 新思路 ")
    assert plan.sub_questions[0].question == "新问题"
    assert plan.sub_questions[0].priority == 3
    assert plan.overall_approach == "新思路"


def test_download_contains_registered_references():
    text = report_markdown({"report": "结论 [1]", "sources": [
        Citation(title="真实来源", url="https://example.com", summary="摘要")]})
    assert "结论 [1]" in text
    assert "[1] 真实来源 — https://example.com" in text


def test_logs_are_isolated_and_handlers_cleaned_after_failure():
    logger = get_logger("src.ui.test")
    handlers = list(logger.handlers)
    lines, renders = [], []
    with pytest.raises(RuntimeError):
        with capture_logs(lines, renders.append):
            logger.info("当前会话")
            other = Thread(target=lambda: logger.info("另一个会话"))
            other.start()
            other.join()
            raise RuntimeError("失败")
    assert len(lines) == 1
    assert "当前会话" in lines[0]
    assert renders
    assert logger.handlers == handlers
