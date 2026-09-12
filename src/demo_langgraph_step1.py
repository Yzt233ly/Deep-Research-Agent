"""LangGraph 学习步骤 1：两个普通函数组成一张图，不调用模型或网络。

运行：python -m src.demo_langgraph_step1
改主题：python -m src.demo_langgraph_step1 "  智能客服  "
"""
import sys
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.utils.logger import get_logger

logger = get_logger(__name__)


# State（状态）就是节点之间传递的工作记录。
# TypedDict 描述字典有哪些键及其类型，方便理解和检查代码；
# 它不是 Pydantic，不会自动执行运行时校验或补充默认值。
class LearningState(TypedDict):
    topic: str
    summary: str


def prepare_topic(state: LearningState) -> dict[str, str]:
    """节点一：去掉主题前后的空白，只返回 topic 的更新。"""
    logger.info("① prepare_topic 读到：%s", state)
    # 不直接修改 state，而是把更新交给图处理。
    # summary 没出现在返回值里，表示保留原值，不表示删除。
    update = {"topic": state["topic"].strip()}
    logger.info("① prepare_topic 返回：%s", update)
    return update


def write_summary(state: LearningState) -> dict[str, str]:
    """节点二：用固定文字生成结论，便于专注观察图的机制。"""
    logger.info("② write_summary 读到：%s", state)
    update = {"summary": f"关于「{state['topic']}」：这是固定的教学结论，没有调用模型。"}
    logger.info("② write_summary 返回：%s", update)
    return update


def build_graph():
    """注册节点、连接路线，再编译成可以执行的图。"""
    builder = StateGraph(LearningState)
    # 传入函数本身，不写 prepare_topic()；现在注册，运行时才调用。
    builder.add_node("prepare_topic", prepare_topic)
    builder.add_node("write_summary", write_summary)

    # START / END 是框架提供的起止标记，不是需要自己实现的函数。
    # 节点的注册顺序不负责调度，真正的执行顺序由边决定。
    builder.add_edge(START, "prepare_topic")
    builder.add_edge("prepare_topic", "write_summary")
    builder.add_edge("write_summary", END)

    # compile 组装并检查图；这时两个节点还没有执行。
    return builder.compile()

# 当你运行 Python 文件时，操作系统会将你在终端输入的这一串命令按空格切分，按顺序放进 sys.argv 这个列表中：
# sys.argv[0]：永远是当前 Python 脚本自身的名称或路径。
# sys.argv[1]：用户传给脚本的第 1 个外部参数。
# sys.argv[2]：用户传给脚本的第 2 个外部参数（以此类推）。
def main() -> None:
    graph = build_graph()
    logger.info("图已编译，节点尚未执行；接下来调用 invoke。")
    topic = sys.argv[1] if len(sys.argv) > 1 else "  RAG 检索增强生成  "
    initial_state: LearningState = {"topic": topic, "summary": "尚未生成结论"}
    # invoke 才会沿着边依次执行节点，并返回最终状态。
    # graph 变量能够使用 .invoke() 方法，是因为它的类型并不是普通的 Python 对象，
    # 而是已经通过 builder.compile() 编译出来的 LangGraph 图实例（类型通常为 CompiledStateGraph）。
    result = graph.invoke(initial_state)
    logger.info("最终状态：%s", result)


if __name__ == "__main__":
    main()
