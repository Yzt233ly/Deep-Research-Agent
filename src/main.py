"""
程序入口（步骤 1）

运行方式（在项目根目录、激活 .venv 后执行）：
    python -m src.main

这一步的 main 只做一件事：验证"配置能正确加载 + 日志能正确输出"。
只要看到日志输出「配置加载成功」，就说明骨架搭好了，
后面步骤 2~6 会在此基础上不断扩展。
"""
from src.config import get_settings
from src.utils.logger import get_logger

# 用当前模块名创建一个 logger，之后所有日志都从这里输出
logger = get_logger(__name__)


def main() -> None:
    """主函数：加载配置并用日志打印关键信息。"""
    settings = get_settings()

    # 演示日志的几种级别，让你直观看到它们的区别
    logger.debug("这是一条 DEBUG 日志（默认 INFO 级别下看不到）")
    logger.info("配置加载成功，模型：%s", settings.model_name)
    logger.info("API 地址：%s", settings.openai_base_url)
    logger.info("最大循环次数：%d", settings.max_iterations)

    # 检查 API Key 是否已填写（步骤 1 不强制要求，步骤 2 会用到）
    if settings.openai_api_key:
        logger.info("已检测到 API Key（长度 %d），可以进入步骤 2", len(settings.openai_api_key))
    else:
        logger.warning("尚未填写 OPENAI_API_KEY（.env 中为空），步骤 1 不影响，步骤 2 前需要补上")


if __name__ == "__main__":
    main()
