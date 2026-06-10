"""FastAPI 服务 —— 竞品情报分析 Agent API

启动时从环境变量加载 API Keys，编译 LangGraph StateGraph 一次。
提供同步风格的 /api/v1/research 端点，内部使用 asyncio.to_thread 异步执行。
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from graph import build_graph, set_graph_config


# ---- Pydantic 模型 ----

class ResearchRequest(BaseModel):
    """竞品分析请求"""
    company_url: Optional[str] = Field(
        default=None,
        description="公司官网 URL",
        examples=["https://example.com"],
    )
    company_description: Optional[str] = Field(
        default=None,
        description="公司业务描述",
        examples=["AI-powered email marketing platform"],
    )
    max_iterations: Optional[int] = Field(
        default=2,
        ge=1,
        le=5,
        description="最大补充搜索轮数（1-5，默认 2）",
    )


class ResearchResponse(BaseModel):
    """竞品分析响应"""
    status: str = Field(description="执行状态：success 或 error")
    analysis_report: str = Field(
        default="",
        description="AI 生成的 Markdown 战略分析报告",
    )
    competitor_urls: list[str] = Field(
        default_factory=list,
        description="发现的竞品 URL 列表",
    )
    competitor_data: list[dict] = Field(
        default_factory=list,
        description="结构化竞品数据",
    )
    iteration_count: int = Field(
        default=0,
        description="执行轮数（含首轮）",
    )
    is_sufficient: bool = Field(
        default=False,
        description="数据是否满足分析要求",
    )
    review_result: dict = Field(
        default_factory=dict,
        description="数据审查详情",
    )
    missing_info: list[str] = Field(
        default_factory=list,
        description="缺失信息字段",
    )
    visited_urls: list[str] = Field(
        default_factory=list,
        description="已抓取的 URL",
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息（如有）",
    )


# ---- 启动生命周期 ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载配置、编译 Graph；关闭时清理"""
    print("[startup] Loading environment variables...")
    load_dotenv()

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")

    missing = []
    if not deepseek_api_key:
        missing.append("DEEPSEEK_API_KEY")
    if not tavily_api_key:
        missing.append("TAVILY_API_KEY")
    if not firecrawl_api_key:
        missing.append("FIRECRAWL_API_KEY")
    if missing:
        print(f"[startup] WARNING: missing env vars: {', '.join(missing)}")

    print("[startup] Injecting graph config...")
    set_graph_config({
        "deepseek_api_key": deepseek_api_key,
        "tavily_api_key": tavily_api_key,
        "firecrawl_api_key": firecrawl_api_key,
    })

    print("[startup] Compiling StateGraph...")
    app.state.graph = build_graph()
    print("[startup] API ready.")

    yield

    print("[shutdown] API server shutting down.")


app = FastAPI(
    title="Competitor Intelligence Agent API",
    description="基于 LangGraph + DeepSeek + Tavily + Firecrawl 的竞品情报分析 API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---- 端点 ----

@app.get("/health")
async def health_check():
    """服务健康检查"""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    """启动竞品情报分析。

    Research Agent 流水线:
    discover -> scrape -> compare -> review -> [analyze | prepare_next_search loop]
    """
    if not request.company_url and not request.company_description:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请提供 company_url 或 company_description（至少一个）",
        )

    initial_state = {
        "company_url": request.company_url or "",
        "company_description": request.company_description or "",
        "competitor_urls": [],
        "competitor_data": [],
        "analysis_report": "",
        "error": None,
        "iteration_count": 0,
        "max_iterations": request.max_iterations or 2,
        "review_result": {},
        "missing_info": [],
        "search_queries": [],
        "is_sufficient": False,
        "visited_urls": [],
    }

    try:
        result = await asyncio.to_thread(
            app.state.graph.invoke, initial_state
        )
        return ResearchResponse(
            status="success" if not result.get("error") else "error",
            analysis_report=result.get("analysis_report", ""),
            competitor_urls=result.get("competitor_urls", []),
            competitor_data=result.get("competitor_data", []),
            iteration_count=result.get("iteration_count", 0),
            is_sufficient=result.get("is_sufficient", False),
            review_result=result.get("review_result", {}),
            missing_info=result.get("missing_info", []),
            visited_urls=result.get("visited_urls", []),
            error=result.get("error"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析执行失败: {str(e)}",
        )


# ---- 直接运行 ----

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
