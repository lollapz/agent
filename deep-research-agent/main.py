"""Streamlit 入口 —— 智能调研报告生成 Agent UI

基于 LangGraph StateGraph，Research Agent 循环：
  discover → scrape → compare → review
    └─ 信息不足 → prepare_next_search → discover（循环）
    └─ 信息充足 → analyze → END

LLM: DeepSeek | 搜索: Tavily | 爬取: Firecrawl
"""

import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from graph import build_graph, set_graph_config

# ── 加载 .env（不存在则静默跳过） ──
load_dotenv()


# ── 页面配置 ──
st.set_page_config(
    page_title="Deep Research Agent | LangGraph + DeepSeek",
    page_icon="🔍",
    layout="wide"
)


# ═══════════════════════════════════════════════════════════════
#  侧边栏：API Key 输入
# ═══════════════════════════════════════════════════════════════

st.sidebar.title("🔑 API 配置")

deepseek_api_key = st.sidebar.text_input(
    "DeepSeek API Key",
    type="password",
    value=os.getenv("DEEPSEEK_API_KEY", ""),
    help="DeepSeek Chat 模型，用于 AI 战略分析报告生成 + Review 数据评估"
)

tavily_api_key = st.sidebar.text_input(
    "Tavily API Key",
    type="password",
    value=os.getenv("TAVILY_API_KEY", ""),
    help="Tavily Search API，用于竞品发现与补充搜索"
)

firecrawl_api_key = st.sidebar.text_input(
    "Firecrawl API Key",
    type="password",
    value=os.getenv("FIRECRAWL_API_KEY", ""),
    help="Firecrawl 网页爬取，用于竞品网站结构化数据提取"
)


# ═══════════════════════════════════════════════════════════════
#  主界面
# ═══════════════════════════════════════════════════════════════

st.title("🔍 Deep Research Agent")
st.caption("LangGraph + DeepSeek + Tavily + Firecrawl — Research Agent 循环模式")

st.info(
    """
    **工作流：信息发现 → 网页抓取 → 数据汇聚 → 数据审查**
    - 数据充分 → AI 调研报告生成
    - 数据不足 → 自动补充搜索（最多 2 轮），再进入分析
    """
)
st.success("💡 同时提供 URL 和调研主题描述，效果最佳")

# 输入区域
col1, col2 = st.columns(2)
with col1:
    url = st.text_input("目标 URL", placeholder="https://example.com")
with col2:
    description = st.text_area("调研主题描述", placeholder="描述调研主题或业务，用于联网搜索", height=68)


# ═══════════════════════════════════════════════════════════════
#  分析按钮 + Graph 执行
# ═══════════════════════════════════════════════════════════════

