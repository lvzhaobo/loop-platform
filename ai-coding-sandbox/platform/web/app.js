/* MumuLoop Loop Console —— 前端逻辑（原生 JS，零构建） */

const $ = (s) => document.querySelector(s);

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function fetchJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}

const RESULT = {
  closed: { cls: "ok", label: "已收敛" },
  pending_fix: { cls: "warn", label: "待修复" },
  escalate: { cls: "err", label: "需人工介入" },
};

function badge(result) {
  const m = RESULT[result] || { cls: "dim", label: result || "-" };
  return `<span class="badge ${m.cls}">${esc(m.label)}</span>`;
}

function bars(rows, opts = {}) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return rows.map((r) => `
    <div class="bar-row ${opts.narrow ? "narrow" : ""}">
      <span class="lbl">${esc(r.label)}</span>
      <span class="bar ${opts.warn ? "warn" : ""}"><i style="width:${Math.round((r.count / max) * 100)}%"></i></span>
      <span class="n">${r.count}</span>
    </div>`).join("");
}

/* ---------- 概览 ---------- */

async function viewOverview(el) {
  const d = await fetchJSON("/api/overview");
  const scope = `数据范围：${d.files} 个日志文件，共 ${d.rounds} 轮`
    + (d.demo_rounds ? `（含演示数据 ${d.demo_rounds} 轮）` : "");
  el.innerHTML = `
    <div class="kpis">
      <div class="kpi"><div class="k">任务数</div><div class="v">${d.tasks}</div></div>
      <div class="kpi"><div class="k">总轮数</div><div class="v">${d.rounds}</div></div>
      <div class="kpi"><div class="k">收敛</div><div class="v">${d.converged}/${d.tasks}</div></div>
      <div class="kpi"><div class="k">拦截累计</div><div class="v">${d.total_hits}</div></div>
      <div class="kpi"><div class="k">有效拦截率</div>
        <div class="v">${d.effective_rate == null ? "-" : d.effective_rate + "%"}</div>
        <div class="x">末轮残留 ${d.pending}</div></div>
    </div>
    <div class="grid-2">
      <div class="panel">
        <h2>规则命中排行</h2>
        ${d.by_rule.length
          ? bars(d.by_rule.map((r) => ({ label: r.rule, count: r.count })))
          : '<div class="empty">暂无命中记录</div>'}
      </div>
      <div class="panel">
        <h2>按天拦截</h2>
        ${d.by_day.length
          ? bars(d.by_day.map((r) => ({ label: r.day, count: r.count })), { narrow: true, warn: true })
          : '<div class="empty">暂无记录</div>'}
      </div>
    </div>
    <div class="panel">
      <h2>最近轮次</h2>
      ${d.recent.length ? `<table class="tbl">
        <thead><tr><th>时间</th><th>任务</th><th>轮</th><th>违规</th><th>结果</th></tr></thead>
        <tbody>${d.recent.map((e) => `<tr>
          <td class="mono">${esc(e.ts)}</td>
          <td class="mono">${esc(e._task)}</td>
          <td class="mono">${e.round}</td>
          <td class="mono">${e.violations}</td>
          <td>${badge(e.result)}</td>
        </tr>`).join("")}</tbody>
      </table>` : '<div class="empty">暂无日志（先将 loop 日志放入 platform/data/logs/）</div>'}
      <div class="note">${esc(scope)}；口径与课程素材 aggregate.py 一致。</div>
    </div>`;
}

/* ---------- 运行 ---------- */

