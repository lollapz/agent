"""Pydantic 数据模型 —— 结构化信息提取

扩展字段支持 Review 节点多维度数据充分性评估。
"""

from pydantic import BaseModel, Field
from typing import List


class CompetitorDataSchema(BaseModel):
    """竞品公司数据模型，用于 Firecrawl 结构化提取"""
    company_name: str = Field(description="公司名称")
    website: str = Field(description="公司官方网站 URL")
    product_description: str = Field(description="产品/服务的详细描述、核心业务")
    pricing: str = Field(description="定价详情、套餐和层级，免费/付费方案")
    core_features: List[str] = Field(description="产品/服务的主要功能和差异化能力")
    target_customers: str = Field(description="目标客户群体、行业和用户画像")
    positioning: str = Field(description="市场定位、竞争优势和品牌策略")
    strengths: List[str] = Field(description="公司或产品的主要优势和核心竞争力")
    weaknesses: List[str] = Field(description="公司或产品的主要劣势和改进空间")
    tech_stack: List[str] = Field(description="使用的技术、框架和工具栈")
    customer_feedback: str = Field(description="客户评价、评论和反馈汇总")
