"""
步骤 4 + 步骤 5 演示脚本：ReAct 循环 + 真实搜索 + 引用溯源

运行方式（在项目根目录执行）：
    python -m src.demo_react                                            # 用默认主题
    python -m src.demo_react "帮我研究未来几年 AI Agent 的发展趋势"      # 自定义主题
也可以在 PyCharm 里右键本文件 → Run，在 Run Configuration 里配 Program arguments。

这个脚本演示完整的研究流程：
  制定计划 → 对每个子问题跑 ReAct 循环（真实搜索 + 抓取网页正文）
  → 汇总成带 [n] 引用的研究报告 → 打印文末参考文献列表

注意：
  - 若 .env 里配置了 TAVILY_API_KEY → 使用真实搜索（结果可溯源）
  - 若没配置 → 自动退化为"LLM 模拟搜索"（结果不可信，仅体验流程）
"""
import sys

from src.agent import ResearchAgent
from src.llm.client import LLMClient


def main() -> None:
    # 从命令行参数读取研究主题（没传则用默认主题）
    topic = sys.argv[1] if len(sys.argv) > 1 else "帮我研究未来几年 AI Agent 的发展趋势"

    # 创建一个共享的 LLMClient（好处：全程的 token 消耗能一起统计，最后统一看总账）
    client = LLMClient()

    # 把 client 注入 Agent（依赖注入）
    agent = ResearchAgent(llm_client=client)

    # 开始研究：会打印完整的 ReAct 过程日志，并返回报告与来源
    result = agent.research(topic)

    # ---------- 打印研究报告 ----------
    print()
    print("=" * 70)
    print("  研究报告")
    print("=" * 70)
    print(result.get("report", "（未生成报告）"))

    # ---------- 打印参考文献列表 ----------
    # 注意：这份列表来自"来源登记处"（真实 URL），不是 LLM 生成的，避免编造链接
    sources = result["sources"]
    print()
    print("=" * 70)
    print("  参考文献")
    print("=" * 70)
    if not sources:
        print("（本次研究没有检索到外部来源）")
    else:
        for i, citation in enumerate(sources, 1):
            print(f"[{i}] {citation.title}")
            print(f"    {citation.url}")

    # ---------- 打印总费用 ----------
    print()
    print("=" * 70)
    print("  本次研究总费用")
    print("=" * 70)
    print(client.usage_report())


if __name__ == "__main__":
    main()
