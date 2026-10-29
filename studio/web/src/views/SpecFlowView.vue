<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { RequirementSummary, SpecCompileResponse, SpecDoc } from '../api/contracts'

// Spec 编译（真实）：需求从「需求池」（source 适配器加载）中选择，而不是手输。
// 左侧先展示 MumuSpec 六轮框架骨架（每个步骤要产出的文档位置），编译后填充真实内容。

// 六轮框架骨架：每轮产出哪些文档
const FRAMEWORK = [
  { round: 'R1', name: '领域分析', desc: '识别业务域、角色、边界', docs: ['01-writing-guidelines.md', '02-elicitation.md'] },
  { round: 'R2', name: '用户故事', desc: '拆能力为用户故事 + AC', docs: ['03-proposal.md', '04-prd.md'] },
  { round: 'R3', name: 'API 契约', desc: '定义接口、状态码、错误码', docs: ['05-user-stories.md', '09-api-spec.md'] },
  { round: 'R4', name: '数据模型', desc: '字段、类型、约束', docs: ['06-fsd.md', '07-nfr.md', '08-architecture.md', '10-data-model.md'] },
  { round: 'R5', name: 'UI 设计', desc: '页面结构、交互', docs: ['11-security.md', '12-implementation-plan.md'] },
  { round: 'R6', name: '验收标准', desc: '可验证断言', docs: ['13-test-strategy.md', '14-traceability-matrix.md', 'spec/spec.md', 'spec/manifest.json', 'spec/acceptance.json'] },
]

const requirements = ref<RequirementSummary[]>([])
const selectedReqId = ref('')
const mock = ref(false)
const loading = ref(false)
const compiling = ref(false)
const error = ref('')
const result = ref<SpecCompileResponse | null>(null)
const selectedPath = ref('')

