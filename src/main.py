"""
程序入口

运行方式（在项目根目录、激活 .venv 后执行）：
    python -m src.main                        # 用默认研究主题
    python -m src.main "帮我研究大模型微调"      # 自定义研究主题（命令行参数）

目前包含三个演示：
  1. show_config()：     步骤 1 —— 加载配置并打印日志
  2. demo_llm()：        步骤 2 —— 调用一次 LLM，展示重试与 token 统计
  3. demo_structured()： 步骤 3 —— 结构化输出，让 LLM 返回 ResearchPlan
"""
import sys

from src.config import get_settings
from src.llm.client import LLMClient
from src.models import ResearchPlan
from src.utils.logger import get_logger

logger = get_logger(__name__)


def show_config() -> None:
    """步骤 1：打印配置信息，验证配置能正确加载。"""
    settings = get_settings()
    logger.info("配置加载成功，模型：%s", settings.model_name)
    logger.info("API 地址：%s", settings.openai_base_url)
    logger.info("最大循环次数：%d", settings.max_iterations)


def demo_llm() -> None:
    """步骤 2：演示 LLMClient，调用一次模型并展示 token 统计。"""
    if not get_settings().openai_api_key:
        logger.warning("尚未填写 OPENAI_API_KEY，跳过 LLM 演示（填好后重跑即可）")
        return

    client = LLMClient()
    try:
        reply = client.chat("用一句话介绍你自己")
        logger.info("模型回复：%s", reply)
        logger.info(client.usage_report())
    except Exception as exc:
        logger.error("LLM 调用最终失败：%s", exc)
        logger.info("如果上面出现了「第 N 次尝试失败」的日志，说明重试机制已生效，请检查 Key 是否正确")


def demo_structured(topic: str | None = None) -> None:
    """步骤 3：演示结构化输出，让 LLM 返回 ResearchPlan。

    参数：
      topic: 研究主题；不传则使用默认主题
    """
    if not get_settings().openai_api_key:
        logger.warning("尚未填写 OPENAI_API_KEY，跳过结构化输出演示")
        return

    # 没传主题时用默认主题，保证直接运行也能出结果
    topic = topic or "帮我研究未来几年 AI Agent 的发展趋势"

    client = LLMClient()
    try:
        plan = client.generate_structured(
            topic,
            ResearchPlan,
            system="你是一名专业的研究规划助手，负责把研究主题拆解成可执行的子问题。",
        )
        logger.info("研究主题：%s", topic)
        logger.info("研究计划生成成功！")
        logger.info("整体思路：%s", plan.overall_approach)
        for i, sq in enumerate(plan.sub_questions, 1):
            logger.info("子问题 %d（优先级 %d）：%s", i, sq.priority, sq.question)
        logger.info(client.usage_report())
    except Exception as exc:
        logger.error("结构化输出失败：%s", exc)


def main() -> None:
    show_config()
    demo_llm()
    # 从命令行参数读取研究主题：sys.argv[0] 是脚本名，sys.argv[1] 才是第一个参数
    # 例如：python -m src.main "帮我研究大模型微调"
    # 没传参数时，demo_structured 内部会使用默认主题
    topic = sys.argv[1] if len(sys.argv) > 1 else None
    demo_structured(topic)


if __name__ == "__main__":
    main()
