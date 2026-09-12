import pytest

from src.agent.graph_researcher import build_research_graph, initial_state
from src.models import AgentAction


@pytest.mark.parametrize(
    "finish_after,limit,expected_searches,expected_decisions",
    [(0, 3, 0, 1), (1, 3, 1, 2), (None, 3, 3, 3), (None, 1, 1, 1), (None, 15, 15, 15)],
)
def test_decision_paths(finish_after, limit, expected_searches, expected_decisions):
    seen_observations = []
    queries = []

    def decide(state):
        seen_observations.append(list(state["observations"]))
        finish = finish_after is not None and state["iteration"] >= finish_after
        return AgentAction(thought="模拟", action="finish" if finish else "search", answer="完成")

    def search(query):
        queries.append(query)
        return f"资料{len(queries)}"

    graph = build_research_graph(decide, search, limit)
    original = initial_state("测试问题")
    result = graph.invoke(original)
    assert queries == ["测试问题"] * expected_searches
    assert result["iteration"] == expected_decisions == len(seen_observations)
    assert result["observations"] == [f"资料{i + 1}" for i in range(expected_searches)]
    assert seen_observations == [[f"资料{i + 1}" for i in range(n)] for n in range(expected_decisions)]
    assert original["observations"] == []
    if finish_after is None:
        assert result["answer"].startswith("达到轮数上限")
        assert f"资料{expected_searches}" in result["answer"]
    else:
        assert result["answer"] == "完成"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_iteration_limit(limit):
    with pytest.raises(ValueError, match="正整数"):
        build_research_graph(lambda state: None, lambda query: "", limit)


def test_empty_question():
    with pytest.raises(ValueError, match="不能为空"):
        initial_state("  ")
