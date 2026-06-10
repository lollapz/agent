"""LangGraph StateGraph —— 竞品情报 Research Agent 核心图

工作流（v2 — Research Agent 循环）：
  discover → scrape → compare → review
    └─ 信息不足 & 未超最大轮次 → prepare_next_search → discover（循环）
    └─ 信息充足 / 达到最大轮次 → analyze → END

LLM: DeepSeek (LangChain ChatOpenAI 兼容接口)
搜索: Tavily Search API
爬取: Firecrawl

API Key 通过模块级 set_graph_config() 注入。
"""

import json
from typing import TypedDict, List, Optional

from tavily import TavilyClient
from firecrawl import FirecrawlApp
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from models import CompetitorDataSchema


# ── 模块级配置（由 main.py 在 invoke 前注入） ──
_graph_config: dict = {}


def set_graph_config(config: dict) -> None:
    """注入图运行所需的全部配置（API Keys）"""
    _graph_config.clear()
    _graph_config.update(config)


# ═══════════════════════════════════════════════════════════════
#  State 定义
# ═══════════════════════════════════════════════════════════════

class CompetitorState(TypedDict):
    # ── 原有字段 ──
    company_url: str                # 用户输入的公司 URL
    company_description: str        # 用户输入的公司描述
    competitor_urls: List[str]      # 发现节点输出的竞品 URL 列表（多轮累积）
    competitor_data: List[dict]     # 爬取节点输出的结构化竞品数据（多轮累积）
    analysis_report: str            # 分析节点输出的 Markdown 报告
    error: Optional[str]            # 错误信息

    # ── Research Agent 循环新增字段 ──
    iteration_count: int            # 当前补充搜索轮数（初始 0）
    max_iterations: int             # 最大补充搜索轮数（默认 2）
    review_result: dict             # Review 节点输出（评估摘要）
    missing_info: List[str]         # 缺失信息字段列表
    search_queries: List[str]       # 下一轮补充搜索 query
    is_sufficient: bool             # 当前数据是否足够生成分析报告
    visited_urls: List[str]         # 已抓取的 URL（避免重复）


# ═══════════════════════════════════════════════════════════════
#  Node 1: 竞品发现（discover_node）— Tavily Search
#  支持两种模式：首轮搜索 / 补充搜索
# ═══════════════════════════════════════════════════════════════

def discover_node(state: CompetitorState) -> dict:
    """
    竞品发现节点：
    - 首轮：根据用户输入搜索 3 个竞品 URL
    - 补充轮：使用 search_queries 搜索更多 URL
    避免重复，总量上限 10
    """
    company_url = state.get("company_url", "")
    company_description = state.get("company_description", "")
    tavily_api_key = _graph_config.get("tavily_api_key", "")

    existing_urls: List[str] = list(state.get("competitor_urls", []))
    visited_urls: List[str] = list(state.get("visited_urls", []))
    search_queries: List[str] = list(state.get("search_queries", []))

    if not company_url and not company_description and not search_queries:
        return {"error": "请提供公司 URL 或描述", "competitor_urls": []}

    tavily = TavilyClient(api_key=tavily_api_key)

    try:
        if search_queries:
            # ── 补充搜索模式 ──
            new_urls: List[str] = []
            skip_set = set(existing_urls) | set(visited_urls)

            for query in search_queries:
                response = tavily.search(
                    query=query,
                    max_results=3,
                    search_depth="advanced",
                    include_answer=False,
                )
                results = response.get("results", [])
                for r in results:
                    u = r["url"]
                    if u not in skip_set and u not in new_urls:
                        new_urls.append(u)

            # 去重 + 总量上限 10
            combined = existing_urls + [u for u in new_urls if u not in existing_urls]
            combined = combined[:10]

            return {"competitor_urls": combined, "error": None}

        else:
            # ── 首轮搜索模式 ──
            if company_url and company_description:
                query = (
                    f"Find top 3 direct competitors of {company_description}"
                    f" (website: {company_url})"
                )
            elif company_url:
                query = f"Find top 3 direct competitors of the company at {company_url}"
            else:
                query = f"Find top 3 direct competitors of: {company_description}"

            response = tavily.search(
                query=query,
                max_results=3,
                search_depth="advanced",
                include_answer=False,
            )

            results = response.get("results", [])
            urls = [r["url"] for r in results[:3]]

            return {"competitor_urls": urls, "error": None}

    except Exception as e:
        return {"competitor_urls": existing_urls, "error": f"竞品发现失败: {str(e)}"}


