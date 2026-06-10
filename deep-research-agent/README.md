# Competitor Intel Agent 🔍

基于 **LangGraph + DeepSeek + Tavily + Firecrawl** 的 **Research Agent 循环模式**竞品情报分析 Agent。

输入公司 URL 或业务描述，自动进行多轮搜索 → 数据审查 → 补充搜索 → AI 战略分析，确保数据充分后才生成报告。

## 核心能力

| 能力 | 说明 |
|------|------|
| 🔁 Research Agent 循环 | 数据不足时自动补充搜索，最多 2 轮 |
| 📋 数据充分性审查 | 9 维度逐竞品评估（公司名/定价/功能/定位/优劣势等） |
| 🚫 visited_urls 去重 | 不重复抓取相同 URL |
| 📊 多轮数据累积 | 每轮搜索追加数据，不覆盖已有结果 |
| 📝 DeepSeek 战略报告 | 7 部分中文 Markdown 报告（含数据完整性说明） |

## 架构

```
用户输入 (URL/描述)
    │
    ▼
┌──────────────────┐
│    discover      │ ← Tavily Search（首轮 + 补充轮）
│  竞品发现节点     │    去重、上限 10 URL
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│     scrape       │ ← Firecrawl extract()
│  网页爬取节点     │    只抓未访问 URL，失败不中断
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    compare       │ ← 多轮累积数据验证
│  数据对比节点     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐         ┌──────────────────────┐
│     review       │ ──────→ │ prepare_next_search  │
│  数据审查节点     │  不充分  │  递增 iteration_count │
│  9 维度评估      │         └──────────┬───────────┘
└────────┬─────────┘                    │
         │ 充分 / 达上限                  │
         ▼                              ▼
┌──────────────────┐         ┌──────────────────┐
│    analyze       │         │    discover      │ ← 循环
│  DeepSeek 报告   │         │  使用 search_query│
└──────────────────┘         └──────────────────┘

LangGraph 条件边：route_after_review
  → is_sufficient=True  → analyze
  → iteration >= max   → analyze
  → 否则               → prepare_next_search → discover（循环）
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 框架 | LangGraph (StateGraph + Conditional Edges) |
| LLM | DeepSeek (deepseek-chat, OpenAI 兼容接口) |
| 竞品发现 | Tavily Search API |
| 网页爬取 | Firecrawl (extract + Pydantic Schema) |
| 数据建模 | Pydantic (11 字段) |
| 数据分析 | Pandas |
| 前端 | Streamlit |
| 环境管理 | uv |

## 快速启动

```bash
# 1. 安装依赖
uv venv
uv sync

# 2. 启动 Streamlit
uv run streamlit run main.py
```

## 使用方式

1. 在侧边栏填入 API Key：
   - **DeepSeek API Key**（必填）— 战略分析 + Review 评估
   - **Tavily API Key**（必填）— 竞品搜索发现 + 补充搜索
   - **Firecrawl API Key**（必填）— 网页爬取与结构化提取
2. 输入公司 URL 或业务描述
3. 点击「🚀 开始分析」
4. 系统自动执行多轮搜索 — 审查 — 补充搜索循环
5. 查看执行摘要（轮次、URL 数、数据评估、补充搜索次数）
6. 展开「数据审查详情」查看逐竞品评估和补充搜索 Query
7. 查看竞品对比表格和 DeepSeek 战略分析报告

## 项目结构

```
competitor-intel-agent/
├── main.py          # Streamlit 入口 + UI 渲染
├── graph.py         # LangGraph StateGraph（6 节点 + 条件边 + 循环边）
│                    #   discover / scrape / compare / review
│                    #   prepare_next_search / analyze
│                    #   route_after_review（条件路由）
├── models.py        # Pydantic CompetitorDataSchema（11 字段）
├── pyproject.toml   # uv 项目配置与依赖声明
└── README.md        # 本文件
```

## State 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| company_url | str | 用户输入的公司 URL |
| company_description | str | 用户输入的公司描述 |
| competitor_urls | List[str] | 竞品 URL（多轮累积，上限 10） |
| competitor_data | List[dict] | 结构化竞品数据（多轮累积） |
| analysis_report | str | Markdown 分析报告 |
| error | Optional[str] | 错误信息 |
| iteration_count | int | 当前补充搜索轮数 |
| max_iterations | int | 最大补充搜索轮数 |
| review_result | dict | Review 评估结果 |
| missing_info | List[str] | 缺失字段列表 |
| search_queries | List[str] | 下一轮搜索 query |
| is_sufficient | bool | 数据是否足够 |
| visited_urls | List[str] | 已抓取 URL（去重） |

## 改造历程

### v1 → v2（当前版本）
- ✅ 新增 review_node（9 维度数据充分性评估）
- ✅ 新增 prepare_next_search_node（迭代计数）
- ✅ 新增 route_after_review（条件路由）
- ✅ discover_node 支持首轮 + 补充搜索双模式
- ✅ scrape_node 支持 visited_urls 去重 + 失败不中断
- ✅ compare_node 支持多轮累积数据
- ✅ analyze_node 报告中标注数据缺失项
- ✅ CompetitorDataSchema 扩展至 11 字段
- ✅ 循环边：prepare_next_search → discover

### 原始 → v1
- ❌ 删除 Agno Agent / Agent Team 全部依赖
- ✅ 改用 LangGraph StateGraph 定义 4 节点线性流水线
- ✅ 竞品发现改用 Tavily Search API
- ✅ LLM 分析改用 DeepSeek（LangChain ChatOpenAI 兼容接口）
- ✅ Firecrawl 爬取保留原版 SDK 调用方式