const selectedReq = computed(() => requirements.value.find(r => r.id === selectedReqId.value) || null)
const compiledDocs = computed(() => result.value?.docs || [])
const docByPath = (path: string) => compiledDocs.value.find(d => d.path.endsWith(path))
const selected = computed(() => compiledDocs.value.find(d => d.path === selectedPath.value) || compiledDocs.value[0] || null)
const statusOf = (req: RequirementSummary) => req.status === 'pending' ? '待处理' : req.status === 'done' ? '已完成' : req.status === 'fetched' ? '已拉取' : req.status

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function renderMarkdown(md: string): string {
  let html = '', inCode = false, inList = false
  for (const line of md.split('\n')) {
    if (line.trim().startsWith('```')) {
      if (inCode) { html += '</code></pre>'; inCode = false }
      else { if (inList) { html += '</ul>'; inList = false } html += '<pre><code>'; inCode = true }
      continue
    }
    if (inCode) { html += escapeHtml(line) + '\n'; continue }
    if (/^#### /.test(line)) { html += '<h4>' + escapeHtml(line.slice(5)) + '</h4>'; continue }
    if (/^### /.test(line)) { html += '<h4>' + escapeHtml(line.slice(4)) + '</h4>'; continue }
    if (/^## /.test(line)) { html += '<h3>' + escapeHtml(line.slice(3)) + '</h3>'; continue }
    if (/^# /.test(line)) { html += '<h2>' + escapeHtml(line.slice(2)) + '</h2>'; continue }
    if (/^\s*[-*] /.test(line)) { if (!inList) { html += '<ul>'; inList = true } html += '<li>' + escapeHtml(line.replace(/^\s*[-*] /, '')) + '</li>'; continue }
    if (inList) { html += '</ul>'; inList = false }
    if (line.trim() === '') continue
    html += '<p>' + escapeHtml(line) + '</p>'
  }
  if (inList) html += '</ul>'
  if (inCode) html += '</code></pre>'
  return html
}
const isJson = (doc: SpecDoc | null) => !!doc?.path.endsWith('.json')
const renderedContent = computed(() => {
  const doc = selected.value
  if (!doc) return ''
  if (isJson(doc)) {
    try { return '<pre><code>' + escapeHtml(JSON.stringify(JSON.parse(doc.content), null, 2)) + '</code></pre>' }
    catch { return '<pre><code>' + escapeHtml(doc.content) + '</code></pre>' }
  }
  return renderMarkdown(doc.content)
})

async function compile() {
  if (!selectedReq.value) return
  compiling.value = true; error.value = ''; result.value = null; selectedPath.value = ''
  try {
    result.value = await api.specCompile(selectedReq.value.title, selectedReq.value.id, mock.value)
    selectedPath.value = result.value.docs[0]?.path || ''
  } catch (e) { error.value = e instanceof Error ? e.message : '编译失败' }
  finally { compiling.value = false }
}

onMounted(async () => {
  loading.value = true
  try {
    requirements.value = (await api.requirements()).requirements
    selectedReqId.value = requirements.value.find(r => r.status === 'pending')?.id || requirements.value[0]?.id || ''
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取需求池' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page spec-flow">
    <div class="page-heading">
      <div>
        <p class="eyebrow">MUMUSPEC · SPEC COMPILATION</p>
        <h1>Spec 编译</h1>
        <p>从需求池选择需求，六轮编译成 Spec 文档。左侧是六轮框架骨架，编译前展示每个文档的位置，编译后填充真实内容。</p>
      </div>
    </div>

    <!-- 需求选择（从需求池） -->
    <section class="sf-req">
      <div class="sf-req-row">
        <label class="sf-select"><span>选择需求（来自需求池 · source 适配器）</span>
          <select v-model="selectedReqId" :disabled="loading">
            <option v-for="r in requirements" :key="r.id" :value="r.id">{{ r.title }} · {{ r.id }} · {{ statusOf(r) }}</option>
          </select>
        </label>
        <label class="sf-mock"><input type="checkbox" v-model="mock" /><span>Mock 模式（不调 LLM）</span></label>
        <button class="primary-button" @click="compile" :disabled="compiling || !selectedReq">{{ compiling ? '编译中（六轮 LLM，约几分钟）…' : '开始编译' }}</button>
      </div>
    </section>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>

    <!-- 两栏：左六轮框架 + 右文档内容 -->
    <div class="sf-columns">
      <aside class="sf-steps">
        <div class="sf-steps-head"><span>六轮框架</span><small>{{ compiledDocs.length ? compiledDocs.length + ' 份已生成' : '骨架预览' }}</small></div>
        <div v-for="f in FRAMEWORK" :key="f.round" class="sf-round">
          <div class="sf-round-head">
            <span class="sf-round-no">{{ f.round }}</span>
            <div><b>{{ f.name }}</b><small>{{ f.desc }}</small></div>
          </div>
          <div class="sf-round-docs">
            <button v-for="doc in f.docs" :key="doc" class="sf-step" :class="{ active: selected?.path.endsWith(doc), filled: !!docByPath(doc) }" :disabled="!docByPath(doc)" @click="selectedPath = docByPath(doc)!.path">
              <span class="sf-dot"></span>
              <div class="sf-step-main"><b>{{ doc.split('/').pop() }}</b></div>
              <i class="sf-state">{{ docByPath(doc) ? '已生成' : '待生成' }}</i>
            </button>
          </div>
        </div>
      </aside>

      <main class="sf-doc">
        <template v-if="selected">
          <header class="sf-doc-head">
            <div><p class="eyebrow">{{ selected.path }}</p><h2>{{ selected.name }}</h2></div>
            <span>{{ selected.content.length }} 字</span>
          </header>
          <div class="sf-doc-body" v-html="renderedContent"></div>
        </template>
        <div v-else class="sf-empty">
          <p class="empty-state">从左侧选择一份文档查看内容。<br />编译前这里是骨架占位，编译后显示真实 Spec。</p>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.sf-req { margin-top: 6px; padding: 16px 18px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.sf-req-row { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; }
.sf-select { flex: 1; min-width: 280px; display: flex; flex-direction: column; gap: 6px; }
.sf-select span, .sf-mock span { color: var(--muted); font-size: 11px; }
.sf-select select { padding: 9px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--ink); font-size: 13px; }
.sf-select select:focus { outline: none; border-color: var(--brand); }
.sf-mock { display: flex; align-items: center; gap: 6px; }
.sf-mock input { width: auto; }
.sf-columns { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 14px; margin-top: 14px; align-items: start; }
.sf-steps { border: 1px solid var(--line); border-radius: 13px; background: var(--panel); overflow: hidden; max-height: 74vh; overflow-y: auto; }
.sf-steps-head { display: flex; align-items: baseline; justify-content: space-between; padding: 12px 15px; border-bottom: 1px solid var(--line); font-size: 12px; font-weight: 700; color: var(--soft); }
.sf-steps-head small { font-weight: 400; font-size: 10px; }
.sf-round { border-bottom: 1px solid var(--line-soft); }
.sf-round-head { display: flex; align-items: center; gap: 9px; padding: 10px 14px 6px; }
.sf-round-no { display: grid; place-items: center; width: 20px; height: 20px; flex: 0 0 20px; border-radius: 6px; background: color-mix(in srgb, var(--violet) 13%, transparent); color: var(--violet); font-size: 10px; font-weight: 700; }
.sf-round-head b { font-size: 12px; display: block; }
.sf-round-head small { color: var(--soft); font-size: 10px; }
.sf-round-docs { padding: 2px 0 6px 14px; }
.sf-step { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 10px; border: 0; background: transparent; cursor: pointer; text-align: left; border-radius: 6px; }
.sf-step:disabled { cursor: default; }
.sf-step.filled:hover { background: var(--panel-2); }
.sf-step.active { background: color-mix(in srgb, var(--brand) 8%, transparent); box-shadow: inset 3px 0 0 var(--brand); }
.sf-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: var(--line); }
.sf-step.filled .sf-dot { background: var(--mint); }
.sf-step-main { flex: 1; min-width: 0; }
.sf-step-main b { font-size: 11px; font-family: ui-monospace, Menlo, monospace; color: var(--soft); }
.sf-step.filled .sf-step-main b { color: var(--ink); }
.sf-state { font-size: 9px; color: var(--soft); font-style: normal; flex-shrink: 0; }
.sf-step.filled .sf-state { color: var(--mint); }
.sf-doc { border: 1px solid var(--line); border-radius: 13px; background: var(--panel); padding: 22px 26px; min-height: 420px; max-height: 74vh; overflow-y: auto; }
.sf-doc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line-soft); padding-bottom: 12px; margin-bottom: 8px; }
.sf-doc-head h2 { margin: 2px 0 0; font-size: 16px; }
.sf-doc-head span { color: var(--soft); font-size: 11px; flex-shrink: 0; }
.sf-empty { display: grid; place-items: center; min-height: 360px; }
.sf-doc-body { color: var(--ink); font-size: 13px; line-height: 1.7; }
.sf-doc-body :deep(h2) { font-size: 18px; margin: 18px 0 8px; }
.sf-doc-body :deep(h3) { font-size: 15px; margin: 16px 0 6px; }
.sf-doc-body :deep(h4) { font-size: 13px; margin: 12px 0 4px; }
.sf-doc-body :deep(p) { margin: 6px 0; }
.sf-doc-body :deep(ul) { margin: 6px 0 6px 20px; }
.sf-doc-body :deep(li) { margin: 3px 0; }
.sf-doc-body :deep(pre) { background: var(--code-bg); border-radius: 8px; padding: 12px; overflow-x: auto; }
.sf-doc-body :deep(code) { font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
.sf-doc-body :deep(pre code) { background: none; padding: 0; }
@media (max-width: 800px) { .sf-columns { grid-template-columns: 1fr; } .sf-steps, .sf-doc { max-height: none; } }
</style>
