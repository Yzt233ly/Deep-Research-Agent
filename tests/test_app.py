"""用 Streamlit 自带 AppTest 操作页面，模型与搜索均替换为假对象。"""
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.agent import ResearchAgent
from src.models import AgentAction
from tests.helpers import FakeFetcher, FakeLLMClient, FakeSearchTool

APP = Path(__file__).resolve().parents[1] / "app.py"


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_page_requires_confirmation_and_does_not_repeat():
    llm = FakeLLMClient(actions=[AgentAction(thought="开始搜索", action="search", search_query="人工关键词")])
    search = FakeSearchTool()
    agent = ResearchAgent(llm, search, FakeFetcher())
    with patch("src.ui.support.create_agent", return_value=agent):
        at = AppTest.from_file(str(APP)).run()
        assert not at.exception
        assert not llm.structured_schemas
        at.text_input(key="topic_input").set_value("测试主题").run()
        button(at, "生成研究计划").click().run()
        assert not at.exception
        assert not search.queries
        assert len(llm.structured_schemas) == 1
        at.run()
        assert len(llm.structured_schemas) == 1
        at.text_area[0].set_value("人工改过的整体思路")
        button(at, "确认并开始研究").click().run()
        assert not at.exception
        assert at.session_state["result"] is not None
        assert search.queries == ["人工关键词"]
        assert "人工改过的整体思路" in llm.chat_prompts[-1]
        calls = len(llm.structured_schemas), len(llm.chat_prompts)
        at.run()
        assert calls == (len(llm.structured_schemas), len(llm.chat_prompts))
        assert button(at, "确认并开始研究").disabled
        at.text_input(key="topic_input").set_value("新主题").run()
        assert at.session_state["plan"] is None
        assert at.session_state["result"] is None


def test_blank_topic_never_creates_client():
    with patch("src.ui.support.create_agent") as factory:
        at = AppTest.from_file(str(APP)).run()
        button(at, "生成研究计划").click().run()
        assert at.error
        factory.assert_not_called()


def test_execution_error_keeps_plan_for_retry():
    agent = ResearchAgent(FakeLLMClient(), FakeSearchTool(), FakeFetcher())
    with patch("src.ui.support.create_agent", return_value=agent), patch.object(
        agent, "research_from_plan", side_effect=RuntimeError("模拟失败")
    ):
        at = AppTest.from_file(str(APP)).run()
        at.text_input(key="topic_input").set_value("主题").run()
        button(at, "生成研究计划").click().run()
        button(at, "确认并开始研究").click().run()
        assert not at.exception
        assert at.error
        assert at.session_state["plan"] is not None
        assert at.session_state["result"] is None
        assert at.session_state["stage"] == "review"


def test_table_add_delete_edit_are_used_by_research():
    agent = ResearchAgent(FakeLLMClient(), FakeSearchTool(), FakeFetcher())
    with patch("src.ui.support.create_agent", return_value=agent):
        at = AppTest.from_file(str(APP)).run()
        at.text_input(key="topic_input").set_value("主题").run()
        button(at, "生成研究计划").click().run()
        # AppTest 尚无 data_editor 的高级操作接口，提交与浏览器相同的编辑差量。
        key = f"plan_editor_{at.session_state['plan_version']}"
        at.session_state[key] = {"edited_rows": {}, "deleted_rows": [0],
                                 "added_rows": [{"question": "人工新增问题", "priority": 4}]}
        button(at, "确认并开始研究").click().run()
        assert not at.exception
        assert [q for q, _ in at.session_state["result"]["answers"]] == ["人工新增问题"]
