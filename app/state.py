"""DataFlow Agent · 共享状态与契约

- FlowState：LangGraph 图的共享状态（七卡片流程的单一数据源）
- ParadigmDecision：路由器的结构化输出"合同"（pydantic 强校验）
"""
from typing import TypedDict

from pydantic import BaseModel, Field

# 支持的分析范式（M1 收窄到四类）
PARADIGMS = ("classification", "clustering", "attribution", "text2sql")

PARADIGM_ZH = {
    "classification": "分类分析（响应预测 / 打分出名单）",
    "clustering": "聚类分析（客户细分）",
    "attribution": "归因分析（找原因）",
    "text2sql": "取数问答（查数 / 报表）",
}

PARADIGM2TEMPLATE = {
    "classification": "T1_response_prediction",
    "clustering": "T2_customer_segmentation",
    "attribution": "T3_attribution",
    "text2sql": "T5_text2sql",
}


class ParadigmDecision(BaseModel):
    """路由器输出合同：LLM 的结构化输出必须过这道校验"""

    paradigm: str
    confidence: float
    rationale: str = ""
    clarifying_questions: list[str] = Field(default_factory=list)

    @classmethod
    def valid_paradigm(cls, v: str) -> bool:
        return v in PARADIGMS


class FlowState(TypedDict, total=False):
    """LangGraph 共享状态：所有卡片读写这一份"""

    run_id: str
    user_request: str          # 用户原始需求
    decision: dict             # 路由判定（双通道结论，dict 方便 JSON 化）
    step: int                  # 当前卡片编号 1~7
    reroute: bool              # 用户点了"重新输入"→ 回到路由
    card2_note: str            # ②样本设计卡片的占位说明
