"""
LLM 调用封装模块（步骤 2）

作用：把"调用大模型"这件事封装成一个类 LLMClient，好处是：
  1. 统一入口：以后所有地方都通过它调模型，不直接裸调 API
  2. 自动重试：网络抖动、限流等临时错误会自动重试，避免程序一抖就崩
  3. 成本统计：每次调用记录输入/输出 token 和费用，心里有数
"""
from typing import TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 泛型类型变量：T 代表"任意一个 Pydantic 模型类型"。
# 用它可以让 generate_structured 的返回值类型和传入的 schema 保持一致：
#   传入 ResearchPlan 就返回 ResearchPlan，IDE 能给出正确的属性补全。
T = TypeVar("T", bound=BaseModel)


def _log_before_retry(retry_state) -> None:
    """
    重试前的回调函数：打印一条中文日志，让你直观看到重试过程。

    注意：这个函数必须定义在 LLMClient 之前！
    因为 @retry(before_sleep=_log_before_retry) 这个装饰器在"定义方法"那一刻就会
    去查找 _log_before_retry，如果它定义在类后面，会报 NameError。

    参数 retry_state 是 tenacity 传进来的状态对象，常用字段：
      attempt_number: 当前是第几次尝试（从 1 开始）
      outcome:        本次尝试的结果（一个 Future，含异常信息）
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "第 %d 次尝试失败，2 秒后进行第 %d 次尝试（错误：%s）",
        retry_state.attempt_number,
        retry_state.attempt_number + 1,
        exc,
    )


class LLMClient:
    """LLM 调用封装类：负责调用模型、失败重试、统计 token 和费用。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings

        # 创建 ChatOpenAI 实例。
        # 为什么用 ChatOpenAI 而不是专门的 DeepSeek 类？
        #   因为 DeepSeek 提供的是"OpenAI 兼容接口"，直接用 ChatOpenAI 配 base_url 即可。
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.0,   # 研究任务需要稳定、可复现，温度设为 0
            timeout=60,        # 单次请求超时 60 秒
            max_retries=0,     # 关闭 OpenAI SDK 自带重试，统一用下面的 tenacity 重试，避免两套重试叠加
        )

        # 累计 token 计数（记录整个运行过程的总消耗）
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    # ==================== 对外方法 ====================

    def chat(self, prompt: str, system: str | None = None) -> str:
        """
        发送一次对话，返回模型回复的文本。

        参数：
          prompt: 用户消息
          system: 可选，系统提示词（用于设定 AI 的角色/行为）
        返回：
          模型回复的字符串
        """
        messages = self._build_messages(prompt, system)
        return self._invoke_with_retry(messages)

    def generate_structured(self, prompt: str, schema: type[T], system: str | None = None) -> T:
        """
        让 LLM 输出符合指定 Pydantic 模型的结构化数据。

        参数：
          prompt: 用户消息
          schema: 一个 Pydantic 模型类（如 ResearchPlan），LLM 会按它的字段结构输出
          system: 可选系统提示词
        返回：
          一个 schema 类型的实例（如 ResearchPlan 对象），可直接用 .字段 访问
        """
        # with_structured_output 是 LangChain 的结构化输出能力：
        #   底层让模型返回符合 schema 的 JSON，再自动解析成 Pydantic 对象。
        # method="function_calling"：用 function calling（tools）方式。
        #   为什么显式指定？因为 LangChain 默认可能用 json_schema（走 response_format），
        #   而 DeepSeek 目前不支持那种 response_format，会报
        #   "This response_format type is unavailable now"。function calling 是 DeepSeek 稳定支持的。
        # include_raw=True：同时返回原始响应（含 token）和解析结果，方便统计与容错。
        structured_llm = self._llm.with_structured_output(
            schema,
            method="function_calling",
            include_raw=True,
        )
        messages = self._build_messages(prompt, system)
        return self._invoke_structured_with_retry(structured_llm, messages, schema)

    def usage_report(self) -> str:
        """返回累计的 token 消耗和费用汇总，方便最后看一眼总成本。"""
        total_cost = self._calc_cost(self.total_input_tokens, self.total_output_tokens)
        return (
            f"累计：输入 {self.total_input_tokens} token，"
            f"输出 {self.total_output_tokens} token，约 ¥{total_cost:.6f}"
        )

    # ==================== 内部方法 ====================

    def _build_messages(self, prompt: str, system: str | None) -> list[BaseMessage]:
        """把用户消息和（可选的）系统消息组装成 LangChain 的消息列表。"""
        messages: list[BaseMessage] = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        return messages

    @retry(
        stop=stop_after_attempt(3),                # 最多尝试 3 次（首次 + 2 次重试）
        wait=wait_fixed(2),                        # 每次重试之间等 2 秒
        retry=retry_if_exception_type(Exception),  # 所有异常都重试（教学简化，见下方说明）
        before_sleep=_log_before_retry,            # 每次重试前打印一条日志
    )
    def _invoke_with_retry(self, messages: list[BaseMessage]) -> str:
        """真正调用模型，并统计本次调用的 token 和费用。"""
        response = self._llm.invoke(messages)

        # 提取本次输入/输出 token 数并累计
        input_tokens, output_tokens = self._extract_usage(response)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # 计算并打印本次费用
        cost = self._calc_cost(input_tokens, output_tokens)
        logger.info("本次调用：输入 %d token，输出 %d token，约 ¥%.6f", input_tokens, output_tokens, cost)

        content = response.content
        # 纯文本时 content 是 str；多模态时可能是 list，这里统一转成字符串
        return content if isinstance(content, str) else str(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(Exception),
        before_sleep=_log_before_retry,
    )
    def _invoke_structured_with_retry(self, structured_llm, messages: list[BaseMessage], schema: type[T]) -> T:
        """调用结构化输出，统计 token，并处理解析失败。"""
        # include_raw=True 时，invoke 返回一个 dict，包含三个 key：
        #   raw：原始 AIMessage（含 token 用量）
        #   parsed：解析好的 Pydantic 对象（解析失败时为 None）
        #   parsing_error：解析错误信息（成功时为 None）
        result = structured_llm.invoke(messages)

        # 从原始响应里统计 token（复用步骤 2 的逻辑）
        raw = result.get("raw")
        if raw is not None:
            input_tokens, output_tokens = self._extract_usage(raw)
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            cost = self._calc_cost(input_tokens, output_tokens)
            logger.info(
                "本次结构化调用：输入 %d token，输出 %d token，约 ¥%.6f",
                input_tokens, output_tokens, cost,
            )

        # 优先用 LangChain 自动解析的结果
        parsed = result.get("parsed")
        if parsed is not None:
            return parsed

        # 兜底：DeepSeek 在带 system message 时，LangChain 的自动解析会得到 None
        # （parsing_error 也为 None，即"静默失败"）。但 raw.tool_calls 里其实有完整的
        # 函数参数 args，手动用 schema.model_validate 解析更稳健。
        if raw is not None:
            tool_calls = getattr(raw, "tool_calls", None) or []
            for tc in tool_calls:
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
                if args:
                    return schema.model_validate(args)

        raise ValueError(f"结构化输出解析失败：{result.get('parsing_error')}")

    def _extract_usage(self, response) -> tuple[int, int]:
        """从模型响应里提取 (输入 token 数, 输出 token 数)。"""
        # langchain 的 AIMessage 通过 usage_metadata 属性携带 token 用量。
        # 实测 usage_metadata 是一个 dict（如 {'input_tokens': 5, 'output_tokens': 9}），
        # 所以用 .get 取值；同时兼容"未来版本可能改成对象"的情况。
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return 0, 0
        if isinstance(usage, dict):
            return usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        return getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """根据 token 数和单价估算费用（单位：元）。"""
        price_in = self.settings.input_price_per_million
        price_out = self.settings.output_price_per_million
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
