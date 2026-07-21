/* harness-5 玻璃盒控制台 · 前端 Mock(预留后端接口)
 *
 * 【后端接通指南】全部"真读写/真运行"都收敛在下方 API 对象里。
 * 将来用 Python http.server 实现这几个端点后,把 API 里的 Mock 换成 fetch 即可,页面其余不动:
 *    GET  /api/config        -> {constraints, facts}
 *    POST /api/config        <- {constraints, facts}   (写回真实文件)
 *    POST /api/run           <- {level, stuck}  -> 真实 subprocess 跑脚本, 回传 rounds/state
 */

// ============ 默认事实源(镜像真实 constraints.json / facts.json) ============
const DEFAULTS = {
  constraints: {
    language: "python", module: "mathkit.py",
    banned_patterns: ["eval(", "exec(", "os.system", "import os", "subprocess"],
    max_lines: 120,
    loop: { max_iterations: 5, max_cost: 100, cost_per_attempt: 20 },
  },
  facts: {
    module: "mathkit.py", min_functions: 4,
    functions: [
      { name: "add", signature: "add(a, b)" },
      { name: "is_prime", signature: "is_prime(n)" },
      { name: "fib", signature: "fib(n)" },
      { name: "factorial", signature: "factorial(n)" },
    ],
  },
};

// mock 模型真正会实现的函数 & 产物行数(用于让门禁结果"真实可信")
const IMPLEMENTED = ["add", "is_prime", "fib", "factorial"];
const MODULE_LINES = 30;
const REAL_HASH = "4964edbdd590a779de936f29ac9dcd090287f19fef1786b3154b2da828b14fee";

// 层 → 脚本文件(运行面与跟练面公用)
const LEVEL_FILE = { L0: "l0_single/run.py", L1: "l1_harness/gate.py", L2: "l2_loop/loop.py",
  L3: "l3_guardrails/loop_guarded.py", L4: "l4_determinism/determinism.py" };

// ============ API 数据层(Mock;后端接通时替换实现) ============
const API = {
  async getConfig() {
    // TODO backend: return (await fetch('/api/config')).json()
    return JSON.parse(JSON.stringify(DEFAULTS));
  },
  async saveConfig(cfg) {
    // TODO backend: fetch('/api/config',{method:'POST',body:JSON.stringify(cfg)})
    return { ok: true, mock: true };
  },
  async run(level, opts) {
    // TODO backend: return (await fetch('/api/run',{method:'POST',body:...})).json()
    return simulateRun(level, STATE.config, opts || {});
  },
};

// ============ 运行模拟(忠实反映真实脚本行为,且受 config 影响) ============
function verifyChecks(attempt, cfg, stuck) {
  const factNames = cfg.facts.functions.map((f) => f.name);
  const missing = factNames.filter((n) => !IMPLEMENTED.includes(n));
  const structOk = missing.length === 0;
  const linesOk = MODULE_LINES <= cfg.constraints.max_lines;
  const buggy = attempt <= 1 || stuck;
  // 只有"正确版 + 无多余函数需求"才可能测试全绿
  const testOk = !buggy && structOk;
  return [
    { name: "结构:模块文件存在", ok: true, detail: "" },
    { name: "结构:函数定义齐全", ok: structOk, detail: structOk ? "" : "缺失: " + missing.join(", ") },
    { name: "安全:无禁用模式", ok: true, detail: "" },
    { name: `规范:行数 ≤ ${cfg.constraints.max_lines}`, ok: linesOk, detail: `实际 ${MODULE_LINES}` },
    { name: "测试:unittest 全绿", ok: testOk, detail: testOk ? "" : (buggy ? "FAILED (failures=1)" : "缺函数,测试无法通过") },
  ];
}
const allOk = (checks) => checks.length > 0 && checks.every((c) => c.ok);

function consistencyCheck(cfg) {
  // facts 里的函数必须能在 spec.md 找到落点;spec 只写了原始 4 个
  const inSpec = ["add", "is_prime", "fib", "factorial"];
  const fails = cfg.facts.functions
    .filter((f) => !inSpec.includes(f.name))
    .map((f) => `facts 声明的函数 '${f.name}' 未在 spec.md 出现`);
  return { ok: fails.length === 0, fails };
}