if st.button("🚀 开始调研", type="primary", use_container_width=True):
    # ── 输入校验 ──
    if not url and not description:
        st.error("请提供目标 URL 或调研主题描述")
        st.stop()

    # ── API Key 校验 ──
    keys_missing = []
    if not deepseek_api_key:
        keys_missing.append("DeepSeek API Key")
    if not tavily_api_key:
        keys_missing.append("Tavily API Key")
    if not firecrawl_api_key:
        keys_missing.append("Firecrawl API Key")

    if keys_missing:
        st.error(f"请在侧边栏填写缺失的 API Key: {', '.join(keys_missing)}")
        st.stop()

    # ── 注入配置到 Graph 模块 ──
    set_graph_config({
        "deepseek_api_key": deepseek_api_key,
        "tavily_api_key": tavily_api_key,
        "firecrawl_api_key": firecrawl_api_key,
    })

    # ── 构建 Graph ──
    app = build_graph()

    # ── 初始 State（含 Research Agent 循环字段） ──
    initial_state = {
        "company_url": url,
        "company_description": description,
        "competitor_urls": [],
        "competitor_data": [],
        "analysis_report": "",
        "error": None,
        "iteration_count": 0,
        "max_iterations": 2,
        "review_result": {},
        "missing_info": [],
        "search_queries": [],
        "is_sufficient": False,
        "visited_urls": [],
    }

    # ── 执行 Graph ──
    with st.spinner("🔍 正在执行智能调研流水线（含补充搜索循环）..."):
        result = app.invoke(initial_state)

    # ── 错误处理 ──
    if result.get("error"):
        st.error(f"❌ 分析过程出错: {result['error']}")
        st.stop()

    # ── 执行摘要：迭代信息 ──
    iteration_count = result.get("iteration_count", 0)
    visited_count = len(result.get("visited_urls", []))
    is_sufficient = result.get("is_sufficient", False)
    review_result = result.get("review_result", {})
    missing_info = result.get("missing_info", [])

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("🔁 搜索轮次", f"{iteration_count + 1} / 3", help="含首轮，最多 3 轮")
    with col_b:
        st.metric("🌐 已抓取 URL", visited_count)
    with col_c:
        label = "✅ 数据充足" if is_sufficient else "⚠️ 数据不足"
        st.metric("📋 数据评估", label)
    with col_d:
        trigger_count = iteration_count
        st.metric("🔄 补充搜索", f"{trigger_count} 次", delta=None if trigger_count == 0 else None)

    # ── Review 详情 ──
    if review_result:
        with st.expander("🔎 数据审查详情", expanded=False):
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.caption("逐竞品评估")
                per_comp = review_result.get("per_competitor", [])
                for pc in per_comp:
                    name = pc.get("company_name", "N/A")
                    missing_f = pc.get("missing_fields", [])
                    sufficient = pc.get("sufficient", False)
                    icon = "✅" if sufficient else "⚠️"
                    st.write(f"{icon} **{name}** — 缺失: {', '.join(missing_f) if missing_f else '无'}")
            with col_r2:
                st.caption("补充搜索 Query")
                queries = review_result.get("next_queries", [])
                if queries:
                    for q in queries:
                        st.code(q, language=None)
                else:
                    st.write("无需补充搜索")

    # ── 缺失信息警告 ──
    if missing_info:
        st.warning(f"⚠️ 以下信息在部分竞品中缺失：{', '.join(missing_info)}")

    # ── 展示：竞品 URL ──
    competitor_urls = result.get("competitor_urls", [])
    if competitor_urls:
        with st.expander(f"📌 发现 {len(competitor_urls)} 个资料 URL", expanded=True):
            for i, u in enumerate(competitor_urls, 1):
                st.write(f"{i}. [{u}]({u})")

    # ── 展示：竞品对比表格 ──
    competitor_data = result.get("competitor_data", [])
    if competitor_data:
        st.subheader("📊 信息对比")

        table_data = []
        for comp in competitor_data:
            row = {
                "公司": comp.get('company_name', 'N/A'),
                "网站": comp.get('website', 'N/A'),
                "产品描述": _truncate(comp.get('product_description', 'N/A'), 100),
                "定价": _truncate(comp.get('pricing', 'N/A'), 100),
                "核心功能": _join_list(comp.get('core_features'), 3),
                "目标客户": _truncate(comp.get('target_customers', 'N/A'), 80),
                "市场定位": _truncate(comp.get('positioning', 'N/A'), 80),
                "优势": _join_list(comp.get('strengths'), 3),
                "劣势": _join_list(comp.get('weaknesses'), 3),
            }
            table_data.append(row)

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        with st.expander("📋 查看原始结构化数据"):
            st.json(competitor_data)

    # ── 展示：AI 分析报告 ──
    analysis_report = result.get("analysis_report", "")
    if analysis_report:
        st.subheader("📝 AI 调研报告")
        st.markdown(analysis_report)

    if analysis_report:
        st.success("✅ 调研完成！")
        st.balloons()


# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════

def _truncate(text: str, max_len: int) -> str:
    """截断过长文本"""
    if not text or text == 'N/A':
        return 'N/A'
    if len(text) > max_len:
        return text[:max_len] + '...'
    return text


def _join_list(items, max_items: int) -> str:
    """列表转逗号分隔，最多 N 项"""
    if not items or items == ['N/A']:
        return 'N/A'
    return ', '.join(items[:max_items])
