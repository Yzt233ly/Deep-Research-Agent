"""
配置管理模块（步骤 1）

作用：把 API Key、模型名、循环次数等"会变的东西"从代码里抽出来，
统一放到 .env 文件里管理。这样：
  1. 切换模型 / 换 API Key 时，只改 .env，不用改代码
  2. API Key 不会写死在代码里被误传到 GitHub

这里使用 pydantic-settings 库，它会在创建 Settings 对象时自动读取 .env 文件，
并把环境变量映射成类的字段，同时还能做类型校验。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    全局配置类。

    每个字段都会被 pydantic-settings 自动匹配一个同名（大写）的环境变量：
      字段 openai_api_key  <->  环境变量 OPENAI_API_KEY
    如果 .env 或系统环境变量里没有对应值，就使用字段后面的默认值。
    """

    # 告诉 pydantic-settings 去哪里读配置、怎么读
    model_config = SettingsConfigDict(
        env_file=".env",           # 从项目根目录的 .env 读取
        env_file_encoding="utf-8", # 用 UTF-8 编码读（避免中文注释乱码）
        extra="ignore",            # .env 里多出的字段直接忽略，不报错
    )

    # ---- LLM 相关配置 ----
    # 说明：DeepSeek 走的是 OpenAI 兼容协议，所以字段名仍保留 openai_ 前缀；
    #       langchain-openai 底层复用的就是 api_key / base_url 这两个概念。
    openai_api_key: str = ""                             # API Key（填 DeepSeek 的 Key，步骤 2 才需要）
    openai_base_url: str = "https://api.deepseek.com/v1"  # DeepSeek 接口地址
    model_name: str = "deepseek-chat"                    # 模型：deepseek-chat（通用）/ deepseek-reasoner（推理）
    input_price_per_million: float = 1.0    # 输入单价（元/百万 token），DeepSeek 参考价，请以官方为准
    output_price_per_million: float = 2.0   # 输出单价（元/百万 token），DeepSeek 参考价，请以官方为准

    # ---- Agent 行为配置 ----
    max_iterations: int = 10   # 最大循环次数，防止 Agent 陷入死循环

    # ---- 日志配置 ----
    log_level: str = "INFO"    # 日志级别：DEBUG / INFO / WARNING / ERROR


@lru_cache
def get_settings() -> Settings:
    """
    获取全局唯一的 Settings 实例。

    为什么要用 @lru_cache？
      Settings 每次创建都会重新读一遍 .env 文件。加上 @lru_cache 后，
      第一次调用会真正创建并缓存起来，之后的调用直接返回同一个实例，
      既保证"全局只有一个配置"，又避免重复读取的开销。
      这是一种常见的"单例"写法。

    用法：
      from src.config import get_settings
      settings = get_settings()
    """
    return Settings()
