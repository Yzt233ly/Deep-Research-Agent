"""LangGraph 单题研究图：步骤二学习路由，步骤三接回工具与反思。

对照 researcher.py 的 _run_react：条件边替代 if，回边替代 for。
"""
from collections.abc import Callable
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from src.models import AgentAction, ReflectionResult, ResearchNote
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResearchState(TypedDict):
    question: str
    action: AgentAction | None
    observations: list[str]
    iteration: int
    answer: str
    local_notes: list[ResearchNote]
    reflection: ReflectionResult | None


def initial_state(question: str) -> ResearchState:
    if not question.strip():
        raise ValueError("子问题不能为空")
    return {
        "question": question.strip(), "action": None,
        "observations": [], "iteration": 0, "answer": "",
        "local_notes": [], "reflection": None,
    }

#在代码 decide: Callable[[ResearchState], AgentAction] 中，
#它规定了传给 build_research_graph 的 decide 参数必须是一个满足特定“输入和输出类型”的函数。
def build_research_graph(
    decide: Callable[[ResearchState], AgentAction],
    search: Callable[[str], str | tuple[str, list[ResearchNote]]],
    max_iterations: int = 3,
    *,
    agent=None,
):
    """传入普通函数，图负责调度；agent 为步骤三提供已有业务方法。

    函数内定义节点，让节点能使用外层传入的依赖，这叫闭包。
    依赖不放进 State；State 只记录当前研究的数据。
    """
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("max_iterations 必须是正整数")

    def think(state: ResearchState) -> dict:
        action = decide(state)
        logger.info("  [第 %d 步] Thought: %s", state["iteration"] + 1, action.thought)
        return {"action": action, "iteration": state["iteration"] + 1}

    def route_action(state: ResearchState) -> Literal["search", "finish"]:
        # 路由只读动作、选择路线，不执行搜索或更新状态。
        return state["action"].action
    # Literal 是类型提示；实际动作校验来自 AgentAction 的 Pydantic 模型。
    def collect(state: ResearchState) -> dict:
        query = state["action"].search_query or state["question"]
        # search_query 是对象字段，不是方法，也不是字段的 description。
        logger.info("  [第 %d 步] Action: search(%s)", state["iteration"], query)
        result = search(query)
        # 步骤二返回文本；旧 _web_search 同时返回观察文本与提取出的事实。
        observation, notes = (result, []) if isinstance(result, str) else result
        logger.info("  [第 %d 步] Observation:\n%s", state["iteration"], observation)
        
        # 默认更新是覆盖，所以返回包含历史记录的新列表，而非只返回新一条。
        context = f"搜索「{query}」的结果：\n{observation}" if agent is not None else observation
        return {
            "observations": [*state["observations"], context],
            "local_notes": [*state["local_notes"], *notes],
        }

    def reflect(state: ResearchState) -> dict:
        reflection = agent.reflector.reflect(state["question"], state["local_notes"])
        logger.info("  [第 %d 步] 反思：%s（%s）", state["iteration"],
                    "资料已足够" if reflection.is_sufficient else "资料仍不足", reflection.reason)
        if reflection.is_sufficient:
            return {"reflection": reflection}
        advice = f"（自评：资料仍不足——{reflection.missing}）"
        if reflection.suggested_query:
            advice += f" 建议下一步搜索：{reflection.suggested_query}"
        return {"reflection": reflection, "observations": [*state["observations"], advice]}

    def route_after_reflection(state: ResearchState) -> Literal["answer_from_notes", "think", "force_answer"]:
        # 即使是最后一轮，资料足够也优先基于事实作答。
        if state["reflection"].is_sufficient:
            return "answer_from_notes"
        return route_after_search(state)

    def answer_from_notes(state: ResearchState) -> dict:
        return {"answer": agent._answer_from_notes(state["question"], state["local_notes"])}

    def route_after_search(state: ResearchState) -> Literal["think", "force_answer"]:
        # 与旧 for 一致：最后一轮仍允许搜索，随后收尾，不再多做一次决策。
        return "force_answer" if state["iteration"] >= max_iterations else "think"

    def finish(state: ResearchState) -> dict:
        logger.info("  [第 %d 步] Action: finish（信息已足够，结束）", state["iteration"])
        return {"answer": state["action"].answer or ""}

    def force_answer(state: ResearchState) -> dict:
        if agent is not None:
            logger.warning("达到最大循环次数 %d，基于已有信息收尾", max_iterations)
            return {"answer": agent._force_answer(state["question"], state["observations"])}
        # 步骤二只拼接模拟资料，步骤三再接回已有的答案生成能力。
        return {"answer": "达到轮数上限，基于已有模拟资料收尾：\n" + "\n".join(state["observations"])}

    builder = StateGraph(ResearchState)
    builder.add_node("think", think)
    builder.add_node("search", collect)
    builder.add_node("finish", finish)
    builder.add_node("force_answer", force_answer)
    builder.add_edge(START, "think")
    builder.add_conditional_edges("think", route_action, {"search": "search", "finish": "finish"})
    if agent is None:
        # 保留步骤二的最小演示；真实单题入口始终包含反思节点。
        builder.add_conditional_edges("search", route_after_search, {"think": "think", "force_answer": "force_answer"})
    else:
        builder.add_node("reflect", reflect)
        builder.add_node("answer_from_notes", answer_from_notes)
        builder.add_edge("search", "reflect")
        builder.add_conditional_edges("reflect", route_after_reflection, {
            "answer_from_notes": "answer_from_notes", "think": "think", "force_answer": "force_answer",
        })
        builder.add_edge("answer_from_notes", END)
    builder.add_edge("finish", END)
    builder.add_edge("force_answer", END)
    # 一轮最多经过 think 和 search 两个节点，另留收尾余量。
    # recursion_limit 是框架执行预算；业务轮数由上面的条件边控制。
    nodes_per_round = 3 if agent is not None else 2
    return builder.compile().with_config({"recursion_limit": nodes_per_round * max_iterations + 3})


def build_agent_graph(agent):
    """复用旧 Agent 的业务方法，但不调用其 _run_react 循环。

    传入真实 ResearchAgent 就使用真实配置；传入装配 Fake 的 Agent 可离线调试。
    本步骤来源暂由 agent.registry 保存，步骤四迁移全局来源状态。
    一个 agent 对应一次研究，不要跨独立任务复用其来源登记处。
    """
    from src.agent.researcher import REACT_SYSTEM_PROMPT

    def decide(state: ResearchState) -> AgentAction:
        prompt = agent._build_react_prompt(state["question"], state["observations"])
        return agent.llm.generate_structured(prompt, AgentAction, system=REACT_SYSTEM_PROMPT)

    return build_research_graph(decide, agent._web_search, agent.max_iterations, agent=agent)
