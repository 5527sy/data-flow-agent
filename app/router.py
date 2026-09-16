"""Agent① 范式路由器 —— 双通道判定

📏 规则通道：关键词表，稳定可解释，永不宕机
🤖 LLM 通道：DeepSeek + LangChain 结构化输出（with_structured_output → pydantic）
✅ 放行规则：两通道一致且置信度 >=0.7；不一致或低置信 → 给澄清问题，绝不硬猜
"""
import os

from .state import PARADIGM2TEMPLATE, ParadigmDecision

LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

CONFIDENCE_GATE = 0.7   # 低于此值必须澄清

# ── 规则通道：关键词表（生产中会扩成带权规则库）──────────────────
_RULES = [
    ("classification", ["名单", "潜在", "开通", "响应", "流失预测", "违约", "逾期", "营销名单", "找出一批"]),
    ("clustering", ["分群", "细分", "聚类", "分层", "画像", "分成几类"]),
    ("attribution", ["为什么", "原因", "归因", "因素", "驱动", "导致"]),
    ("text2sql", ["统计", "查询", "多少", "占比", "报表", "余额"]),
]

DEFAULT_CLARIFY = ["你期望的产出是『打分排序的名单』，还是『先分群看看结构』？",
                   "数据里是否已有标注好的目标列（如：是否已开通）？"]


def rule_channel(text: str) -> dict:
    """📏 规则通道：命中关键词 → 范式；都不命中 → text2sql 兜底（最安全）"""
    for paradigm, keywords in _RULES:
        hits = [k for k in keywords if k in text]
        if hits:
            return {"paradigm": paradigm, "hits": hits, "confidence": 0.75}
    return {"paradigm": "text2sql", "hits": [], "confidence": 0.5}


def _get_llm():
    """配置了 Key 且装了 langchain-openai 才返回 LLM，否则走单通道 Mock"""
    if not LLM_API_KEY:
        return None
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=0.1,
    )


_LLM_SYSTEM = """你是银行数据分析需求路由器。判断用户需求属于哪类分析范式，只输出结构化结果。
判定规则：
- 有历史标签（已开通/已流失/已响应）且要"名单/排名/评分" → classification
- 无标签，要"分群/细分/分层画像" → clustering
- 问"为什么/哪些因素导致" → attribution
- 只查数、算指标、做报表 → text2sql
样例："根据已流失客户特征找出可能流失名单" → classification（有标签+要名单）
置信度 confidence 取 0~1，没把握就给低分。"""


def llm_channel(text: str) -> dict | None:
    """🤖 LLM 通道：结构化输出直出 ParadigmDecision；任何异常返回 None（降级）"""
    llm = _get_llm()
    if llm is None:
        return None
    try:
        result: ParadigmDecision = llm.with_structured_output(ParadigmDecision).invoke(
            [{"role": "system", "content": _LLM_SYSTEM},
             {"role": "user", "content": text}]
        )
        if not ParadigmDecision.valid_paradigm(result.paradigm):
            return None
        d = result.model_dump()
        d["matched_template"] = PARADIGM2TEMPLATE.get(d["paradigm"], "T5_text2sql")
        d["confidence"] = max(0.0, min(1.0, d["confidence"]))
        return d
    except Exception as e:                     # 网络/限流/输出不合法 → 降级
        print(f"[llm_channel] 降级：{e}")
        return None


def decide(user_request: str) -> dict:
    """双通道裁决入口：analyze 节点调用，返回完整判定（含双通道对照）"""
    rule = rule_channel(user_request)
    llm = llm_channel(user_request)

    if llm is None:                            # 单通道（无 Key / LLM 挂了）
        final = {
            "paradigm": rule["paradigm"],
            "confidence": rule["confidence"],
            "rationale": f"（规则通道）命中关键词：{'、'.join(rule['hits']) or '无，走查数兜底'}",
            "clarifying_questions": [],
            "source": "mock",
        }
        agreed = None                          # 只有一个裁判，谈不上一致
    else:
        agreed = llm["paradigm"] == rule["paradigm"]
        if agreed:
            final = dict(llm)
            final["rationale"] = (f"双通道一致。LLM：{llm['rationale']}；"
                                  f"规则通道命中：{'、'.join(rule['hits'])}")
            final["confidence"] = max(final["confidence"], 0.9)   # 双确认给高置信
            final["source"] = "llm+dual"
        else:                                  # 裁判打架 → 压低置信度，必须澄清
            final = dict(llm)
            final["confidence"] = min(final["confidence"], 0.6)
            final["rationale"] += f"（⚠ 与规则通道结论 {rule['paradigm']} 不一致）"
            final["source"] = "llm"

    decision = {
        "paradigm": final["paradigm"],
        "confidence": round(final["confidence"], 2),
        "rationale": final.get("rationale", ""),
        "clarifying_questions": final.get("clarifying_questions", []),
        "matched_template": PARADIGM2TEMPLATE.get(final["paradigm"], "T5_text2sql"),
        "source": final.get("source", "mock"),
        "dual_channel": {
            "rule": {"paradigm": rule["paradigm"], "hits": rule["hits"]},
            "llm": (llm or {}).get("paradigm"),
            "agreed": agreed,
        },
    }
    # 放行规则：置信度不足 → 追加澄清问题，绝不硬猜
    if decision["confidence"] < CONFIDENCE_GATE and not decision["clarifying_questions"]:
        decision["clarifying_questions"] = DEFAULT_CLARIFY
    return decision
