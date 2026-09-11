r"""网页入口：输入主题 → 规划 → 人工编辑确认 → 执行 → 展示报告。

运行：.venv\Scripts\python.exe -m streamlit run app.py
Streamlit 每次交互都会重新执行脚本，所以业务对象和结果必须放在 session_state。
"""
import streamlit as st

from src.config import get_settings
from src.ui.support import capture_logs, create_agent, plan_from_rows, report_markdown, safe_error


def reset_research() -> None:
    """更换主题后废弃旧计划，防止用 A 的计划研究 B；不会自动发起调用。"""
    state = st.session_state
    state.update(agent=None, plan=None, result=None, stage="input", run_log=[], error="")
    state.plan_version += 1


def render_result(result: dict) -> None:
    """结果从会话读取；切换标签、下载均不重新执行 Agent。"""
    st.subheader("研究结果")
    report, sources, notes, answers = st.tabs(["研究报告", "参考文献", "关键事实", "子问题答案"])
    with report:
        markdown = report_markdown(result)
        st.markdown(markdown)
        st.download_button("下载 Markdown 报告", markdown, file_name="research_report.md",
                           mime="text/markdown", on_click="ignore")
    with sources:
        if not result["sources"]:
            st.info("本次没有外部来源。")
        for i, source in enumerate(result["sources"], 1):
            st.write(f"[{i}] {source.title}")
            st.write(source.url)
            st.caption(source.summary)
    with notes:
        if not result["notes"]:
            st.info("本次未提取到关键事实。")
        for note in result["notes"]:
            st.write(note.fact)
            st.caption(f"来源：{note.source_url}")
    with answers:
        for question, answer in result["answers"]:
            with st.expander(question):
                st.markdown(answer)


def main() -> None:
    st.set_page_config(page_title="Deep Research Agent", layout="wide")
    state = st.session_state
    defaults = dict(agent=None, plan=None, result=None, stage="input", run_log=[],
                    plan_version=0, error="", active_topic="")
    for key, value in defaults.items():
        if key not in state:
            state[key] = value

    busy = state.stage in ("planning", "running")
    settings = get_settings()
    st.title("Deep Research Agent")
    st.caption("输入主题 → 生成计划 → 人工编辑确认 → 开始研究 → 查看报告")
    with st.sidebar:
        st.header("运行配置")
        st.write(f"模型：{settings.model_name}")
        st.write(f"每个子问题最多 {settings.max_iterations} 轮")
        st.write("搜索：Tavily" if settings.tavily_api_key else "搜索：模拟模式")
        st.caption("配置读取自项目 .env，修改后需重启服务。")
        st.caption("会话保存在当前连接中；刷新浏览器或重启服务后需要重新开始。")
        st.button("清空并重新开始", on_click=reset_research, disabled=busy)
    if not settings.tavily_api_key:
        st.warning("未配置 Tavily Key：将使用模型模拟搜索，结果不能作为真实研究依据。")

    topic = st.text_input("研究主题", key="topic_input", on_change=reset_research,
                          disabled=busy, placeholder="例如：RAG 在智能客服中的应用与局限")
    st.caption("生成计划会调用模型；只有确认计划后才开始搜索和撰写报告。")
    if st.button("生成研究计划", disabled=busy, type="primary"):
        if not topic.strip():
            state.error = "请输入研究主题"
        else:
            reset_research()
            state.active_topic = topic.strip()
            state.stage = "planning"
            st.rerun()

    if state.plan is not None:
        st.subheader("编辑并确认研究计划")
        st.caption("双击单元格编辑；可增删行。优先级 1–5，数字越大越先研究，同优先级按表格顺序。")
        # form 把多处修改一起提交；表格源数据保持固定，避免 rerun 时重复应用编辑差量。
        # 新计划更换 key，确保上一份计划的增删记录不会污染新计划。
        locked = busy or state.stage == "done"
        with st.form(f"plan_form_{state.plan_version}"):
            approach = st.text_area("整体研究思路", state.plan.overall_approach, disabled=locked)
            rows = st.data_editor(
                [sq.model_dump() for sq in state.plan.sub_questions],
                key=f"plan_editor_{state.plan_version}", num_rows="dynamic",
                hide_index=True, width="stretch", disabled=locked,
                column_config={
                    "question": st.column_config.TextColumn("子问题", required=True),
                    "priority": st.column_config.NumberColumn("优先级", min_value=1,
                                                               max_value=5, step=1, required=True),
                },
            )
            confirmed = st.form_submit_button("确认并开始研究", disabled=locked, type="primary")
        if confirmed:
            try:
                state.approved_plan = plan_from_rows(rows, approach)
            except ValueError as exc:
                state.error = str(exc)
            else:
                state.error = ""
                state.stage = "running"
                st.rerun()

    if state.error:
        st.error(state.error)
    if state.stage == "done":
        st.success("研究完成。可查看或下载结果；重新生成计划后可发起新的研究。")
    with st.expander("运行日志", expanded=busy or bool(state.error)):
        st.caption("展示当前任务最近 1000 条日志。")
        log_view = st.empty()
        log_view.code("\n".join(state.run_log) or "等待开始。", language=None)

    # 单独的执行状态让按钮先变为禁用，再同步调用 Agent。
    # 成功后立即改变状态，之后的页面重跑只展示结果，不重复付费执行。
    if busy:
        operation = state.stage
        try:
            with capture_logs(state.run_log, lambda text: log_view.code(text, language=None)):
                with st.spinner("正在生成计划…" if operation == "planning" else "正在研究，请稍候…"):
                    if operation == "planning":
                        state.agent = create_agent()
                        state.plan = state.agent.make_plan(state.active_topic)
                        state.stage = "review"
                    else:
                        state.result = state.agent.research_from_plan(state.active_topic, state.approved_plan)
                        state.stage = "done"
        except Exception as exc:
            state.error = f"本次操作失败：{safe_error(exc)}。可检查配置或网络后重试。"
            state.stage = "review" if state.plan is not None else "input"
        st.rerun()

    if state.agent is not None and hasattr(state.agent.llm, "usage_report"):
        st.caption(state.agent.llm.usage_report())
    if state.result is not None:
        render_result(state.result)


if __name__ == "__main__":
    main()
