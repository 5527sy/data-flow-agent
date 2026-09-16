"""DataFlow Agent · LangGraph 流程图（M1：路由卡片 → 人工拍板 → 样本设计占位）

图结构：
    START → analyze（双通道路由）→ confirm_gate（interrupt：等人工拍板）
        ├─ confirm → card2（②样本设计占位）→ END
        └─ reroute → 回到 analyze（带新需求文本）

interrupt() = 卡片式交互的本质：图在这里暂停，前端渲染卡片，
点"确认"用 Command(resume=...) 续跑，点"重新输入"带着新文本回到路由。
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .router import decide
from .state import FlowState

# M1 用内存检查点（重启即清空）；M5 升级 SqliteSaver 实现跨天快照
checkpointer = MemorySaver()


def analyze_node(state: FlowState) -> dict:
    """① 需求路由：双通道判定"""
    decision = decide(state["user_request"])
    return {"decision": decision, "step": 1}


def confirm_gate_node(state: FlowState) -> dict:
    """人工拍板闸门：interrupt 暂停 → 前端渲染判定卡片 → 等待用户动作"""
    action = interrupt({"card": 1, "decision": state["decision"]})
    if action.get("action") == "confirm":
        return {"step": 2, "reroute": False}
    # 重新输入：带着新文本回到路由节点
    return {"reroute": True, "user_request": action.get("message") or state["user_request"]}


def card2_node(state: FlowState) -> dict:
    """② 样本设计卡片占位（M1 下一迭代实现）"""
    return {"card2_note": (
        "范式已锁定，下一步将进入《样本设计方案》：观察期/表现期/正负标签/排除规则。"
        "（M1 下一迭代实现）"
    )}


def route_after_gate(state: FlowState) -> str:
    return "analyze" if state.get("reroute") else "card2"


def build_flow():
    g = StateGraph(FlowState)
    g.add_node("analyze", analyze_node)
    g.add_node("confirm_gate", confirm_gate_node)
    g.add_node("card2", card2_node)
    g.add_edge(START, "analyze")
    g.add_edge("analyze", "confirm_gate")
    g.add_conditional_edges("confirm_gate", route_after_gate,
                            {"card2": "card2", "analyze": "analyze"})
    g.add_edge("card2", END)
    return g.compile(checkpointer=checkpointer)


flow = build_flow()