# ═══════════════════════════════════════════════════════════════
#  Node 2: 网页爬取（scrape_node）— Firecrawl
#  只抓取未访问 URL，失败不中断，保留已成功数据
# ═══════════════════════════════════════════════════════════════

def scrape_node(state: CompetitorState) -> dict:
    """
    网页爬取节点：
    - 只抓取 competitor_urls 中不在 visited_urls 的 URL
    - 单个 URL 失败记录 error 但继续
    - 追加新数据到已有 competitor_data
    """
    competitor_urls: List[str] = list(state.get("competitor_urls", []))
    visited_urls: List[str] = list(state.get("visited_urls", []))
    existing_data: List[dict] = list(state.get("competitor_data", []))
    firecrawl_api_key = _graph_config.get("firecrawl_api_key", "")

    to_scrape = [u for u in competitor_urls if u not in visited_urls]

    if not to_scrape:
        return {"error": None}

    new_data: List[dict] = []
    new_visited: List[str] = list(visited_urls)
    errors: List[str] = []

    extraction_prompt = """
    Extract detailed information about the company's offerings, including:
    - Company name and official website URL
    - Detailed product/service description and core business
    - Pricing details, plans, tiers, free/paid options
    - Key features and differentiating capabilities
    - Target customer segments, industries, and user personas
    - Market positioning, competitive advantages, and brand strategy
    - Company strengths and core competencies
    - Company weaknesses and areas for improvement
    - Technology stack, frameworks, and tools
    - Customer feedback, reviews, and testimonials

    Analyze the entire website content to provide comprehensive information for each field.
    """

    for comp_url in to_scrape:
        try:
            app = FirecrawlApp(api_key=firecrawl_api_key)
            url_pattern = f"{comp_url}/*"

            response = app.extract(
                [url_pattern],
                prompt=extraction_prompt,
                schema=CompetitorDataSchema.model_json_schema()
            )

            if hasattr(response, 'success') and response.success:
                if hasattr(response, 'data') and response.data:
                    extracted_info = response.data

                    def safe_get(data, key, default='N/A'):
                        """安全取值，兼容 dict 和 object"""
                        if isinstance(data, dict):
                            return data.get(key, default)
                        return getattr(data, key, default)

                    def safe_list(data, key, max_items=5):
                        """安全取列表，可截断"""
                        if isinstance(data, dict):
                            val = data.get(key, [])
                        else:
                            val = getattr(data, key, [])
                        if not val:
                            return ['N/A']
                        return val[:max_items]

                    comp_json = {
                        "competitor_url": comp_url,
                        "company_name": safe_get(extracted_info, 'company_name'),
                        "website": safe_get(extracted_info, 'website', comp_url),
                        "product_description": safe_get(extracted_info, 'product_description'),
                        "pricing": safe_get(extracted_info, 'pricing'),
                        "core_features": safe_list(extracted_info, 'core_features'),
                        "target_customers": safe_get(extracted_info, 'target_customers'),
                        "positioning": safe_get(extracted_info, 'positioning'),
                        "strengths": safe_list(extracted_info, 'strengths'),
                        "weaknesses": safe_list(extracted_info, 'weaknesses'),
                        "tech_stack": safe_list(extracted_info, 'tech_stack'),
                        "customer_feedback": safe_get(extracted_info, 'customer_feedback'),
                    }
                    new_data.append(comp_json)
                    new_visited.append(comp_url)
                else:
                    errors.append(f"无返回数据: {comp_url}")
            else:
                errors.append(f"Firecrawl 提取失败: {comp_url}")

        except Exception as e:
            errors.append(f"{comp_url}: {str(e)}")

    return {
        "competitor_data": existing_data + new_data,
        "visited_urls": new_visited,
        "error": None,
    }


# ═══════════════════════════════════════════════════════════════
#  Node 3: 数据对比（compare_node）— 多轮累积验证
# ═══════════════════════════════════════════════════════════════

def compare_node(state: CompetitorState) -> dict:
    """
    数据对比节点：
    - 验证多轮累积后的 competitor_data 是否非空
    - 不覆盖数据，仅做 gate
    """
    competitor_data = state.get("competitor_data", [])

    if not competitor_data:
        return {"error": "无竞品数据可对比"}

    return {}