async function viewRuns(el) {
  const runs = await fetchJSON("/api/runs");
  if (!runs.length) {
    el.innerHTML = '<div class="panel"><div class="empty">暂无运行记录（先将 loop 日志放入 platform/data/logs/）</div></div>';
    return;
  }
  el.innerHTML = `
    <div class="panel">
      <h2>任务列表（点击行展开轮次明细）</h2>
      <table class="tbl">
        <thead><tr><th>任务</th><th>轮数</th><th>拦截累计</th><th>末轮违规</th><th>状态</th><th>最近时间</th></tr></thead>
        <tbody>
        ${runs.map((t, i) => `
          <tr class="task-row" data-i="${i}">
            <td class="mono">${esc(t.task)}</td>
            <td class="mono">${t.rounds}</td>
            <td class="mono">${t.total_hits}</td>
            <td class="mono">${t.entries[t.entries.length - 1].violations}</td>
            <td>${badge(t.last_result)}</td>
            <td class="mono muted">${esc(t.last_ts)}</td>
          </tr>
          <tr class="detail-row" data-detail="${i}">
            <td colspan="6"><div class="detail-inner">
              <table class="tbl">
                <thead><tr><th>轮</th><th>时间</th><th>违规</th><th>规则明细</th><th>动作</th><th>结果</th></tr></thead>
                <tbody>${t.entries.map((e) => `<tr>
                  <td class="mono">${e.round}</td>
                  <td class="mono">${esc(e.ts)}</td>
                  <td class="mono">${e.violations}</td>
                  <td class="mono">${esc(Object.entries(e.byRule || {}).map(([k, n]) => k + "×" + n).join(" ") || "—")}</td>
                  <td class="mono">${esc(e.action || "none")}</td>
                  <td>${badge(e.result)}</td>
                </tr>`).join("")}</tbody>
              </table>
            </div></td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  el.querySelectorAll(".task-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      const d = el.querySelector(`[data-detail="${tr.dataset.i}"]`);
      if (d) d.classList.toggle("open");
    });
  });
}

/* ---------- 检查 ---------- */

async function viewChecks(el) {
  const d = await fetchJSON("/api/checks");
  const total = d.by_rule.reduce((s, r) => s + r.count, 0);
  el.innerHTML = `
    <div class="grid-2">
      <div class="panel">
        <h2>规则命中统计（累计 ${total} 次）</h2>
        ${d.by_rule.length ? `<table class="tbl">
          <thead><tr><th>规则</th><th>命中</th><th>占比</th></tr></thead>
          <tbody>${d.by_rule.map((r) => `<tr>
            <td class="mono">${esc(r.rule)}</td>
            <td class="mono">${r.count}</td>
            <td class="mono muted">${total ? Math.round((r.count * 100) / total) : 0}%</td>
          </tr>`).join("")}</tbody>
        </table>` : '<div class="empty">暂无命中</div>'}
        <div class="note">规则语义与判据见课程素材 <span class="chip">demo-project/rules/</span>（规则治理为后续演进）。</div>
      </div>
      <div class="panel">
        <h2>违规轮次（按时间倒序）</h2>
        ${d.seq.length ? `<table class="tbl">
          <thead><tr><th>时间</th><th>任务</th><th>轮</th><th>违规</th><th>明细</th></tr></thead>
          <tbody>${d.seq.map((e) => `<tr>
            <td class="mono">${esc(e.ts)}</td>
            <td class="mono">${esc(e.task)}</td>
            <td class="mono">${e.round}</td>
            <td class="mono">${e.violations}</td>
            <td class="mono muted">${esc(Object.entries(e.byRule).map(([k, n]) => k + "×" + n).join(" "))}</td>
          </tr>`).join("")}</tbody>
        </table>` : '<div class="empty">暂无违规轮次</div>'}
      </div>
    </div>`;
}

/* ---------- 工单 ---------- */

async function viewTickets(el) {
  const d = await fetchJSON("/api/tickets");
  el.innerHTML = `
    <div class="panel">
      <h2>待处理（当前未收敛任务）</h2>
      ${d.open.length ? `<table class="tbl">
        <thead><tr><th>任务</th><th>轮数</th><th>状态</th></tr></thead>
        <tbody>${d.open.map((t) => `<tr>
          <td class="mono">${esc(t.task)}</td>
          <td class="mono">${t.rounds}</td>
          <td>${badge(t.status)}</td>
        </tr>`).join("")}</tbody>
      </table>`
        : '<div class="empty">无待处理票据——当前所有任务已收敛</div>'}
    </div>
    <div class="panel">
      <h2>历史提票记录（feedback_written）</h2>
      ${d.history.length ? `<table class="tbl">
        <thead><tr><th>时间</th><th>任务</th><th>轮</th><th>违规</th><th>修正指令文件</th></tr></thead>
        <tbody>${d.history.map((h) => `<tr>
          <td class="mono">${esc(h.ts)}</td>
          <td class="mono">${esc(h.task)}</td>
          <td class="mono">${h.round}</td>
          <td class="mono">${h.violations}</td>
          <td class="mono">${esc(h.feedback)}</td>
        </tr>`).join("")}</tbody>
      </table>` : '<div class="empty">暂无提票记录</div>'}
      <div class="note">工单桥：${esc(d.bridge)}。此页为票据视图雏形，数据从 Loop 日志推导。</div>
    </div>`;
}

