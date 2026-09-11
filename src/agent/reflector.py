"""
反思器（步骤 6）

作用：让 Agent 显式地"自我评估"——现有资料够不够回答当前子问题？

什么是 Reflection（反思）？
  普通 Agent 的循环只有一个终止条件："LLM 说够了"或"达到最大次数"。
  这样容易出现两种浪费：
    - 资料其实已经够了，却还在继续搜（浪费时间和钱）
    - 资料明显不够，却草草收尾（报告质量差）

  反思就是让 Agent 在每轮搜索后，额外做一次"自我检查"：
    1. 现有事实能回答子问题了吗？（is_sufficient）
    2. 如果不够，还缺什么？（missing）
    3. 下一步该搜什么关键词？（suggested_query）

  这样一来：
    - 资料够了 → 立刻停止搜索，生成答案（省钱、省时间）
    - 资料不够 → 带着"缺什么、搜什么"的明确指引进入下一轮（更有的放矢）

这在学术界叫 Reflexion（自我反思），是提升 Agent 可靠性的常用手段。
"""
from src.llm.client import LLMClient
from src.models import ReflectionResult, ResearchNote
from src.utils.logger import get_logger

logger = get_logger(__name__)

REFLECT_SYSTEM_PROMPT = (
    "你是一名严谨的研究审核员。请评估“目前已收集到的事实”是否足以回答给定子问题。"
    "判断标准要务实：如果关键要素都已覆盖，就判为足够；"
    "如果还缺关键信息，就指出缺什么，并给出一个更精准的搜索关键词。"
)


class Reflector:
    """反思器：评估资料是否充足，并给出下一步建议。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    def reflect(self, question: str, notes: list[ResearchNote]) -> ReflectionResult:
        """
        对"当前资料能否回答子问题"做一次自我评估。

        参数：
          question: 当前研究的子问题
          notes: 目前已收集到的关键事实
        返回：
          ReflectionResult（是否足够 / 理由 / 缺什么 / 建议搜索词）
        """
        # 一条资料都没有时，不用浪费一次 LLM 调用，直接判定"不足"
        if not notes:
            return ReflectionResult(
                is_sufficient=False,
                reason="目前还没有收集到任何资料",
                missing="全部关键信息",
                suggested_query=question,
            )

        facts_text = "\n".join(f"- {note.fact}" for note in notes)

        try:
            result = self.llm.generate_structured(
                f"子问题：{question}\n\n目前已收集到的事实：\n{facts_text}\n\n请评估资料是否足够。",
                ReflectionResult,
                system=REFLECT_SYSTEM_PROMPT,
            )
        except Exception as exc:
            # 反思本身失败时，不应该阻断主流程：
            # 保守地认为"资料不足"，让 ReAct 循环按原逻辑继续（最多到循环上限）。
            logger.warning("  [反思失败] 保守判定为资料不足（%s）", exc)
            return ReflectionResult(
                is_sufficient=False,
                reason="反思环节调用失败，保守认为资料不足",
                missing="未知",
                suggested_query=None,
            )

        return result