function simulateRun(level, cfg, opts) {
  const stuck = !!opts.stuck;
  const res = { level, rounds: [], consistency: null, passed: false, stopReason: "", hashes: null };

  if (level === "L0") {
    res.rounds.push({ attempt: 1, cost: null, checks: [], note: "L0 无任何验收 —— 产物可能是错的,你无从得知" });
    res.stopReason = "L0 只生成,不验收(sample 下这版 factorial 是错的)";
    res.passed = null; // 无判定
    return res;
  }

  // L1~L4 都先跑自洽性
  res.consistency = consistencyCheck(cfg);
  if (!res.consistency.ok) {
    res.stopReason = "自洽性门禁未过(facts 与 spec 漂移),生成前即拦下";
    res.passed = false;
    return res;
  }

  if (level === "L1") {
    const checks = verifyChecks(1, cfg, stuck); // 单次尝试
    res.rounds.push({ attempt: 1, cost: null, checks });
    res.passed = allOk(checks);
    res.stopReason = res.passed ? "验收通过" : "L1 只发现不修复(去 L2 看闭环)";
    return res;
  }

  // L2 / L3 / L4:循环
  const g = cfg.constraints.loop;
  const maxIter = level === "L2" ? 8 : g.max_iterations; // L2 无护栏,给个演示截断
  const maxCost = g.max_cost, cpa = g.cost_per_attempt;
  const doLoop = () => {
    const rounds = []; let cost = 0; let stop = "", passed = false; let prevBuggy = null;
    for (let a = 1; ; a++) {
      if (level === "L3" && a > maxIter) { stop = `触发【迭代上限】${maxIter} 轮仍未通过`; break; }
      if (level !== "L2" && cost + cpa > maxCost) { stop = `触发【花费上限】再跑将超预算 ${maxCost}(已花 ${cost})`; break; }
      if (level === "L2" && a > maxIter) { stop = "L2 无护栏:真实会无限循环,这里为演示截断"; break; }
      cost += cpa;
      const buggy = a <= 1 || stuck;
      // 护栏③ 卡死检测(仅 L3):本轮产物与上轮相同
      if (level === "L3" && prevBuggy !== null && buggy === prevBuggy) {
        rounds.push({ attempt: a, cost, checks: null, stuckStop: true });
        stop = "触发【卡死检测】本轮产物与上轮完全相同,判定修不动了"; break;
      }
      prevBuggy = buggy;
      const checks = verifyChecks(a, cfg, stuck);
      rounds.push({ attempt: a, cost, checks });
      if (allOk(checks)) { stop = `验收通过 ✓(共 ${a} 轮,花费 ${cost})`; passed = true; break; }
      if (level === "L2" && a >= maxIter) { stop = "L2 无护栏:真实会无限循环,这里为演示截断"; break; }
    }
    return { rounds, stop, passed, cost };
  };

  if (level === "L4") {
    const r1 = doLoop(), r2 = doLoop();
    res.rounds = r1.rounds;
    res.passed = r1.passed && r2.passed;
    const h = res.passed ? REAL_HASH : null;
    res.hashes = [r1.passed ? h : "(未收敛)", r2.passed ? h : "(未收敛)"];
    res.stopReason = res.passed
      ? "两次均通过且哈希一致 → 确定性通过 ✓"
      : "未收敛,无法比对确定性";
    return res;
  }

  const r = doLoop();
  res.rounds = r.rounds; res.passed = r.passed; res.stopReason = r.stop;
  return res;
}

// ============ 状态 ============
const STATE = { config: null, view: "v-pipe" };

// ============ 主题 & 标签 ============
const THEME_KEY = "harness5-console-theme";
function initTheme() {
  let t = "light"; try { t = localStorage.getItem(THEME_KEY) || "light"; } catch (e) {}
  document.documentElement.setAttribute("data-theme", t);
  document.getElementById("themeBtn").textContent = t === "dark" ? "☀" : "☾";
}
document.getElementById("themeBtn").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  document.getElementById("themeBtn").textContent = next === "dark" ? "☀" : "☾";
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
};
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(t.dataset.view).classList.add("active");
    STATE.view = t.dataset.view;
  };
});