/* ---------- Trace ---------- */

async function viewTrace(el) {
  const d = await fetchJSON("/api/trace");
  el.innerHTML = `
    <div class="panel">
      <h2>Trace 记录（原始日志，对标 dsh Trajectory 的简化版）</h2>
      ${d.entries.length ? `<table class="tbl">
        <thead><tr><th>时间</th><th>任务</th><th>轮</th><th>违规</th><th>动作</th><th>结果</th><th>来源文件</th></tr></thead>
        <tbody>${d.entries.map((e) => `<tr>
          <td class="mono">${esc(e.ts)}</td>
          <td class="mono">${esc(e._task)}</td>
          <td class="mono">${e.round}</td>
          <td class="mono">${e.violations}</td>
          <td class="mono">${esc(e.action || "none")}</td>
          <td>${badge(e.result)}</td>
          <td class="mono muted">${esc(e._file)}${e._demo ? ' <span class="badge dim">演示</span>' : ""}</td>
        </tr>`).join("")}</tbody>
      </table>` : '<div class="empty">暂无 Trace 记录</div>'}
      <div class="note">${d.langfuse_url
        ? `LangFuse 入口：<a class="link" href="${esc(d.langfuse_url)}" target="_blank" rel="noopener">${esc(d.langfuse_url)}</a>`
        : "LangFuse 入口未配置（启动时设置 LANGFUSE_URL 环境变量）。"}</div>
    </div>`;
}

/* ---------- 设置 ---------- */