# ═══════════════════════════════════════════════════════════════
#  Node 4: 数据充分性审查（review_node）
#  评估当前竞品数据是否足够生成分析报告
# ═══════════════════════════════════════════════════════════════

# Review 评估的必需字段
REQUIRED_FIELDS = [
    "company_name",
    "website",
    "product_description",
    "core_features",
    "pricing",
    "target_customers",
    "positioning",
    "strengths",
    "weaknesses",
]

# 缺失字段 → Tavily 搜索 query 模板
QUERY_TEMPLATES = {
    "pricing": "{name} pricing plans tiers cost",
    "target_customers": "{name} target customers market",
    "positioning": "{name} market positioning strategy",
    "strengths": "{name} strengths advantages competitive edge",
    "weaknesses": "{name} weaknesses disadvantages reviews",
    "product_description": "{name} product overview description",
    "core_features": "{name} key features capabilities",
    "company_name": "{name} company",
    "website": "{name} official website",
}


def review_node(state: CompetitorState) -> dict:
    """
    Review 节点：
    1. 逐竞品检查 9 个核心字段是否有效
    2. 判断数据充分性（≥60% 竞品数据完整即视为充分）
    3. 生成 missing_info 和 search_queries
    """

    def is_valid(value) -> bool:
        """判断字段值是否有效（非空、非 N/A）"""
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != "" and value.strip().upper() != "N/A"
        if isinstance(value, list):
            return len(value) > 0 and not (
                len(value) == 1 and str(value[0]).upper() == "N/A"
            )
        return True

    competitor_data = state.get("competitor_data", [])

    if not competitor_data:
        return {
            "is_sufficient": False,
            "review_result": {
                "total_competitors": 0,
                "sufficient_count": 0,
                "is_sufficient": False,
                "missing_info": ["无竞品数据"],
                "next_queries": [],
                "per_competitor": [],
            },
            "missing_info": ["无竞品数据"],
            "search_queries": [],
            "error": "无竞品数据可供审查",
        }

    # 逐竞品检查
    all_missing_fields: set = set()
    sufficient_count = 0
    per_competitor = []

    for comp in competitor_data:
        missing = []
        for field in REQUIRED_FIELDS:
            value = comp.get(field)
            if not is_valid(value):
                missing.append(field)

        # 至少 6/9 字段有效 → 这个竞品数据充分
        if len(missing) <= 3:
            sufficient_count += 1

        all_missing_fields.update(missing)
        per_competitor.append({
            "company_name": comp.get("company_name", "N/A"),
            "missing_fields": missing,
            "sufficient": len(missing) <= 3,
        })

    total = len(competitor_data)
    # ≥60% 竞品数据充分 → 整体充分
    is_sufficient = (sufficient_count / total) >= 0.6 if total > 0 else False

    missing_info = list(all_missing_fields)

    # 生成补充搜索 query
    search_queries: List[str] = []
    company_names = [
        c.get("company_name", "")
        for c in competitor_data
        if is_valid(c.get("company_name"))
    ]

    if not is_sufficient and missing_info and company_names:
        for name in company_names[:3]:
            for field in missing_info[:3]:
                template = QUERY_TEMPLATES.get(
                    field, "{name} {field}"
                )
                q = template.replace("{name}", name)
                if "{field}" in q:
                    q = q.replace("{field}", field.replace("_", " "))
                search_queries.append(q)

        # 去重，最多 5 条
        seen = set()
        unique_queries = []
        for q in search_queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        search_queries = unique_queries[:5]

    review_result = {
        "total_competitors": total,
        "sufficient_count": sufficient_count,
        "is_sufficient": is_sufficient,
        "missing_info": missing_info,
        "next_queries": search_queries,
        "per_competitor": per_competitor,
    }

    return {
        "review_result": review_result,
        "missing_info": missing_info,
        "search_queries": search_queries,
        "is_sufficient": is_sufficient,
    }


# ═══════════════════════════════════════════════════════════════
#  Node 5: 准备下一轮搜索（prepare_next_search_node）
#  递增 iteration_count，透传 search_queries
# ═══════════════════════════════════════════════════════════════

