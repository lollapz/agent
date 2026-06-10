# 智能调研报告生成Agent

> Deep Research Agent based on LangGraph

基于 **LangGraph + DeepSeek + Tavily + Firecrawl** 构建的 Deep Research Agent，支持用户输入调研主题、公司 URL 或业务描述，自动完成需求解析、联网搜索、网页抓取、多源信息整合、数据充分性审查、补充检索以及结构化调研报告生成。

> 竞品分析 / 行业调研 / 技术调研 / 市场研究 均可作为应用场景，不再仅限于竞品分析。

## 项目价值

传统搜索只能返回离散信息，本项目基于 LangGraph 构建可循环执行的 Research Agent Workflow，实现需求解析、联网搜索、网页抓取、数据验证、补充检索与结构化报告生成全流程自动化，提高调研效率与信息完整性。

## 核心亮点

- 基于 **LangGraph** 构建可循环执行的 Research Agent Workflow
- 支持 **Conditional Edge** 条件路由与状态驱动决策
- 集成 **Tavily + Firecrawl** 实现联网搜索与网页抓取
- 引入 **Review** 机制自动评估数据充分性
- 支持自动补充搜索与多轮信息累积
- 基于 **DeepSeek** 自动生成结构化调研报告
- 支持 **visited_urls** 去重与失败重试机制
- 支持调研主题、企业分析、行业研究、竞品分析等场景

## 核心能力

| 能力 | 说明 |
|------|------|
| 🔁 Research Agent 循环 | 数据不足时自动补充搜索，最多 2 轮 |
| 📋 数据充分性审查 | 逐对象多维度评估，数据不完整自动补充 |
| 🚫 visited_urls 去重 | 不重复抓取相同 URL |
| 📊 多轮数据累积 | 每轮搜索追加数据，不覆盖已有结果 |
| 📝 DeepSeek 报告生成 | 结构化中文 Markdown 报告（含数据完整性说明） |

## 架构

```
用户输入 (主题/URL/描述)
    │
    ▼
┌──────────────────┐
│    discover      │ ← Tavily Search（首轮 + 补充轮）
│  信息发现节点     │    去重、上限 10 URL
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
│  数据汇聚节点     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐         ┌──────────────────────┐
│     review       │ ──────→ │ prepare_next_search  │
│  数据审查节点     │  不充分  │  递增 iteration_count │
│                  │         └──────────┬───────────┘
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
| 联网搜索 | Tavily Search API |
| 网页抓取 | Firecrawl (extract + Pydantic Schema) |
| 数据建模 | Pydantic |
| 数据分析 | Pandas |
| 服务层 | FastAPI |
| 界面层 | Streamlit |
| 环境管理 | uv |

## 快速启动

```bash
# 1. 安装依赖
uv sync

# 2. Streamlit 前端
uv run streamlit run main.py

# 3. FastAPI 后端
uv run python api.py
```

## 使用方式

1. 在侧边栏填入 API Key：
   - **DeepSeek API Key**（必填）— 报告生成 + Review 评估
   - **Tavily API Key**（必填）— 联网搜索发现 + 补充搜索
   - **Firecrawl API Key**（必填）— 网页抓取与结构化提取
2. 输入调研主题 URL 或描述
3. 点击「🚀 开始调研」
4. 系统自动执行多轮搜索 — 审查 — 补充搜索循环
5. 查看执行摘要（轮次、URL 数、数据评估、补充搜索次数）
6. 展开「数据审查详情」查看评估和补充搜索 Query
7. 查看结构化对比表格和 DeepSeek 调研报告

## 项目结构

```
deep-research-agent/
├── main.py          # Streamlit 入口 + UI 渲染
├── graph.py         # LangGraph StateGraph（6 节点 + 条件边 + 循环边）
│                    #   discover / scrape / compare / review
│                    #   prepare_next_search / analyze
│                    #   route_after_review（条件路由）
├── models.py        # Pydantic DataSchema（11 字段）
├── api.py           # FastAPI 后端服务
├── pyproject.toml   # uv 项目配置与依赖声明
└── README.md        # 本文件
```

## State 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| company_url | str | 用户输入的目标 URL |
| company_description | str | 用户输入的调研主题描述 |
| competitor_urls | List[str] | 发现的资料 URL（多轮累积，上限 10） |
| competitor_data | List[dict] | 结构化调研数据（多轮累积） |
| analysis_report | str | Markdown 调研报告 |
| error | Optional[str] | 错误信息 |
| iteration_count | int | 当前补充搜索轮数 |
| max_iterations | int | 最大补充搜索轮数 |
| review_result | dict | Review 评估结果 |
| missing_info | List[str] | 缺失字段列表 |
| search_queries | List[str] | 下一轮搜索 query |
| is_sufficient | bool | 数据是否足够 |
| visited_urls | List[str] | 已抓取 URL（去重） |

## 改造历程

### v2 — Research Agent 循环（当前版本）
- ✅ 新增 review_node（数据充分性评估）
- ✅ 新增 prepare_next_search_node（迭代计数）
- ✅ 新增 route_after_review（条件路由）
- ✅ discover_node 支持首轮 + 补充搜索双模式
- ✅ scrape_node 支持 visited_urls 去重 + 失败不中断
- ✅ compare_node 支持多轮累积数据
- ✅ analyze_node 报告中标注数据缺失项
- ✅ DataSchema 扩展至 11 字段
- ✅ 循环边：prepare_next_search → discover

### v1 — LangGraph 重构
- ❌ 删除 Agno Agent / Agent Team 全部依赖
- ✅ 改用 LangGraph StateGraph 定义节点流水线
- ✅ 搜索改用 Tavily Search API
- ✅ LLM 改用 DeepSeek（LangChain ChatOpenAI 兼容接口）
- ✅ Firecrawl 保留原版 SDK 调用方式
