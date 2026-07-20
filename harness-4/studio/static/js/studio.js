// Harness-4 配置工作台前端逻辑
const $ = (id) => document.getElementById(id);
const api = async (url, opts) => {
  const res = await fetch(url, opts);
  return res.json();
};
const splitList = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);

let currentCase = null;   // 当前编辑的用例名(null = 新建)
let constraints = null;
let previewCache = { case: "", specs: {} };
let debounceTimer = null;

// --------------------------------------------------------------------------
// 字段行(field_rules)动态表格
// --------------------------------------------------------------------------
function addFieldRow(field = "", rule = {}, numeric = "") {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input class="fr-name" value="${field}"></td>
    <td>
      <select class="fr-type">
        <option value="string">string</option>
        <option value="int">int</option>
        <option value="number">number</option>
        <option value="array">array</option>
      </select>
    </td>
    <td>
      <select class="fr-numeric">
        <option value="">否</option>
        <option value="int">int</option>
        <option value="number">number</option>
      </select>
    </td>
    <td><input class="fr-seq" type="number" value="${rule.sequential_from ?? ""}"></td>
    <td><input class="fr-maxlen" type="number" value="${rule.max_len ?? ""}"></td>
    <td><input class="fr-minlen" type="number" value="${rule.min_len ?? ""}"></td>
    <td><input class="fr-gt" type="number" value="${rule.gt ?? ""}"></td>
    <td><input class="fr-gte" type="number" value="${rule.gte ?? ""}"></td>
    <td><span class="del">✕</span></td>`;
  tr.querySelector(".fr-type").value = rule.type || "string";
  tr.querySelector(".fr-numeric").value = numeric || "";
  tr.querySelector(".del").onclick = () => { tr.remove(); scheduleValidate(); };
  tr.querySelectorAll("input, select").forEach((el) => el.addEventListener("input", scheduleValidate));
  $("field-rows").appendChild(tr);
}

function collectFieldRules() {
  const requiredFields = [];
  const fieldRules = {};
  const numericFields = {};
  $("field-rows").querySelectorAll("tr").forEach((tr) => {
    const name = tr.querySelector(".fr-name").value.trim();
    if (!name) return;
    requiredFields.push(name);
    const rule = { type: tr.querySelector(".fr-type").value };
    const num = (sel) => { const v = tr.querySelector(sel).value.trim(); return v === "" ? null : Number(v); };
    if (num(".fr-seq") !== null) rule.sequential_from = num(".fr-seq");
    if (num(".fr-maxlen") !== null) rule.max_len = num(".fr-maxlen");
    if (num(".fr-minlen") !== null) rule.min_len = num(".fr-minlen");
    if (num(".fr-gt") !== null) rule.gt = num(".fr-gt");
    if (num(".fr-gte") !== null) rule.gte = num(".fr-gte");
    fieldRules[name] = rule;
    const nf = tr.querySelector(".fr-numeric").value;
    if (nf) numericFields[name] = nf;
  });
  return { requiredFields, fieldRules, numericFields };
}

// --------------------------------------------------------------------------
// 表单 <-> case 对象
// --------------------------------------------------------------------------
function formToCase() {
  const { requiredFields, fieldRules, numericFields } = collectFieldRules();
  const imageField = $("u-image-field").value.trim();
  const dataFile = $("f-data-file").value.trim();
  return {
    name: $("f-name").value.trim(),
    entity: $("f-entity").value.trim(),
    title: $("f-title").value.trim(),
    data_file: dataFile,
    min_items: Number($("f-min-items").value) || 0,
    required_fields: requiredFields,
    numeric_fields: numericFields,
    field_rules: fieldRules,
    loader_function: $("f-loader").value.trim(),
    route_functions: splitList($("r-funcs").value),
    routes: {
      list: $("r-list").value.trim(),
      detail_sample: $("r-detail").value.trim(),
      api_list: $("r-api-list").value.trim(),
      api_detail_ok: $("r-api-ok").value.trim(),
      api_detail_missing: $("r-api-missing").value.trim(),
    },
    list_marker: $("u-list-marker").value.trim(),
    list_card_children: splitList($("u-card-children").value),
    detail_markers: splitList($("u-detail-markers").value),
    colors: splitList($("u-colors").value),
    needs_images: $("u-needs-images").checked,
    image_field: $("u-needs-images").checked ? (imageField || null) : null,
    extra_required_files: dataFile ? [dataFile] : [],
  };
}

function caseToForm(c) {
  $("f-name").value = c.name || "";
  $("f-entity").value = c.entity || "";
  $("f-title").value = c.title || "";
  $("f-data-file").value = c.data_file || "";
  $("f-min-items").value = c.min_items || 6;
  $("f-loader").value = c.loader_function || "";
  $("r-funcs").value = (c.route_functions || []).join(", ");
  const r = c.routes || {};
  $("r-list").value = r.list || "/";
  $("r-detail").value = r.detail_sample || "";
  $("r-api-list").value = r.api_list || "";
  $("r-api-ok").value = r.api_detail_ok || "";
  $("r-api-missing").value = r.api_detail_missing || "";
  $("u-list-marker").value = c.list_marker || "";
  $("u-card-children").value = (c.list_card_children || []).join(", ");
  $("u-detail-markers").value = (c.detail_markers || []).join(", ");
  $("u-colors").value = (c.colors || []).join(", ");
  $("u-needs-images").checked = !!c.needs_images;
  $("u-image-field").value = c.image_field || "";
  $("field-rows").innerHTML = "";
  (c.required_fields || []).forEach((f) => {
    addFieldRow(f, (c.field_rules || {})[f] || {}, (c.numeric_fields || {})[f] || "");
  });
}

// --------------------------------------------------------------------------
// 校验 + 预览(实时,防抖)
// --------------------------------------------------------------------------
function scheduleValidate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(validateNow, 350);
}

async function validateNow() {
  const c = formToCase();
  previewCache.case = JSON.stringify(c, null, 2);
  const data = await api("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(c),
  });
  previewCache.specs = data.specs || {};
  renderPreview();
  const box = $("validate-result");
  const status = $("global-status");
  if (data.ok) {
    box.className = "validate-result ok";
    box.textContent = "✅ 自洽性预检通过,可安全保存写盘。";
    status.className = "pill ok"; status.textContent = "自洽 ✓";
  } else {
    box.className = "validate-result";
    box.innerHTML = "❌ 存在漂移,以下事实未落到 spec:<ul>" +
      data.fails.map((f) => `<li>${f}</li>`).join("") + "</ul>";
    status.className = "pill err"; status.textContent = "漂移 ✗";
  }
}

function renderPreview() {
  const tab = document.querySelector(".tab.active").dataset.tab;
  $("preview-body").textContent = tab === "case"
    ? previewCache.case
    : (previewCache.specs[tab] || "(空)");
}

// --------------------------------------------------------------------------
// 用例列表
// --------------------------------------------------------------------------
async function loadCases() {
  const { cases } = await api("/api/cases");
  const ul = $("case-list");
  ul.innerHTML = "";
  cases.forEach((name) => {
    const li = document.createElement("li");
    li.textContent = name;
    if (name === currentCase) li.className = "active";
    li.onclick = () => openCase(name);
    ul.appendChild(li);
  });
  renderRunCases(cases);
}

async function openCase(name) {
  const data = await api(`/api/case/${name}`);
  if (data.error) return alert(data.error);
  currentCase = name;
  $("editor-title").textContent = `编辑用例:${name}`;
  $("btn-delete-case").hidden = false;
  caseToForm(data.case);
  await loadCases();
  validateNow();
}

function newCase() {
  currentCase = null;
  $("editor-title").textContent = "新建用例";
  $("btn-delete-case").hidden = true;
  caseToForm({
    routes: { list: "/" },
    required_fields: ["id", "title", "summary", "content"],
    field_rules: {
      id: { type: "int", sequential_from: 1 },
      title: { type: "string", max_len: 60 },
      summary: { type: "string", max_len: 120 },
      content: { type: "string", min_len: 200 },
    },
    min_items: 6,
    colors: ["#1a73e8"],
  });
  loadCases();
  validateNow();
}

async function saveCase() {
  const c = formToCase();
  if (!c.name) return alert("请填写用例名 name");
  const data = await api(`/api/case/${c.name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(c),
  });
  currentCase = c.name;
  await loadCases();
  await openCase(c.name);
  alert(data.ok ? `已写盘:cases/${c.name}/(case.json + 3 份 spec)` :
    `已写盘,但自洽性未通过:\n- ${data.fails.join("\n- ")}`);
}

