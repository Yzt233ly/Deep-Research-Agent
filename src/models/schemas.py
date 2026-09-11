"""
Pydantic 数据模型（步骤 3 + 步骤 4）

作用：定义整个 Agent 用到的"数据结构"。

Pydantic 是一个数据校验库：你定义一个类，它负责：
  1. 校验数据是否符合类型（比如 priority 必须是 int）
  2. 提供类型提示和 IDE 自动补全
  3. 方便地序列化成 JSON / 从 JSON 还原成对象

为什么 Agent 需要这些模型？
  Agent 要让 LLM 输出"研究计划""子问题""引用"等内容。
  如果 LLM 输出的是自由文本，代码很难可靠地处理；
  有了这些模型，LLM 就能输出"符合固定结构"的数据，代码直接拿到对象使用。

关键点：Field(description=...) 里的 description 会传给 LLM，
  告诉它每个字段应该填什么，这是"结构化输出"能成功的关键。
"""
from typing import Literal

from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    """一个待研究的子问题。"""
    question: str = Field(description="需要研究的子问题内容")
    priority: int = Field(description="优先级，1-5，数字越大越重要")


class ResearchPlan(BaseModel):
    """研究计划：把一个宽泛主题拆解成若干子问题。"""
    sub_questions: list[SubQuestion] = Field(description="拆解出的子问题列表")
    overall_approach: str = Field(description="整体研究思路的一句话说明")


class SearchQuery(BaseModel):
    """一次搜索要用的查询。"""
    query: str = Field(description="用于搜索的关键词")
    intent: str = Field(description="这次搜索想搞清楚什么")


class Citation(BaseModel):
    """一条引用来源。"""
    title: str = Field(description="来源标题")
    url: str = Field(description="来源链接")
    summary: str = Field(description="来源内容的一两句话摘要")


class ResearchNote(BaseModel):
    """一条研究笔记：从某篇资料里提取出的关键事实。"""
    fact: str = Field(description="关键事实")
    source_url: str = Field(description="这条事实来自哪个链接")


class AgentAction(BaseModel):
    """
    ReAct 循环中，Agent 每一步的"思考 + 决策"（步骤 4 新增）。

    这是 ReAct 的核心数据结构：每一步让 LLM 同时输出
      - thought（思考）：下一步该做什么、为什么
      - action（行动）：具体执行哪个动作

    用 Literal 限定 action 只能是 "search" 或 "finish" 两个值之一：
      这样 LLM 的输出就被约束在可控范围内，代码能可靠地用 if/else 判断分支。
    """
    thought: str = Field(description="思考：基于当前已有信息，说明下一步该做什么、为什么")
    action: Literal["search", "finish"] = Field(
        description="动作类型：search=继续搜索更多信息，finish=信息已足够，结束并给出答案"
    )
    search_query: str | None = Field(
        default=None, description="搜索关键词，仅当 action='search' 时填写"
    )
    answer: str | None = Field(
        default=None, description="对该子问题的最终回答，仅当 action='finish' 时填写"
    )


class ExtractedFacts(BaseModel):
    """
    从一篇资料中压缩提取出的关键事实（步骤 6 新增）。

    为什么需要它？（这就是"上下文压缩"）
      一篇网页正文可能有几千字，如果每轮都把它整段塞进 prompt，
      上下文会越来越长，导致：变慢、变贵、模型抓不住重点。
      所以先让 LLM 把正文"读薄"成 3~5 条关键事实，只保留事实，丢掉废话。

    注意字段类型是 list[str]（纯字符串），不是 list[ResearchNote]。
    原因：source_url 由程序在压缩后补充，不让 LLM 填写，
      避免 LLM 篡改或编造链接（和步骤 5 的教训一致：真实性交给程序保证）。
    """
    facts: list[str] = Field(description="从资料中提取出的 3~5 条关键事实，每条一句话")


class ReflectionResult(BaseModel):
    """
    反思结果：Agent 对自己"资料够不够"的自我评估（步骤 6 新增）。

    这就是 Reflection（反思）模式：
      普通 Agent 只会"一直搜到循环次数上限"或者"LLM 自己说够了"。
      加了反思后，Agent 会显式地自问："现有资料能回答子问题了吗？还缺什么？"
      从而更早停止、或在资料不足时给出更精准的下一步搜索词。
    """
    is_sufficient: bool = Field(description="现有资料是否已足以回答子问题")
    reason: str = Field(description="做出该判断的一句话理由")
    missing: str = Field(description="若资料不足，说明还缺少什么信息；若已足够，填「无」")
    suggested_query: str | None = Field(
        default=None, description="若资料不足，建议下一步使用的搜索关键词"
    )