// ============ 联动图 ============
const STAGES = [
  { lv: "L0", nm: "单次调用", cmp: "l0_single/run.py → <b>model.generate()</b>", flow: "spec → prompt → 生成 → 落盘",
    title: "l0_single/run.py", desc: "最朴素:拼提示词 → 调模型 → 写文件。无任何检查。",
    code: `def main():
    spec_text, facts, constraints = common.load_spec()
    written = model.generate(OUT, spec_text, facts, constraints, attempt=1)
    print("[L0] 完成:", written)
    # 没有验收 —— 产物可能是错的,你无从得知` },
  { lv: "L1", nm: "Harness 门禁", cmp: "gate.py → <b>gates.check_consistency</b> + <b>gates.verify</b>", flow: "自洽性 → 生成 → 验收",
    title: "l1_harness/gate.py", desc: "生成前查自洽性(便宜先跑),生成后验收(结构/安全/行数/测试)。",
    code: `cfails = gates.check_consistency(spec_text, facts)   # 关卡一(生成前)
if cfails: sys.exit(2)
model.generate(OUT, spec_text, facts, constraints, attempt=1)
results = gates.verify(OUT, facts, constraints)      # 关卡二(生成后)
sys.exit(0 if gates.all_ok(results) else 1)          # 只发现,不修复` },
  { lv: "L2", nm: "Loop 闭环", cmp: "loop.py → while not ok: <b>generate → verify → 回喂</b>", flow: "失败报告 → 下一轮 prompt",
    title: "l2_loop/loop.py", desc: "Maker/Checker 分离:验收失败报告回喂给模型,重试到通过。",
    code: `while True:
    model.generate(OUT, ..., attempt=attempt, feedback=feedback)
    results = gates.verify(OUT, facts, constraints)
    if gates.all_ok(results): break          # 可验证的停止条件
    feedback = gates.format_report(results)   # 失败报告 = 下一轮输入` },
  { lv: "L3", nm: "护栏", cmp: "loop_guarded.py → 迭代/花费/卡死 <b>三护栏</b>", flow: "constraints.loop 参数",
    title: "l3_guardrails/loop_guarded.py", desc: "三条刹车:max_iterations / max_cost / sha256 卡死检测。参数来自 constraints.json。",
    code: `if attempt > max_iter: stop = "迭代上限"; break
if cost + cost_per > max_cost: stop = "花费上限"; break
cur_hash = common.sha256_file(module_path)
if prev_hash == cur_hash: stop = "卡死检测"; break   # 修不动了
prev_hash = cur_hash` },
  { lv: "L4", nm: "确定性", cmp: "determinism.py → 跑两遍 <b>比对 sha256</b>", flow: "temp0+seed → runs.jsonl",
    title: "l4_determinism/determinism.py", desc: "固定 temp0+seed,独立跑两遍,比对最终产物哈希。可复现是最硬的验收。",
    code: `for i in (1, 2):
    passed, h, n = run_once(OUT/f"run{i}", ...)   # 各自跑到通过
    runs.append({"run": i, "sha256": h, ...})
same_hash = runs[0]["sha256"] == runs[1]["sha256"]
sys.exit(0 if (both_pass and same_hash) else 1)` },
];
function renderPipe() {
  const el = document.getElementById("pipe");
  el.innerHTML = "";
  STAGES.forEach((s, i) => {
    const d = document.createElement("div");
    d.className = "stage"; d.dataset.i = i;
    d.innerHTML = `<div class="lv">${s.lv}</div><div class="nm">${s.nm}</div>
      <div class="cmp">${s.cmp}</div><div class="flowtag">${s.flow}</div>`;
    d.onclick = () => {
      document.querySelectorAll(".stage").forEach((x) => x.classList.remove("sel"));
      d.classList.add("sel");
      document.getElementById("srcTitle").textContent = s.title;
      document.getElementById("srcDesc").textContent = s.desc;
      document.getElementById("srcCode").textContent = s.code;
    };
    el.appendChild(d);
    if (i < STAGES.length - 1) {
      const a = document.createElement("div"); a.className = "arrow"; a.textContent = "▼";
      el.appendChild(a);
    }
  });
}

// ============ 配置面板 ============
function renderConfig() {
  const c = STATE.config.constraints;
  const bind = (id, valId, path) => {
    const inp = document.getElementById(id), lab = document.getElementById(valId);
    const get = () => path.split(".").reduce((o, k) => o[k], STATE.config);
    inp.value = get(); lab.textContent = get();
    inp.oninput = () => {
      const keys = path.split("."); let o = STATE.config;
      for (let i = 0; i < keys.length - 1; i++) o = o[keys[i]];
      o[keys[keys.length - 1]] = Number(inp.value);
      lab.textContent = inp.value; renderPreview();
    };
  };
  bind("mi", "miVal", "constraints.loop.max_iterations");
  bind("mc", "mcVal", "constraints.loop.max_cost");
  bind("cp", "cpVal", "constraints.loop.cost_per_attempt");
  bind("ml", "mlVal", "constraints.max_lines");
  renderBanChips(); renderFnList(); renderPreview();
}
function renderBanChips() {
  const el = document.getElementById("banChips");
  el.innerHTML = "";
  STATE.config.constraints.banned_patterns.forEach((p, i) => {
    const c = document.createElement("span"); c.className = "chip";
    c.innerHTML = `<span class="mono">${p}</span><span class="x" data-i="${i}">✕</span>`;
    c.querySelector(".x").onclick = () => {
      STATE.config.constraints.banned_patterns.splice(i, 1); renderBanChips(); renderPreview();
    };
    el.appendChild(c);
  });
}
document.getElementById("banAdd").onclick = () => {
  const v = document.getElementById("banInput").value.trim();
  if (v) { STATE.config.constraints.banned_patterns.push(v); document.getElementById("banInput").value = ""; renderBanChips(); renderPreview(); }
};
function renderFnList() {
  const el = document.getElementById("fnList");
  el.innerHTML = "";
  STATE.config.facts.functions.forEach((f, i) => {
    const inSpec = ["add", "is_prime", "fib", "factorial"].includes(f.name);
    const r = document.createElement("div"); r.className = "fn-row";
    r.innerHTML = `<span class="sig">${f.signature}</span>` +
      (inSpec ? "" : `<span class="badge">spec 无落点</span>`) +
      `<span class="x mono" style="cursor:pointer;color:var(--mute)" data-i="${i}">✕</span>`;
    r.querySelector(".x").onclick = () => {
      STATE.config.facts.functions.splice(i, 1); renderFnList(); renderPreview();
    };
    el.appendChild(r);
  });
}
document.getElementById("fnAdd").onclick = () => {
  const v = document.getElementById("fnInput").value.trim();
  if (v) { STATE.config.facts.functions.push({ name: v, signature: `${v}(n)` }); document.getElementById("fnInput").value = ""; renderFnList(); renderPreview(); }
};