async function viewSettings(el) {
  const d = await fetchJSON("/api/settings");
  const metrics = Object.entries(d.metrics)
    .map(([k, v]) => `<span class="k">${esc(k)}</span><span>${esc(v)}</span>`).join("");
  const todo = d.todo.map((t) => `<li>${esc(t)}</li>`).join("");
  el.innerHTML = `
    <div class="grid-2">
      <div class="panel">
        <h2>平台信息</h2>
        <div class="kv">
          <span class="k">版本</span><span>${esc(d.version)}</span>
          <span class="k">日志目录</span><span class="mono">${esc(d.logs_dir)}</span>
          <span class="k">日志文件</span><span class="mono">${d.files}</span>
          <span class="k">总轮数</span><span class="mono">${d.rounds}</span>
          <span class="k">服务端口</span><span class="mono">${d.port}</span>
          <span class="k">LangFuse</span><span class="mono">${esc(d.langfuse_url || "未配置")}</span>
        </div>
      </div>
      <div class="panel">
        <h2>度量口径</h2>
        <div class="kv">${metrics}</div>
        <div class="note">口径与课程素材 <span class="chip">aggregate.py</span> 完全一致。</div>
      </div>
    </div>
    <div class="panel">
      <h2>Harness 四象限</h2>
      <div class="quad">
        <div class="quad-cell">
          <div class="qh"><span class="axis">前馈 PRE</span><span class="qt">计算型 · 守卫</span></div>
          <div class="qd">AI 动手前确定性拦截，不靠 AI 自觉。</div>
          <ul>
            <li>三类守卫：路径 / 命令 / 参数；三种权限：禁止 / 审批 / 自动</li>
            <li>实操：梳理禁止清单与审批清单</li>
          </ul>
          <div class="qf">落点 <span class="chip">AGENTS.md 硬约束</span><span class="chip">规则表带机器检查 ID</span></div>
        </div>
        <div class="quad-cell">
          <div class="qh"><span class="axis">前馈 PRE</span><span class="qt">推理型 · 注入</span></div>
          <div class="qd">规范注入上下文，AI 读到后自己判断。</div>
          <ul>
            <li>载体分工：Rules / Skills / AGENTS.md；Rule 格式：规则 + 正例 + 反例</li>
            <li>实操：写 Rule 并验证 AI 遵守</li>
          </ul>
          <div class="qf">落点 <span class="chip">注入层</span><span class="chip">边界说明 · 审查清单</span></div>
        </div>
        <div class="quad-cell post">
          <div class="qh"><span class="axis">反馈 POST</span><span class="qt">计算型 · 传感器</span></div>
          <div class="qd">确定性、快速、每次变更运行；查"有没有"。</div>
          <ul>
            <li>手段：Linter → pytest → 架构检查；约定：一条 Rule 一条检查</li>
            <li>实操：为 Rule 写 pytest 检查并验证</li>
          </ul>
          <div class="qf">落点 <span class="chip">检查层 check.py</span><span class="chip">calibrate 红绿测</span></div>
        </div>
        <div class="quad-cell post">
          <div class="qh"><span class="axis">反馈 POST</span><span class="qt">推理型 · 传感器</span></div>
          <div class="qd">计算型查"有没有"，推理型查"好不好"。</div>
          <ul>
            <li>手段：AI 审查代码 + 人工评估审查质量；人工抽查 ≥ 20%</li>
            <li>实操：机检盲区清单</li>
          </ul>
          <div class="qf">落点 <span class="chip">审查层</span><span class="chip">抽查记录</span></div>
        </div>
      </div>
      <div class="quad-loop">
        <span class="lk">闭环层</span>
        <span><b>回路本体，不属于任何象限</b>——失败 → 修正 → 复检 → 留痕四要素，JSONL 旁路日志，max-rounds 3 轮不收敛转 escalate。</span>
      </div>
      <div class="note">四象限是归类工具：先做无 Harness 基线（收翻车），把翻车点逐条分类，识别 P0 缺口并指定 Owner。</div>
    </div>
    <div class="panel">
      <h2>待接入（演进方向）</h2>
      <ul class="plain">${todo}</ul>
    </div>`;
}

/* ---------- 路由与主题 ---------- */

const routes = {
  overview: { title: "概览", sub: "拦截 / 收敛 / 运行总览", render: viewOverview },
  runs: { title: "运行", sub: "任务与轮次", render: viewRuns },
  checks: { title: "检查", sub: "违规明细 / 按规则统计", render: viewChecks },
  tickets: { title: "工单", sub: "提票状态（工单桥未接入）", render: viewTickets },
  trace: { title: "Trace", sub: "采集轨迹（LangFuse 对接）", render: viewTrace },
  settings: { title: "设置", sub: "平台配置 · 度量口径 · Harness 四象限", render: viewSettings },
};

function applyTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("mumuloop-theme", t); } catch (e) { /* 忽略 */ }
  document.querySelectorAll("[data-theme-set]").forEach((b) =>
    b.classList.toggle("active", b.dataset.themeSet === t));
}

async function navigate() {
  const key = (location.hash.replace(/^#\//, "").split("?")[0]) || "overview";
  const route = routes[key] ? key : "overview";
  document.querySelectorAll("#menu a").forEach((a) =>
    a.classList.toggle("active", a.dataset.route === route));
  $("#page-title").textContent = routes[route].title;
  $("#page-sub").textContent = routes[route].sub;
  $("#page-meta").textContent = "载入 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const view = $("#view");
  view.innerHTML = '<div class="loading">加载中…</div>';
  try {
    await routes[route].render(view);
  } catch (err) {
    view.innerHTML = `<div class="panel"><div class="empty">加载失败：${esc(err.message)}（服务是否已启动？）</div></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  let stored = null;
  try { stored = localStorage.getItem("mumuloop-theme"); } catch (e) { /* 忽略 */ }
  applyTheme(stored === "dark" ? "dark" : "light");
  document.querySelectorAll("[data-theme-set]").forEach((b) =>
    b.addEventListener("click", () => applyTheme(b.dataset.themeSet)));
  window.addEventListener("hashchange", navigate);
  navigate();
});
