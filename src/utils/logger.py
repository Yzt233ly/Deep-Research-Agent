"""
日志模块（步骤 1）

作用：用 logging 替代 print，好处是：
  1. 日志带时间戳，方便回溯 Agent 每一步发生在什么时候
  2. 可以分级（DEBUG / INFO / WARNING / ERROR），调试时想看得多就调成 DEBUG
  3. 后期可以把日志写到文件，而不是只打印在终端
"""
import logging

from src.config import get_settings

# 日志统一格式：时间 [级别] 模块名: 内容
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str) -> logging.Logger:
    """
    获取一个配置好的 logger。

    参数 name 通常传 __name__，这样日志里能看出是哪段代码输出的。

    为什么判断 `if not logger.handlers`？
      Python 的 logger 有层级结构，同一个名字可能被重复获取。
      如果不加判断，每调用一次就加一个 handler，会导致同一条日志打印多次。
      判断 handlers 为空才添加，保证每个 logger 只配置一次。
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        # 创建一个输出到控制台的 handler
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)

        # 从配置里读日志级别（默认 INFO）
        level = get_settings().log_level.upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

        # 关闭向父 logger 传递，避免同一条日志被重复打印
        logger.propagate = False

    return logger