function diffLine(label, oldv, newv) {
  if (JSON.stringify(oldv) === JSON.stringify(newv)) return "";
  return `<div><span class="del">- ${label}: ${JSON.stringify(oldv)}</span></div>` +
         `<div><span class="add">+ ${label}: ${JSON.stringify(newv)}</span></div>`;
}
function renderPreview() {
  const o = DEFAULTS, n = STATE.config;
  let diff = "";
  diff += diffLine("loop.max_iterations", o.constraints.loop.max_iterations, n.constraints.loop.max_iterations);
  diff += diffLine("loop.max_cost", o.constraints.loop.max_cost, n.constraints.loop.max_cost);
  diff += diffLine("loop.cost_per_attempt", o.constraints.loop.cost_per_attempt, n.constraints.loop.cost_per_attempt);
  diff += diffLine("max_lines", o.constraints.max_lines, n.constraints.max_lines);
  diff += diffLine("banned_patterns", o.constraints.banned_patterns, n.constraints.banned_patterns);
  const ofn = o.facts.functions.map((f) => f.name), nfn = n.facts.functions.map((f) => f.name);
  diff += diffLine("facts.functions", ofn, nfn);
  document.getElementById("diff").innerHTML = diff || `<span class="none">(与默认一致,无改动)</span>`;

  // writes:改了哪些文件
  const filesChanged = [];
  const cChanged = diff.includes("max_iterations") || diff.includes("max_cost") ||
    diff.includes("cost_per_attempt") || diff.includes("max_lines") || diff.includes("banned_patterns");
  if (cChanged) filesChanged.push("constraints.json");
  if (JSON.stringify(ofn) !== JSON.stringify(nfn)) filesChanged.push("spec/facts.json");
  document.getElementById("writes").innerHTML = filesChanged.length
    ? "将写回:" + filesChanged.map((f) => `<span class="file">${f}</span>`).join("、")
    : "<span class='none'>无文件改动</span>";

  // 等价命令 / 结果 JSON 片段
  const cmd = document.getElementById("cmd");
  cmd.innerHTML =
    `<span class="p"># 保存后等价于手改 constraints.json 的 loop 段:</span>\n` +
    `"loop": ${JSON.stringify(n.constraints.loop)}\n` +
    `<span class="p"># max_lines:</span> ${n.constraints.max_lines}\n` +
    (JSON.stringify(ofn) !== JSON.stringify(nfn)
      ? `<span class="p"># spec/facts.json functions:</span> [${nfn.join(", ")}]` : "");
}
document.getElementById("resetBtn").onclick = () => {
  STATE.config = JSON.parse(JSON.stringify(DEFAULTS)); renderConfig();
};
document.getElementById("saveBtn").onclick = async () => {
  await API.saveConfig(STATE.config);
  const w = document.getElementById("writes");
  w.innerHTML += `　<span style="color:var(--ok)">✓ 已保存(Mock:后端接通后真正写盘)</span>`;
};

