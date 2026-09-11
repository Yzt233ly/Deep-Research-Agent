"""
上下文压缩器（步骤 6）

作用：把一篇很长的网页正文，"读薄"成 3~5 条关键事实。

为什么需要压缩？（这是 Agent 工程里非常重要的一环）
  回想步骤 5：Agent 每轮搜索都会抓到网页正文（最多 1500 字），
  然后把这些正文塞进下一轮的 prompt。问题在于：
    - 一个子问题可能搜 3~5 轮 → prompt 里堆了几千字
    - 多个网页内容互相重复、夹带大量无关信息
    - 结果就是：上下文（context）越来越长 → 变慢、变贵、模型反而抓不住重点

  解决思路就是"压缩"：
    抓到的正文不直接塞进 prompt，而是先让 LLM 提炼成几条关键事实，
    之后只带"事实"进入下一轮。这样上下文又短又精。

关键设计：source_url 由程序补充，不让 LLM 填
  和步骤 5 的教训一致——链接的真实性由程序保证，LLM 只负责"提炼内容"。
  这样就不会出现 LLM 篡改/编造来源链接的情况。
"""
from src.llm.client import LLMClient
from src.models import ExtractedFacts, ResearchNote
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 提炼事实时给 LLM 的角色设定
COMPRESS_SYSTEM_PROMPT = (
    "你是一名资料提炼助手。请从给定的资料中，提取出 3~5 条最关键的事实。"
    "要求：每条一句话、信息密度高、忠于原文、不要加入原文没有的内容。"
    "如果资料内容空洞或与主题无关，就少提甚至不提。"
)


class ContextCompressor:
    """上下文压缩器：长文本 → 若干条关键事实（ResearchNote）。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    def compress(self, text: str, source_url: str) -> list[ResearchNote]:
        """
        把一段资料压缩成关键事实列表。

        参数：
          text: 待压缩的原始资料（网页正文或搜索摘要）
          source_url: 这段资料来自哪个链接（由程序写入每条笔记，不由 LLM 填）
        返回：
          list[ResearchNote]；资料为空或压缩失败时返回空列表
        """
        if not text or not text.strip():
            return []

        try:
            result = self.llm.generate_structured(
                f"请从下面的资料中提取 3~5 条关键事实：\n\n{text}",
                ExtractedFacts,
                system=COMPRESS_SYSTEM_PROMPT,
            )
        except Exception as exc:
            # 压缩失败不应该让整个研究流程崩掉：
            # 退化为"不压缩"，直接把原文截断当作一条事实使用。
            logger.warning("  [压缩失败] 退化为原文截断（%s）", exc)
            return [ResearchNote(fact=text[:300], source_url=source_url)]

        # 把 LLM 给的事实字符串，包装成带来源链接的研究笔记
        notes = [ResearchNote(fact=fact, source_url=source_url) for fact in result.facts if fact.strip()]
        logger.info("  [压缩] %d 字 → %d 条关键事实", len(text), len(notes))
        return notes
