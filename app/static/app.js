/* DataFlow Agent M1 · 前端逻辑（零依赖原生 JS）
   卡片式向导：每张卡片 = LangGraph 图在某个 interrupt 点的暂停态
   点"确认" = Command(resume) 续跑图；点"重新输入" = 带新文本回路由节点 */
const STEPS = ["需求路由", "样本设计", "取数上传", "数据体检", "清洗特征", "训练评估", "名单输出"];
let state = { runId: null, step: 1 };

const $ = (id) => document.getElementById(id);

/* ── 步骤导航条 ── */
function renderStepper() {
  $("stepper").innerHTML = STEPS.map((name, i) => {
    const n = i + 1;
    const cls = n < state.step ? "done" : (n === state.step ? "current" : "");
    return `<span class="step ${cls}">${n}. ${name}</span>`;
  }).join("");
}

/* ── 卡片切换（滑入动画）── */
function showCard(n) {
  document.querySelectorAll(".card").forEach(c => c.classList.remove("active"));
  $(`card${n}`).classList.add("active");
  renderStepper();
}

/* ── API ── */
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/* ── 提交需求 ── */
async function send() {
  const m = $("reqInput").value.trim();
  if (!m) return;
  $("sendBtn").disabled = true; $("loading").classList.remove("hidden");
  try {
    const s = await api("/api/chat", { message: m, run_id: state.runId });
    applySnapshot(s);
  } catch (e) { alert("请求失败：" + e.message); }
  $("sendBtn").disabled = false; $("loading").classList.add("hidden");
}

/* ── 拍板 ── */
async function decide(action) {
  const message = $("reqInput").value.trim();
  $("decisionBox").innerHTML = "<p class='hint'>⏳ 图执行中…</p>";
  try {
    const s = await api("/api/confirm", { run_id: state.runId, action, message });
    applySnapshot(s);
  } catch (e) { alert("请求失败：" + e.message); }
}

/* ── 渲染快照 ── */
function applySnapshot(s) {
  state.runId = s.run_id;
  state.step = s.step || 1;
  if (state.step >= 2) {                       // 进入卡片②
    $("card2Text").textContent = s.card2_note || "";
    showCard(2);
    return;
  }
  showCard(1);
  renderDecision(s.decision);
}

function renderDecision(d) {
  if (!d) return;
  const dual = d.dual_channel || {};
  const llmVerdict = dual.llm ? dual.llm : "未启用（Mock 模式）";
  const agreedText = dual.agreed === true ? "<span class='ok'>✓ 一致</span>"
    : dual.agreed === false ? "<span class='bad'>✗ 不一致</span>"
    : "—（单通道）";
  const zh = {
    classification: "分类分析（响应预测 / 打分出名单）",
    clustering: "聚类分析（客户细分）",
    attribution: "归因分析（找原因）",
    text2sql: "取数问答（查数 / 报表）",
  }[d.paradigm] || d.paradigm;
  const conf = Math.round(d.confidence * 100);
  const needClarify = (d.clarifying_questions || []).length > 0 && d.confidence < 0.7;

  const clarifyHtml = needClarify
    ? `<div class="warn"><b>⚠️ 置信度不足（${conf}% &lt; 70%），请补充信息后点「重新输入」：</b><br>` +
      d.clarifying_questions.map(q => "· " + q).join("<br>") + "</div>"
    : "";

  $("decisionBox").innerHTML = `
    <h2 style="margin-bottom:6px">📋 路由判定结果</h2>
    <div class="metric"><span>范式</span><b>${zh}</b></div>
    <div class="metric"><span>置信度</span><div class="bar"><i style="width:${conf}%"></i></div><b>${conf}%</b></div>
    <table class="mini">
      <tr><th>裁判</th><th>结论</th></tr>
      <tr><td>📏 规则通道</td><td>${dual.rule?.paradigm || "-"}（命中：${(dual.rule?.hits || []).join("、") || "无"}）</td></tr>
      <tr><td>🤖 LLM 通道</td><td>${llmVerdict}</td></tr>
      <tr><td>双通道裁决</td><td>${agreedText}</td></tr>
      <tr><td>匹配模板</td><td>${d.matched_template}</td></tr>
    </table>
    <p class="rationale">💡 ${d.rationale}</p>
    ${clarifyHtml}
    <div class="row">
      <button id="confirmBtn" class="primary">✅ 确认范式，下一步</button>
      <button id="rerouteBtn">🔁 重新输入</button>
      <span class="hint">run: ${state.runId}</span>
    </div>`;
  $("confirmBtn").onclick = () => decide("confirm");
  $("rerouteBtn").onclick = () => { $("reqInput").focus(); decide("reroute"); };
}

/* ── 初始化 ── */
$("sendBtn").onclick = send;
$("backBtn").onclick = () => showCard(1);
renderStepper();
fetch("/health").then(r => r.json()).then(h => {
  $("connState").textContent = `后端已连接 · ${h.app} · ${h.milestone}`;
}).catch(() => { $("connState").textContent = "❌ 后端未连接"; });