// ============ 运行面板 ============
document.getElementById("lvSel").onchange = updateRunCmd;
document.getElementById("stuckChk").onchange = updateRunCmd;
function updateRunCmd() {
  const lv = document.getElementById("lvSel").value;
  const stuck = document.getElementById("stuckChk").checked;
  const pre = stuck ? "HARNESS_SAMPLE_STUCK=1 " : "";
  document.getElementById("runCmd").textContent = `≡ ${pre}python3 harness-5/${LEVEL_FILE[lv]}`;
}
document.getElementById("runBtn").onclick = async () => {
  const lv = document.getElementById("lvSel").value;
  const stuck = document.getElementById("stuckChk").checked;
  const btn = document.getElementById("runBtn"); btn.disabled = true; btn.textContent = "运行中…";
  document.getElementById("rounds").innerHTML = "";
  document.getElementById("verdict").innerHTML = "";
  document.getElementById("hashcmp").innerHTML = "";
  const res = await API.run(lv, { stuck });
  await animateRun(res);
  btn.disabled = false; btn.textContent = "▶ 运行";
};
function checkRow(c) {
  return `<div class="chk"><span class="mk ${c.ok ? "ok" : "bad"}">${c.ok ? "PASS" : "FAIL"}</span>` +
    `<span>${c.name}</span>${c.detail ? `<span class="dt">${c.detail}</span>` : ""}</div>`;
}
async function animateRun(res, els) {
  els = els || { rounds: document.getElementById("rounds"), verdict: document.getElementById("verdict"), hashcmp: document.getElementById("hashcmp") };
  const roundsEl = els.rounds;
  if (res.consistency && !res.consistency.ok) {
    roundsEl.innerHTML = `<div class="round"><div class="rh"><span class="mk bad" style="width:auto;padding:2px 8px">自洽性 FAIL</span></div>
      <div class="checks">${res.consistency.fails.map((f) => `<div class="chk"><span class="mk bad">FAIL</span><span>${f}</span></div>`).join("")}</div></div>`;
  }
  for (const r of res.rounds) {
    const d = document.createElement("div"); d.className = "round";
    let body;
    if (r.note !== undefined) body = `<div class="checks"><div class="chk"><span>${r.note}</span></div></div>`;
    else if (r.stuckStop) body = `<div class="checks"><div class="chk"><span class="mk bad">STOP</span><span>产物与上轮完全相同 → 卡死检测触发</span></div></div>`;
    else body = `<div class="checks">${r.checks.map(checkRow).join("")}</div>`;
    const pass = r.checks && allOk(r.checks);
    d.innerHTML = `<div class="rh">第 ${r.attempt} 轮` +
      (r.checks ? `<span class="mk ${pass ? "ok" : "bad"}" style="width:auto;padding:2px 8px">${r.checks.filter((c)=>c.ok).length}/${r.checks.length}</span>` : "") +
      (r.cost !== null && r.cost !== undefined ? `<span class="cost">花费 ${r.cost}</span>` : "") + `</div>${body}`;
    roundsEl.appendChild(d);
    await sleep(320);
  }
  // 判定
  const v = els.verdict;
  if (res.passed === null) v.innerHTML = `<div class="verdict bad" style="background:var(--warn-weak);color:var(--warn)">⚠ ${res.stopReason}</div>`;
  else v.innerHTML = `<div class="verdict ${res.passed ? "ok" : "bad"}">${res.passed ? "✓" : "✗"} ${res.stopReason}</div>`;
  // L4 哈希比对
  if (res.hashes) {
    const same = res.hashes[0] === res.hashes[1] && res.passed;
    els.hashcmp.innerHTML =
      `<div class="hashcmp"><div class="h">run1 sha256 = ${res.hashes[0]}</div>` +
      `<div class="h">run2 sha256 = ${res.hashes[1]}</div>` +
      `<div class="verdict ${same ? "ok" : "bad"}">${same ? "✓ 两次哈希一致 → 确定性通过" : "✗ 哈希不一致或未收敛"}</div></div>`;
  }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ============ 跟练模式(对齐 OUTLINE.md 的章节) ============
const STEPS = [
  { ch: "开场", mins: 10, title: "为什么要自己搭",
    why: "现成产品的两难:<b>越开箱即用越黑箱,越可控越要自己搭</b>。Kiro(闭源黑箱)/ Spec Kit(重框架)都不适合“教原理”。",
    points: ["体系:Prompt → Context → <b>Harness → Loop</b>(Addy Osmani, Loop Engineering)", "我们自研最小组件,每段都能当场改——先看联动图看全貌"],
    tabHint: "v-pipe", tabLabel: "先去「联动图」看 L0→L4 全景 →",
    expose: "从最朴素的 L0 一层层搭起。" },
  { ch: "第 1 章", mins: 15, title: "L0 单次调用", run: { level: "L0" },
    why: "最朴素的生成 = 拼提示词 → 调模型 → 落盘。就三步,没有任何保障。",
    files: ["l0_single/run.py(20 行)"],
    expose: "产物对不对没人知道(sample 下 factorial 是错的)。→ 需要验收 → L1。" },
  { ch: "第 2 章", mins: 20, title: "L1 Harness 门禁", run: { level: "L1" },
    why: "Harness = 给生成套可控环境。三关<b>从便宜到贵</b>:自洽性 → 生成 → 验收。",
    files: ["constraints.json(宪法・硬约束)", "lib/gates.py(check_consistency + verify)", "l1_harness/gate.py"],
    expose: "门禁只发现、不修复(退出码 1)。→ 需要闭环 → L2。" },
  { ch: "第 3 章", mins: 20, title: "L2 Loop 闭环", run: { level: "L2" },
    why: "Maker/Checker 分离;失败报告回喂;<b>可验证的停止条件</b>(验收全绿,而非“模型说完了”)。",
    files: ["l2_loop/loop.py(while not ok: 生成→验收→回喂)", "output/l2/state.json(逐轮状态)"],
    expose: "裸循环没刹车,真实模型可能无限烧钱。→ 需要护栏 → L3。" },
  { ch: "第 4 章", mins: 20, title: "L3 护栏", run: { level: "L3", stuck: true },
    why: "三护栏 = 迭代上限 / 花费上限 / 卡死检测(diff)。斯坦福:同任务 token 差 30 倍,<b>先设上限再开 loop</b>。",
    files: ["constraints.json 加 loop 段", "l3_guardrails/loop_guarded.py(三处 if...break + sha256)"],
    tip: "已默认勾上“修不好”(STUCK):看卡死检测秒停。想看迭代上限?去「配置」把 max_iterations 拖到 1 再回来跑。",
    expose: "同样输入重跑一样吗?→ 需要确定性 → L4。" },
  { ch: "第 5 章", mins: 15, title: "L4 确定性", run: { level: "L4" },
    why: "可复现是最硬的验收;temp0+seed;哈希基线——<b>这是主流产品普遍不做的差异点</b>。",
    files: ["l4_determinism/determinism.py(跑两遍→比对哈希)", "output/l4/runs.jsonl(可审计基线)"],
    expose: "两次 sha256 一致 → 确定性通过。" },
  { ch: "收尾", mins: 10, title: "现场改给学员看",
    why: "体现“可控”:当场改文件,看门禁/循环立刻反应——这是 Kiro 永远给不了的。",
    lived: [
      { label: "改 spec/facts.json 加一个函数", effect: "自洽性门禁立刻报错(facts 与 spec 漂移)" },
      { label: "改 constraints.json 的 max_lines=10", effect: "行数关卡触发" },
      { label: "改 loop.max_iterations=1", effect: "循环第 1 轮就被迭代上限拦下" },
    ],
    tabHint: "v-config", tabLabel: "去「配置」页现场演示这三个改动 →",
    expose: "一句话:Harness 管“一次生成可控”,Loop 管“多次收敛可控”,确定性管“结果可信”。" },
];
let curStep = 0;
function gotoTab(view) {
  const t = document.querySelector(`.tab[data-view=${view}]`);
  if (t) t.click();
}
function renderGuide() {
  const stepper = document.getElementById("stepper");
  stepper.innerHTML = "";
  STEPS.forEach((s, i) => {
    const d = document.createElement("div");
    d.className = "step-item" + (i === curStep ? " cur" : "") + (i < curStep ? " done" : "");
    d.innerHTML = `<span class="n">${i < curStep ? "✓" : i + 1}</span><span>${s.ch} · ${s.title}</span>`;
    d.onclick = () => { curStep = i; renderGuide(); };
    stepper.appendChild(d);
  });
  const s = STEPS[curStep];
  document.getElementById("stepCh").textContent = s.ch;
  document.getElementById("stepMins").textContent = "约 " + s.mins + " min";
  document.getElementById("stepTitle").textContent = s.title;

  let h = `<div class="sect"><div class="lb">讲什么 <span class="tg">为什么</span></div><div class="why">${s.why}</div>`;
  if (s.points) h += `<ul class="why-pts">` + s.points.map((p) => `<li>${p}</li>`).join("") + `</ul>`;
  h += `</div>`;
  if (s.files && s.files.length) {
    h += `<div class="sect"><div class="lb">手搭 <span class="tg">怎么做</span></div><div class="filelist">` +
      s.files.map((f) => `<div class="f">${f}</div>`).join("") + `</div></div>`;
  }
  if (s.run) {
    const stuck = !!s.run.stuck;
    h += `<div class="sect"><div class="lb">现场跑 <span class="tg">${s.run.level}${stuck ? " · STUCK" : ""}</span></div>` +
      `<div class="cmd">${stuck ? "HARNESS_SAMPLE_STUCK=1 " : ""}python3 harness-5/${LEVEL_FILE[s.run.level]}</div>` +
      (s.tip ? `<div class="hint" style="margin-top:8px">${s.tip}</div>` : "") +
      `<button class="btn" id="gRun" style="margin-top:10px">▶ 在此运行本层</button>` +
      `<div class="rounds" id="gRounds" style="margin-top:12px"></div><div id="gVerdict"></div><div id="gHash"></div></div>`;
  }
  if (s.lived) {
    h += `<div class="sect"><div class="lb">现场改给学员看 <span class="tg">可控</span></div><div class="filelist">` +
      s.lived.map((l) => `<div class="f">改 ${l.label} → <span style="color:var(--warn)">${l.effect}</span></div>`).join("") + `</div></div>`;
  }
  if (s.tabHint) {
    h += `<div class="sect"><button class="btn ghost sm" id="gTab">${s.tabLabel}</button></div>`;
  }
  h += `<div class="sect"><div class="lb">暴露问题 → 下一章</div><div class="expose">${s.expose}</div></div>`;
  document.getElementById("stepBody").innerHTML = h;

  const gr = document.getElementById("gRun");
  if (gr) gr.onclick = async () => {
    gr.disabled = true; gr.textContent = "运行中…";
    document.getElementById("gRounds").innerHTML = "";
    document.getElementById("gVerdict").innerHTML = "";
    document.getElementById("gHash").innerHTML = "";
    const res = await API.run(s.run.level, { stuck: !!s.run.stuck });
    await animateRun(res, { rounds: document.getElementById("gRounds"), verdict: document.getElementById("gVerdict"), hashcmp: document.getElementById("gHash") });
    gr.disabled = false; gr.textContent = "▶ 再跑一次";
  };
  const gt = document.getElementById("gTab");
  if (gt) gt.onclick = () => gotoTab(s.tabHint);
  document.getElementById("prevStep").disabled = curStep === 0;
  document.getElementById("nextStep").disabled = curStep === STEPS.length - 1;
}
document.getElementById("prevStep").onclick = () => { if (curStep > 0) { curStep--; renderGuide(); } };
document.getElementById("nextStep").onclick = () => { if (curStep < STEPS.length - 1) { curStep++; renderGuide(); } };

// ============ 组件四象限(前馈/后馈 × 计算型/推理型) ============
const QUADRANTS = {
  cols: [
    { key: "calc", label: "计算型", sub: "确定性・不调模型" },
    { key: "reason", label: "推理型", sub: "靠大模型" },
  ],
  rows: [
    { key: "ff", label: "前馈", sub: "生成・Maker" },
    { key: "fb", label: "后馈", sub: "验收回喂・Checker" },
  ],
  cells: {
    "ff-calc": {
      title: "确定性地准备 / 产出", desc: "不靠模型:拼输入、离线产出、落盘,同样输入必得同样结果。",
      files: [
        { p: "lib/model.py", note: "sample:离线确定产物" },
        { p: "lib/common.py", note: "load_spec / 解析 / 落盘" },
        { p: "spec/spec.md", note: "人读规格" },
        { p: "spec/facts.json", note: "机器可读事实源" },
      ],
    },
    "ff-reason": {
      title: "用大模型生成产物", desc: "Maker 调 LLM 把代码写出来——这是唯一必须靠推理的环节。",
      files: [
        { p: "lib/model.py", note: "real:调 DeepSeek 生成" },
        { p: "l0_single/run.py", note: "最朴素的一次生成" },
      ],
    },
    "fb-calc": {
      title: "用可计算方式验收(主力)", desc: "跑测试 / 正则 / 行数 / 哈希——结果确定,是我们 Checker 的全部。",
      files: [
        { p: "lib/gates.py", note: "check_consistency + verify" },
        { p: "tests/test_mathkit.py", note: "可执行的规格" },
        { p: "constraints.json", note: "禁用模式 / 行数上限" },
        { p: "l4_determinism/determinism.py", note: "跑两遍比对 sha256" },
      ],
    },
    "fb-reason": {
      title: "用大模型当裁判(刻意留空)", desc: "语义验收交给 LLM。我们不用它——确定性验收才可复现、可审计。",
      empty: true,
      files: [
        { na: true, label: "本项目未使用:Checker 全是计算型" },
        { na: true, label: "要补语义评判:promptfoo / DeepEval / Guardrails AI" },
      ],
    },
  },
};
function qfileRow(f) {
  if (f.na) return `<div class="qf na">${f.label}</div>`;
  return `<div class="qf" data-p="${f.p}"><span>${f.p}</span><span class="qn">${f.note || ""}</span></div>`;
}
function renderQuad() {
  const q = QUADRANTS;
  let h = `<div class="quad-corner"></div>`;
  q.cols.forEach((c) => (h += `<div class="quad-colh">${c.label}<span class="s">${c.sub}</span></div>`));
  q.rows.forEach((r) => {
    h += `<div class="quad-rowh">${r.label}<span class="s">${r.sub}</span></div>`;
    q.cols.forEach((c) => {
      const cell = q.cells[`${r.key}-${c.key}`];
      h += `<div class="quad-cell${cell.empty ? " empty" : ""}"><h4>${cell.title}</h4>` +
        `<div class="qd">${cell.desc}</div>${cell.files.map(qfileRow).join("")}</div>`;
    });
  });
  const wrap = document.getElementById("quadWrap");
  wrap.innerHTML = h;
  wrap.querySelectorAll(".qf[data-p]").forEach((el) => (el.onclick = () => openFile(el.dataset.p, true)));
}

// ============ 概览 + 源码浏览器 ============
// 从 harness-5 根目录起服务时(打开 /console/),可直读真实文件
const FILE_BASE = location.pathname.includes("/console/")
  ? location.pathname.replace(/\/console\/[^/]*$/, "/")
  : "./";
const FILES = [
  { g: "规格 · 事实源", items: [
    { p: "spec/spec.md", lang: "md", brief: "人读规格(自然语言契约)。" },
    { p: "spec/facts.json", lang: "json", brief: "机器可读事实源:声明要生成的函数。" },
  ] },
  { g: "硬约束", items: [
    { p: "constraints.json", lang: "json", brief: "宪法:禁用模式、行数上限、loop 护栏参数。" },
  ] },
  { g: "共享库 lib", items: [
    { p: "lib/common.py", lang: "py", brief: "读写 / 哈希 / 解析模型输出的小工具。" },
    { p: "lib/model.py", lang: "py", brief: "模型层:real=DeepSeek / sample=离线确定性(先错后对)。" },
    { p: "lib/gates.py", lang: "py", brief: "门禁:check_consistency(生成前)+ verify(生成后)。" },
  ] },
  { g: "五层 L0→L4", items: [
    { p: "l0_single/run.py", lang: "py", brief: "L0 裸调模型,无检查。" },
    { p: "l1_harness/gate.py", lang: "py", brief: "L1 三步门禁:自洽→生成→验收。" },
    { p: "l2_loop/loop.py", lang: "py", brief: "L2 失败回喂重试到通过。" },
    { p: "l3_guardrails/loop_guarded.py", lang: "py", brief: "L3 三护栏:迭代/花费/卡死。" },
    { p: "l4_determinism/determinism.py", lang: "py", brief: "L4 跑两遍比对哈希。" },
  ] },
  { g: "验收 · 编排", items: [
    { p: "tests/test_mathkit.py", lang: "py", brief: "固定验收测试(可执行的规格)。" },
    { p: "run_all.sh", lang: "sh", brief: "一键按 L0→L4 跑全部。" },
  ] },
  { g: "文档", items: [
    { p: "README.md", lang: "md", brief: "总览与五层说明。" },
    { p: "OUTLINE.md", lang: "md", brief: "Workshop 课件结构。" },
  ] },
];
const metric = (v, l) => `<div class="m"><div class="mv">${v}</div><div class="ml">${l}</div></div>`;
function renderOverview() {
  const nFiles = FILES.reduce((a, g) => a + g.items.length, 0);
  document.getElementById("dashMetrics").innerHTML =
    metric("5", "阶梯 L0→L4") + metric(nFiles, "可读源码文件") +
    metric("2", "门禁关卡") + metric("3", "循环护栏") + metric("sha256", "确定性基线");
  document.getElementById("lvlGrid").innerHTML = STAGES.map((s) =>
    `<div class="lvl-row"><span class="lb">${s.lv}</span><span class="ln">${s.nm}</span><span class="ld">${s.desc}</span></div>`).join("");
  fetch(FILE_BASE + "output/l4/runs.jsonl")
    .then((r) => (r.ok ? r.text() : Promise.reject()))
    .then((t) => { document.getElementById("runsjsonl").textContent = t.trim() || "(空)"; })
    .catch(() => { document.getElementById("runsjsonl").textContent = "(尚未跑 L4,或未从 harness-5 根目录起服务)\n运行: python3 harness-5/l4_determinism/determinism.py"; });
}
let curFile = null;
function fileMeta(p) { for (const g of FILES) { const f = g.items.find((x) => x.p === p); if (f) return f; } return null; }
function renderFiles() {
  const tree = document.getElementById("ftree");
  let h = "";
  FILES.forEach((g) => {
    h += `<div class="fg">${g.g}</div>`;
    g.items.forEach((f) => {
      h += `<div class="fi" data-p="${f.p}"><span>${f.p.split("/").pop()}</span><span class="lang">${f.lang}</span></div>`;
    });
  });
  tree.innerHTML = h;
  tree.querySelectorAll(".fi").forEach((el) => (el.onclick = () => openFile(el.dataset.p, true)));
  const first = tree.querySelector(".fi");
  if (first) openFile(first.dataset.p);
}
async function openFile(p, switchView) {
  if (switchView) { const t = document.querySelector('.tab[data-view="v-files"]'); if (t) t.click(); }
  const f = fileMeta(p);
  curFile = p;
  document.querySelectorAll("#ftree .fi").forEach((el) => el.classList.toggle("cur", el.dataset.p === p));
  document.getElementById("fvPath").textContent = "harness-5/" + p;
  document.getElementById("fvLang").textContent = f ? f.lang : "";
  document.getElementById("fvDesc").textContent = f ? f.brief : "";
  const code = document.getElementById("fvCode");
  code.textContent = "加载中…";
  try {
    const r = await fetch(FILE_BASE + p);
    if (!r.ok) throw new Error(String(r.status));
    code.textContent = await r.text();
  } catch (e) {
    code.textContent = "⚠ 读取失败。请从 harness-5 根目录起静态服务,以便读到真实文件:\n\n  cd harness-5 && python3 -m http.server 5300\n  打开 http://localhost:5300/console/\n\n(文件:harness-5/" + p + ")";
  }
}

// ============ 初始化 ============
async function init() {
  initTheme();
  const fb = document.getElementById("stFileBase");
  if (fb) fb.textContent = "FILE_BASE " + FILE_BASE + (FILE_BASE === "./" ? " (未从根目录起服务,源码可能读不到)" : "");
  STATE.config = await API.getConfig();
  renderPipe();
  renderConfig();
  renderGuide();
  renderQuad();
  renderOverview();
  renderFiles();
  updateRunCmd();
  document.querySelector(".stage").click(); // 预展开 L0 源码
}
init();