async function deleteCase() {
  if (!currentCase) return;
  if (!confirm(`确认删除用例 ${currentCase}?将移除整个 cases/${currentCase}/ 目录。`)) return;
  await api(`/api/case/${currentCase}`, { method: "DELETE" });
  currentCase = null;
  newCase();
}

// --------------------------------------------------------------------------
// 全局 constraints
// --------------------------------------------------------------------------
async function loadConstraints() {
  constraints = await api("/api/constraints");
  const t = constraints.tech || {};
  $("tech-box").textContent =
    `${t.language} / ${t.framework}\nentry: ${t.entry}  port: ${t.default_port}`;
  $("banned-deps").value = (constraints.banned_deps || []).join(", ");
  $("banned-patterns").value = (constraints.banned_code_patterns || []).join(", ");
  $("max-inline-style").value = constraints.max_inline_style ?? 2;
}

function renderRunCases(cases) {
  const box = $("run-cases-box");
  const runCases = (constraints && constraints.run_cases) || [];
  box.innerHTML = "";
  cases.forEach((name) => {
    const label = document.createElement("label");
    label.innerHTML =
      `<input type="checkbox" value="${name}" ${runCases.includes(name) ? "checked" : ""}> ${name}`;
    box.appendChild(label);
  });
}

async function saveConstraints() {
  const runCases = [...$("run-cases-box").querySelectorAll("input:checked")].map((el) => el.value);
  const payload = {
    ...constraints,
    banned_deps: splitList($("banned-deps").value),
    banned_code_patterns: splitList($("banned-patterns").value),
    max_inline_style: Number($("max-inline-style").value) || 0,
    run_cases: runCases,
  };
  const data = await api("/api/constraints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  constraints = data.constraints;
  alert("已保存 constraints.json");
}

// --------------------------------------------------------------------------
// 真实门禁(自洽性关)
// --------------------------------------------------------------------------
async function runGate() {
  $("validate-result").textContent = "正在运行 check_consistency.py …";
  const data = await api("/api/gate/consistency", { method: "POST" });
  const box = $("validate-result");
  box.className = data.ok ? "validate-result ok" : "validate-result";
  box.textContent = (data.ok ? "✅ 真实门禁通过\n" : "❌ 真实门禁未通过\n") +
    (data.stdout || "") + (data.stderr || "");
}

// --------------------------------------------------------------------------
// 事件绑定
// --------------------------------------------------------------------------
function bind() {
  $("btn-add-field").onclick = () => { addFieldRow(); scheduleValidate(); };
  $("btn-new-case").onclick = newCase;
  $("btn-save-case").onclick = saveCase;
  $("btn-delete-case").onclick = deleteCase;
  $("btn-save-constraints").onclick = saveConstraints;
  $("btn-gate").onclick = runGate;
  document.querySelectorAll(".editor input, .editor select").forEach(
    (el) => el.addEventListener("input", scheduleValidate));
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      renderPreview();
    };
  });
}

(async function init() {
  bind();
  await loadConstraints();
  await loadCases();
  const { cases } = await api("/api/cases");
  if (cases.length) openCase(cases[0]); else newCase();
})();