def prepare_next_search_node(state: CompetitorState) -> dict:
    """
    准备下一轮补充搜索：
    递增 iteration_count，保留 search_queries 供 discover_node 使用。
    """
    return {
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


# ═══════════════════════════════════════════════════════════════
#  条件路由：route_after_review
# ═══════════════════════════════════════════════════════════════

def route_after_review(state: CompetitorState) -> str:
    """
    根据 is_sufficient 和 iteration_count 决定下一步：
    - 数据充分 → "analyze"
    - 到达最大轮次 → "analyze"（强制继续）
    - 否则 → "prepare_next_search"
    """
    if state.get("is_sufficient", False):
        return "analyze"

    if state.get("iteration_count", 0) >= state.get("max_iterations", 2):
        return "analyze"

    return "prepare_next_search"


# ═══════════════════════════════════════════════════════════════
#  Node 6: AI 分析（analyze_node）— DeepSeek
#  使用最终累积竞品数据 + review_result 上下文
# ═══════════════════════════════════════════════════════════════

def analyze_node(state: CompetitorState) -> dict:
    """
    AI 分析节点：
    输入累积竞品数据 + review 结果，由 DeepSeek 生成 Markdown 战略分析报告。
    报告中标注数据不足项。
    """
    competitor_data = state.get("competitor_data", [])
    review_result = state.get("review_result", {})
    missing_info = state.get("missing_info", [])
    deepseek_api_key = _graph_config.get("deepseek_api_key", "")

    if not competitor_data:
        return {"analysis_report": "", "error": "无竞品数据可分析"}

    try:
        formatted_data = json.dumps(competitor_data, indent=2, ensure_ascii=False)
        missing_note = ""
        if missing_info:
            missing_note = (
                "\n\n[数据说明]\n"
                f"以下字段在部分竞品中缺失，分析时请注意标注：{', '.join(missing_info)}\n"
            )

        llm = ChatOpenAI(
            model="deepseek-chat",
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            temperature=0.3,
        )

        prompt = f"""Analyze the following competitor data in JSON format and generate a strategic competitive intelligence report in Markdown:

{formatted_data}
{missing_note}

# Report Structure

## 1. 竞品概览
- 逐一介绍每家竞品公司（名称、网站、核心产品描述）

## 2. 功能对比
- 用表格对比各竞品的核心功能、技术栈

## 3. 价格策略
- 对比定价模式、免费/付费方案、价格层级

## 4. 用户定位
- 分析各竞品的目标客户群体和市场定位

## 5. 优势劣势
- 列出每家竞品的竞争优势和改进空间

## 6. 市场机会与建议
- 基于竞品分析，发现市场空白和差异化机会
- 为目标公司提供产品开发和市场进入策略建议

## 7. 数据完整性说明（如有缺失）
- 列出本次分析中数据不足的字段，并说明影响范围

Requirements:
- 使用中文撰写
- 表格尽可能完整，缺失数据标注「暂无数据」
- 建议部分要具体、可执行
"""

        response = llm.invoke(prompt)
        return {"analysis_report": response.content, "error": None}

    except Exception as e:
        return {"analysis_report": "", "error": f"分析生成失败: {str(e)}"}


# ═══════════════════════════════════════════════════════════════
#  Graph 构建与编译（v2 — Research Agent 循环）
# ═══════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    """构建并编译 Research Agent StateGraph（含条件循环边）"""

    workflow = StateGraph(CompetitorState)

    # 注册 6 个节点
    workflow.add_node("discover", discover_node)
    workflow.add_node("scrape", scrape_node)
    workflow.add_node("compare", compare_node)
    workflow.add_node("review", review_node)
    workflow.add_node("prepare_next_search", prepare_next_search_node)
    workflow.add_node("analyze", analyze_node)

    # 入口
    workflow.set_entry_point("discover")

    # 线性边：discover → scrape → compare → review
    workflow.add_edge("discover", "scrape")
    workflow.add_edge("scrape", "compare")
    workflow.add_edge("compare", "review")

    # 条件边：review → analyze 或 prepare_next_search
    workflow.add_conditional_edges(
        "review",
        route_after_review,
        {
            "analyze": "analyze",
            "prepare_next_search": "prepare_next_search",
        }
    )

    # 循环边：prepare_next_search → discover
    workflow.add_edge("prepare_next_search", "discover")

    # 终点
    workflow.add_edge("analyze", END)

    return workflow.compile()
