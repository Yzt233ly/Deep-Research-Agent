"""运行：python -m src.demo_langgraph_step2，不调用 API、不联网。"""
from src.agent.graph_researcher import build_research_graph, initial_state
from src.models import AgentAction


def main() -> None:
    for scenario in ("直接结束", "搜索一次后结束", "一直搜索"):
        print(f"\n=== {scenario} ===")

        def decide(state):
            should_finish = scenario == "直接结束" or (
                scenario == "搜索一次后结束" and state["observations"]
            )
            return AgentAction(
                thought="固定教学动作，不是模型推理",
                action="finish" if should_finish else "search",
                answer="固定教学答案" if should_finish else None,
            )

        def search(query):
            return f"【模拟资料】关于「{query}」的固定搜索结果"

        graph = build_research_graph(decide, search, max_iterations=3)
        # updates 逐个显示节点返回的更新，便于亲眼看到回边与分支。
        for update in graph.stream(initial_state("什么是 RAG？"), stream_mode="updates"):
            print(update)


if __name__ == "__main__":
    main()
