"""人工确认边界的回归测试：全程使用假对象，不调用模型或网络。"""
import pytest

from src.agent import ResearchAgent
from src.models import ResearchPlan, SubQuestion
from tests.helpers import FakeFetcher, FakeLLMClient, FakeSearchTool


def build_agent():
    llm, search = FakeLLMClient(), FakeSearchTool()
    return ResearchAgent(llm, search, FakeFetcher()), llm, search


def test_planning_does_not_start_research():
    agent, llm, search = build_agent()
    plan = agent.make_plan("主题")
    assert plan.sub_questions
    assert llm.structured_schemas == [ResearchPlan]
    assert not llm.chat_prompts
    assert not search.queries


def test_approved_plan_is_used_without_replanning():
    agent, llm, _ = build_agent()
    plan = ResearchPlan(overall_approach="先比较实际应用", sub_questions=[
        SubQuestion(question="低优先级", priority=1),
        SubQuestion(question="人工补充", priority=5),
    ])
    result = agent.research_from_plan("主题", plan)
    assert [q for q, _ in result["answers"]] == ["人工补充", "低优先级"]
    assert ResearchPlan not in llm.structured_schemas
    assert "先比较实际应用" in llm.chat_prompts[-1]
    assert plan.sub_questions[0].question == "低优先级"


@pytest.mark.parametrize("questions", [[], [SubQuestion(question="  ", priority=1)],
    [SubQuestion(question="问题", priority=6)]])
def test_invalid_plan_is_rejected_before_calls(questions):
    agent, llm, search = build_agent()
    with pytest.raises(ValueError):
        agent.research_from_plan("主题", ResearchPlan(sub_questions=questions, overall_approach="思路"))
    assert not llm.structured_schemas
    assert not search.queries


def test_empty_topic_is_rejected_before_planning():
    agent, llm, _ = build_agent()
    with pytest.raises(ValueError):
        agent.make_plan("  ")
    assert not llm.structured_schemas
