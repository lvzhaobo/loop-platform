<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { KnowledgeResponse } from '../api/contracts'

// 知识工程（Mock 原型）：Tab 结构
// ① 概览（动态原理图画布）② 知识源 ③ 存储与对接 ④ MCP Server ⑤ 检索验证

type TabKey = 'overview' | 'source' | 'storage' | 'mcp' | 'verify'
const tab = ref<TabKey>('overview')
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: '概览·原理图' },
  { key: 'source', label: '知识源' },
  { key: 'storage', label: '存储与对接' },
  { key: 'mcp', label: 'MCP Server' },
  { key: 'verify', label: '检索验证' },
]

// ── 概览：动态原理图节点（两条路径 + 更新回环）──
const VECTOR_FLOW = [
  { id: 'source', label: '知识源', sub: 'NAS / 云存储 / 代码仓库 / 文件', tone: 'tone-blue', detail: '知识从哪来：内网 NAS、对象存储（S3/OSS）、代码仓库、本地文件导入。接入后统一进入处理管道。' },
  { id: 'chunk', label: '解析·分块', sub: '切成可检索片段', tone: 'tone-violet', detail: '把文档/代码按语义边界切成小块（chunk），每块是一个最小检索单元。切块大小直接影响检索精度。' },
  { id: 'embed', label: '向量化', sub: '片段 → 数字向量', tone: 'tone-violet', detail: '每块通过 Embedding 模型转成一组数字（向量）。相似内容数字相近——只需理解到这一步，不展开数学。' },
  { id: 'vector', label: '向量库', sub: '写入 + 建索引', tone: 'tone-ok', detail: '向量写入向量库（collection），并建索引。之后可按相似度快速检索，不必逐条比对。' },
  { id: 'retrieve', label: '检索', sub: 'query → 相似片段', tone: 'tone-ok', detail: '查询进来，同样转成向量，在向量库里找最相近的片段返回。支持正则/语义/词法/术语多路。' },
  { id: 'consume', label: 'IDE / MCP', sub: '动态检索 · 问答', tone: 'tone-muted', detail: '命中的知识作为上下文注入 Claude Code、Qoder，或通过 MCP 暴露成工具——这是「动态检索」路径，回答「这段代码该怎么写」这类即时问题。' },
]
const CONSTRAINT_FLOW = [
  { id: 'struct', label: '结构化', sub: '知识 → 规则 / Spec', tone: 'tone-violet', detail: '把知识提炼成结构化规则、Spec、AGENTS.md。这是知识工程区别于普通 RAG 的核心产出——不只是「检索片段」，而是「可复用的约束」。' },
  { id: 'rules', label: '规则 / Spec', sub: '确定性约束', tone: 'tone-blue', detail: '沉淀为规则库、术语库、Spec 文档（如安全红线、编码规范、术语表）。确定性知识，注入即生效。' },
  { id: 'harness', label: 'Harness 约束', sub: '前馈注入', tone: 'tone-blue', detail: '规则 / Spec 作为前馈约束注入 Harness，生成前即生效，从源头约束 AI 输出。' },
  { id: 'landing', label: 'Landing Zone', sub: '装配底座', tone: 'tone-muted', detail: '约束装配进 Landing Zone，落地到 Loop Platform 沙箱或 dsh 底座。这是知识工程的最终落点。' },
]
const ALL_NODES = [...VECTOR_FLOW, ...CONSTRAINT_FLOW]
const activeNode = ref<string | null>(null)
const nodeOf = (id: string) => ALL_NODES.find(n => n.id === id)

// ── 知识源 ──
type SourceType = 'nas' | 'cloud' | 'repo' | 'file'
const SOURCE_TYPES: Array<{ id: SourceType; label: string; desc: string; fields: Array<{ name: string; label: string; placeholder: string }> }> = [
  { id: 'nas', label: 'NAS 网盘', desc: '接入内网 NAS 知识库目录', fields: [{ name: 'address', label: '网盘地址', placeholder: 'smb://192.0.2.10/kb' }, { name: 'path', label: '挂载路径', placeholder: '/mnt/kb' }] },
  { id: 'cloud', label: '云存储', desc: '接入对象存储（S3/OSS）', fields: [{ name: 'provider', label: '供应商', placeholder: '阿里云 OSS' }, { name: 'bucket', label: 'Bucket', placeholder: 'kb-bucket' }] },
  { id: 'repo', label: '代码仓库', desc: '接入代码仓库与提交历史', fields: [{ name: 'url', label: '仓库地址', placeholder: 'git@gitlab.example.com:team/repo.git' }, { name: 'branch', label: '默认分支', placeholder: 'main' }] },
  { id: 'file', label: '文件导入', desc: '批量导入本地文件/文档', fields: [{ name: 'files', label: '文件', placeholder: '拖拽或选择文件' }] },
]
const TYPE_META: Record<SourceType, { label: string; tone: string }> = {
  nas: { label: 'NAS 网盘', tone: 'tone-blue' },
  cloud: { label: '云存储', tone: 'tone-violet' },
  repo: { label: '代码仓库', tone: 'tone-ok' },
  file: { label: '文件导入', tone: 'tone-muted' },
}
const sources = ref([
  { id: 's1', type: 'repo' as SourceType, name: '核心业务代码仓库', detail: 'gitlab.example.com/core · main', status: '已接入', level: '机密', version: 'v3 · 10-20' },
  { id: 's2', type: 'nas' as SourceType, name: '研发知识库 NAS', detail: 'smb://192.0.2.10/kb · 12.4 GB · 1,284 文件', status: '已接入', level: '内部', version: '10-18' },
  { id: 's3', type: 'cloud' as SourceType, name: '架构文档 OSS', detail: 'oss://arch-docs', status: '同步中', level: '公开', version: '10-18' },
])
const adding = ref<SourceType | null>(null)
const form = ref<Record<string, string>>({})

// ── 存储与对接：静态步骤 ──
const STORE_STEPS = [
  { no: 1, t: '分块', d: '文档按语义边界切成 chunk（如 512 token 一块）' },
  { no: 2, t: '向量化', d: '每块经 Embedding 转成数字向量' },
  { no: 3, t: '写库', d: '向量 + 原文一起写入 collection' },
  { no: 4, t: '建索引', d: '为向量建索引，支持相似度近邻检索' },
]
const IDE_STEPS = [
  { no: 1, t: '查询', d: 'IDE 里的 Agent 发起查询（query）' },
  { no: 2, t: '检索', d: 'query 向量化，在向量库找最相近片段' },
  { no: 3, t: '组装上下文', d: '命中片段拼成 Rules / 上下文' },
  { no: 4, t: '注入 IDE', d: '注入 Claude Code / Qoder 的 context / system prompt' },
]

// ── 分层存储 ──
const STORE_TYPES = [
  { id: 'rules', label: '规则库', type: '确定性', desc: 'Spec / Rules / AGENTS.md', use: '注入 Harness 前馈约束' },
  { id: 'term', label: '术语库', type: '精确匹配', desc: '企业术语表 / 词典', use: '术语检索' },
  { id: 'vector', label: '向量库', type: '语义', desc: '文档向量 / 索引', use: '语义检索' },
]

// ── 评测集（Ground Truth）──
const EVAL_SET = [
  { q: '数据库连接超时怎么办', hit: '连接池配置规则（规则库）' },
  { q: '用户密码如何存储', hit: '密码加密红线（规则库）' },
  { q: '订单状态怎么流转', hit: '订单状态机 Spec（Spec）' },
]

// ── MCP Server 核心 ──
const MCP_SKELETON = `from mcp.server import Server
srv = Server("knowledge")

@srv.tool()
def search_knowledge(query: str) -> list:
    """在向量库检索相关知识片段"""
    return vector_db.search(query, top_k=5)

srv.run()  # stdio 协议，IDE 直接连`

// ── 检索验证 ──
const RETRIEVERS = [
  { id: 'regex', label: '正则', desc: '正则表达式精确匹配' },
  { id: 'semantic', label: '语义', desc: 'Embedding 向量相似度' },
  { id: 'lexical', label: '词法', desc: '分词 / 关键词 BM25' },
  { id: 'term', label: '术语', desc: '术语表词典精确匹配' },
]
const retrieverOn = ref<Record<string, boolean>>({ regex: true, semantic: true, lexical: true, term: true })
const ABLATION = [
  { combo: '全路（正则+语义+词法+术语）', recall: 92, precision: 88, latency: 180, cost: 0.012 },
  { combo: '去掉语义', recall: 78, precision: 90, latency: 120, cost: 0.008 },
  { combo: '去掉术语', recall: 85, precision: 82, latency: 170, cost: 0.011 },
  { combo: '单路 · 正则', recall: 55, precision: 95, latency: 30, cost: 0.002 },
  { combo: '单路 · 语义', recall: 70, precision: 72, latency: 90, cost: 0.006 },
  { combo: '单路 · 术语', recall: 62, precision: 90, latency: 20, cost: 0.001 },
]
const ablationRan = ref(false)

const data = ref<KnowledgeResponse | null>(null)
const error = ref('')
const loading = ref(true)

function openAdd(type: SourceType) { adding.value = type; form.value = {} }
function closeAdd() { adding.value = null; form.value = {} }
function submitAdd() {
  const t = SOURCE_TYPES.find(x => x.id === adding.value); if (!t) return
  const detail = t.fields.map(f => `${form.value[f.name] || '—'}`).join(' · ')
  sources.value.push({ id: 's' + Date.now(), type: t.id, name: form.value.name || t.label, detail, status: '已接入（Mock）', level: '内部', version: '—' })
  closeAdd()
}
function remove(id: string) { sources.value = sources.value.filter(s => s.id !== id) }

onMounted(async () => {
  loading.value = true; error.value = ''
  try { data.value = await api.knowledge() }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取知识工程数据' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page knowledge">
    <div class="page-heading">
      <div>
        <p class="eyebrow">KNOWLEDGE ENGINEERING</p>
        <h1>知识工程</h1>
        <p>接入知识源 → 向量化存储 → 注入 IDE / MCP，并用消融实验验证检索质量。此页为 Mock 原型。</p>
      </div>
      <span class="proto-chip">原型 · Mock</span>
    </div>

    <div class="tab-bar">
      <button v-for="t in TABS" :key="t.key" class="tab" :class="{ on: tab === t.key }" @click="tab = t.key">{{ t.label }}</button>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>

    <!-- ① 概览：动态原理图 -->
    <section v-if="tab === 'overview'" class="k-panel">
      <div class="k-panel-head"><h2>知识工程数据流转</h2><span>两条路径 + 更新回环，点击节点查看详情</span></div>

      <div class="track-label">向量检索路径 · 动态（即时检索问答）</div>
      <div class="flow-canvas">
        <template v-for="(n, i) in VECTOR_FLOW" :key="n.id">
          <button class="flow-node" :class="[n.tone, { active: activeNode === n.id }]" @click="activeNode = activeNode === n.id ? null : n.id">
            <span class="flow-no">{{ i + 1 }}</span>
            <b>{{ n.label }}</b>
            <small>{{ n.sub }}</small>
          </button>
          <span v-if="i < VECTOR_FLOW.length - 1" class="flow-arrow">→</span>
        </template>
      </div>

      <div class="track-label" style="margin-top:18px">约束化路径 · 静态（Harness 前馈约束）</div>
      <div class="flow-canvas">
        <template v-for="(n, i) in CONSTRAINT_FLOW" :key="n.id">
          <button class="flow-node" :class="[n.tone, { active: activeNode === n.id }]" @click="activeNode = activeNode === n.id ? null : n.id">
            <span class="flow-no">{{ i + 1 }}</span>
            <b>{{ n.label }}</b>
            <small>{{ n.sub }}</small>
          </button>
          <span v-if="i < CONSTRAINT_FLOW.length - 1" class="flow-arrow">→</span>
        </template>
      </div>

      <div class="feedback-loop">
        <span class="feedback-arrow">↺</span>
        <span><b>更新闭环</b>：运行 / 验证 → 复盘 → 更新知识源与规则（失败 case 回流为约束）</span>
      </div>

      <div v-if="activeNode && nodeOf(activeNode)" class="flow-detail">
        <b>{{ nodeOf(activeNode)?.label }}</b>
        <p>{{ nodeOf(activeNode)?.detail }}</p>
      </div>
    </section>

    <!-- ② 知识源 -->
    <section v-if="tab === 'source'" class="k-panel">
      <div class="k-panel-head"><h2>知识源接入</h2><span>接入内网网盘、云存储、代码仓库或导入文件</span></div>
      <div class="src-types">
        <button v-for="t in SOURCE_TYPES" :key="t.id" class="src-type" @click="openAdd(t.id)"><b>+ {{ t.label }}</b><span>{{ t.desc }}</span></button>
      </div>
      <div class="src-list-head"><b>已接入知识源</b><small>{{ sources.length }} 个</small></div>
      <div class="src-list">
        <div v-for="s in sources" :key="s.id" class="src-row">
          <span class="src-tag" :class="TYPE_META[s.type].tone">{{ TYPE_META[s.type].label }}</span>
          <div class="src-main"><b>{{ s.name }} <span class="level-tag" :class="s.level === '机密' ? 'lv-secret' : s.level === '内部' ? 'lv-internal' : 'lv-public'">{{ s.level }}</span></b><small>{{ s.detail }} · v{{ s.version }}</small></div>
          <span class="src-status" :class="{ sync: s.status === '同步中' }">{{ s.status }}</span>
          <button class="src-remove" @click="remove(s.id)" title="移除">×</button>
        </div>
      </div>
    </section>

    <!-- ③ 存储与对接 -->
    <section v-if="tab === 'storage'" class="k-panel">
      <div class="k-panel-head"><h2>分层存储</h2><span>确定性知识与非结构化文档分开存，各对应不同消费方式</span></div>
      <div class="store-grid">
        <div v-for="st in STORE_TYPES" :key="st.id" class="store-card">
          <b>{{ st.label }}</b><span class="store-type">{{ st.type }}</span>
          <p>{{ st.desc }}</p>
          <small>{{ st.use }}</small>
        </div>
      </div>

      <div class="k-panel-head" style="margin-top:22px"><h2>向量库存储过程</h2><span>点设置后数据怎么存进去（不讲向量数学）</span></div>
      <div class="mini-flow">
        <template v-for="(s, i) in STORE_STEPS" :key="s.no">
          <div class="step"><span class="step-no">{{ s.no }}</span><b>{{ s.t }}</b><p>{{ s.d }}</p></div>
          <span v-if="i < STORE_STEPS.length - 1" class="mini-arrow">→</span>
        </template>
      </div>

      <div class="k-panel-head" style="margin-top:22px"><h2>与 IDE 对接</h2><span>知识怎么到 Claude Code / Qoder</span></div>
      <div class="mini-flow">
        <template v-for="(s, i) in IDE_STEPS" :key="s.no">
          <div class="step"><span class="step-no">{{ s.no }}</span><b>{{ s.t }}</b><p>{{ s.d }}</p></div>
          <span v-if="i < IDE_STEPS.length - 1" class="mini-arrow">→</span>
        </template>
      </div>
    </section>

    <!-- ④ MCP Server -->
    <section v-if="tab === 'mcp'" class="k-panel">
      <div class="k-panel-head"><h2>自定义 MCP Server · 核心原理</h2><span>不贴完整实现，只看核心过程</span></div>
      <div class="mcp-flow">
        <div class="mcp-node"><b>Claude Code / Qoder</b><small>IDE · MCP 客户端</small></div>
        <span class="mcp-arrow">↔</span>
        <div class="mcp-node"><b>MCP Server</b><small>search_knowledge 工具</small></div>
        <span class="mcp-arrow">→</span>
        <div class="mcp-node"><b>向量库</b><small>相似度检索</small></div>
      </div>
      <div class="mcp-principle">
        <p><b>MCP = Model Context Protocol</b>，一个标准协议：把「知识检索能力」暴露成标准工具，任何支持 MCP 的 IDE（Claude Code / Qoder）都能用同一套知识库。</p>
        <p>核心过程只有三步：<b>①</b> 定义工具（<code>search_knowledge</code>）→ <b>②</b> 工具内部调向量库 → <b>③</b> 通过 stdio 协议被 IDE 连接调用。</p>
      </div>
      <pre class="mcp-code">{{ MCP_SKELETON }}</pre>
    </section>

    <!-- ⑤ 检索验证 -->
    <section v-if="tab === 'verify'" class="k-panel">
      <div class="k-panel-head"><h2>评测集（Ground Truth）</h2><span>消融实验在什么数据上测、标准答案是什么</span></div>
      <div class="eval-set">
        <div v-for="e in EVAL_SET" :key="e.q" class="eval-row"><b>{{ e.q }}</b><span>应命中：{{ e.hit }}</span></div>
      </div>

      <div class="k-panel-head" style="margin-top:18px"><h2>多路检索验证 · 消融实验</h2><span>逐路去掉/单路启用，量化每路贡献</span></div>
      <div class="retriever-row">
        <button v-for="r in RETRIEVERS" :key="r.id" class="retriever" :class="{ off: !retrieverOn[r.id] }" @click="retrieverOn[r.id] = !retrieverOn[r.id]"><i>{{ retrieverOn[r.id] ? '✓' : '—' }}</i><b>{{ r.label }}</b><span>{{ r.desc }}</span></button>
        <button class="primary-button" @click="ablationRan = true">跑消融实验</button>
      </div>
      <table v-if="ablationRan" class="ablation-table">
        <thead><tr><th>检索组合</th><th>召回率</th><th>准确率</th><th>延迟</th><th>成本</th></tr></thead>
        <tbody><tr v-for="row in ABLATION" :key="row.combo"><td>{{ row.combo }}</td><td>{{ row.recall }}%</td><td>{{ row.precision }}%</td><td>{{ row.latency }}ms</td><td>¥{{ row.cost.toFixed(3) }}</td></tr></tbody>
      </table>
      <p v-else class="empty-state">选择检索器组合，点击「跑消融实验」查看对比。</p>
    </section>

    <!-- 添加抽屉 -->
    <div v-if="adding" class="drawer-mask" @click="closeAdd"></div>
    <aside v-if="adding" class="drawer">
      <div class="drawer-head"><div><p class="drawer-eyebrow">ADD SOURCE</p><b>添加{{ SOURCE_TYPES.find(t => t.id === adding)?.label }}</b></div><button class="drawer-close" @click="closeAdd">&lt;</button></div>
      <p class="drawer-desc">{{ SOURCE_TYPES.find(t => t.id === adding)?.desc }}</p>
      <div class="drawer-form">
        <label class="field"><span>名称</span><input v-model="form.name" placeholder="给这个知识源起个名" /></label>
        <label v-for="f in SOURCE_TYPES.find(t => t.id === adding)?.fields || []" :key="f.name" class="field"><span>{{ f.label }}</span><input v-model="form[f.name]" :placeholder="f.placeholder" /></label>
      </div>
      <button class="primary-button drawer-submit" @click="submitAdd">添加（Mock）</button>
    </aside>
  </section>
</template>

<style scoped>
.proto-chip { padding: 4px 10px; border-radius: 6px; background: color-mix(in srgb, var(--amber) 13%, transparent); color: var(--amber); font-size: 11px; font-weight: 600; }
.tab-bar { display: flex; gap: 6px; margin: 4px 0 16px; border-bottom: 1px solid var(--line); }
.tab { padding: 9px 15px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--muted); font-size: 13px; font-weight: 500; cursor: pointer; }
.tab:hover { color: var(--ink); }
.tab.on { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.k-panel { padding: 20px 22px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.k-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.k-panel-head h2 { margin: 0; font-size: 15px; }
.k-panel-head span { color: var(--soft); font-size: 12px; }

/* 概览画布 */
.flow-canvas { display: flex; align-items: stretch; gap: 8px; overflow-x: auto; padding: 6px 0 10px; }
.flow-node { flex: 1 0 120px; padding: 14px 12px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); cursor: pointer; text-align: center; }
.flow-node:hover { border-color: var(--brand); }
.flow-node.active { border-color: var(--brand); box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 20%, transparent); }
.flow-no { display: grid; place-items: center; width: 20px; height: 20px; margin: 0 auto 8px; border-radius: 6px; font-size: 11px; font-weight: 700; }
.tone-blue .flow-no { background: color-mix(in srgb, var(--blue) 15%, transparent); color: var(--blue); }
.tone-violet .flow-no { background: color-mix(in srgb, var(--violet) 15%, transparent); color: var(--violet); }
.tone-ok .flow-no { background: color-mix(in srgb, var(--mint) 15%, transparent); color: var(--mint); }
.tone-muted .flow-no { background: var(--panel-2); color: var(--soft); }
.flow-node b { display: block; font-size: 13px; }
.flow-node small { display: block; margin-top: 4px; color: var(--soft); font-size: 10px; line-height: 1.4; }
.flow-arrow { align-self: center; color: var(--soft); font-size: 15px; }
.flow-detail { margin-top: 12px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel-2); }
.flow-detail b { font-size: 13px; }
.flow-detail p { margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.track-label { margin: 4px 0 8px; color: var(--soft); font-size: 11px; font-weight: 600; }
.feedback-loop { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; border: 1px dashed var(--amber); border-radius: 9px; background: color-mix(in srgb, var(--amber) 7%, transparent); color: var(--amber); font-size: 12px; }
.feedback-loop b { color: var(--amber); }
.feedback-arrow { font-size: 16px; }

/* 知识源 */
.src-types { display: grid; grid-template-columns: repeat(4, 1fr); gap: 11px; margin-bottom: 20px; }
.src-type { text-align: left; padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); cursor: pointer; }
.src-type:hover { border-color: var(--brand); }
.src-type b { display: block; font-size: 13px; color: var(--blue); }
.src-type span { display: block; margin-top: 4px; color: var(--soft); font-size: 11px; }
.src-list-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }
.src-list-head b { font-size: 13px; } .src-list-head small { color: var(--soft); font-size: 11px; }
.src-row { display: grid; grid-template-columns: 84px minmax(0, 1fr) auto 28px; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line-soft); }
.src-tag { padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 600; text-align: center; }
.src-main b { display: block; font-size: 13px; } .src-main small { display: block; margin-top: 2px; color: var(--soft); font-size: 11px; }
.src-status { color: var(--mint); font-size: 11px; } .src-status.sync { color: var(--amber); }
.src-remove { width: 24px; height: 24px; border: 1px solid var(--line); border-radius: 6px; background: transparent; color: var(--soft); cursor: pointer; }
.src-remove:hover { border-color: var(--red); color: var(--red); }
.level-tag { margin-left: 6px; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
.lv-secret { background: color-mix(in srgb, var(--amber) 14%, transparent); color: var(--amber); }
.lv-internal { background: color-mix(in srgb, var(--blue) 12%, transparent); color: var(--blue); }
.lv-public { background: color-mix(in srgb, var(--mint) 12%, transparent); color: var(--mint); }
.store-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 11px; margin-bottom: 6px; }
.store-card { padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); }
.store-card b { font-size: 13px; }
.store-type { margin-left: 8px; padding: 1px 7px; border-radius: 5px; background: var(--panel); color: var(--soft); font-size: 10px; }
.store-card p { margin: 6px 0 0; color: var(--muted); font-size: 12px; }
.store-card small { display: block; margin-top: 4px; color: var(--soft); font-size: 11px; }
.eval-set { display: flex; flex-direction: column; }
.eval-row { display: flex; align-items: baseline; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--line-soft); font-size: 12px; }
.eval-row b { color: var(--ink); }
.eval-row span { color: var(--soft); }
.tone-blue { background: color-mix(in srgb, var(--blue) 12%, transparent); color: var(--blue); }
.tone-violet { background: color-mix(in srgb, var(--violet) 12%, transparent); color: var(--violet); }
.tone-ok { background: color-mix(in srgb, var(--mint) 12%, transparent); color: var(--mint); }
.tone-muted { background: var(--panel-2); color: var(--soft); }

/* 存储与对接 */
.step-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 11px; }
.mini-flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mini-flow .step { flex: 1 0 150px; }
.mini-arrow { color: var(--soft); font-size: 15px; }
.mcp-flow { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.mcp-node { flex: 1; padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); text-align: center; }
.mcp-node b { display: block; font-size: 13px; }
.mcp-node small { display: block; margin-top: 4px; color: var(--soft); font-size: 10px; }
.mcp-arrow { color: var(--soft); font-size: 15px; }
.step { padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); }
.step-no { display: grid; place-items: center; width: 22px; height: 22px; margin-bottom: 8px; border-radius: 50%; background: var(--brand); color: #fff; font-size: 11px; font-weight: 700; }
.step b { font-size: 13px; } .step p { margin: 5px 0 0; color: var(--soft); font-size: 11px; line-height: 1.5; }

/* MCP */
.mcp-principle p { margin: 8px 0; color: var(--muted); font-size: 13px; line-height: 1.7; }
.mcp-principle b { color: var(--ink); }
.mcp-principle code { background: var(--panel-2); padding: 1px 6px; border-radius: 4px; font: 12px ui-monospace, Menlo, monospace; color: var(--violet); }
.mcp-code { margin: 12px 0 0; padding: 14px; border-radius: 10px; background: var(--code-bg); color: var(--code-ink); font: 12px/1.6 ui-monospace, Menlo, monospace; overflow-x: auto; }

/* 检索验证 */
.retriever-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.retriever { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-2); cursor: pointer; }
.retriever.off { opacity: .55; }
.retriever i { font-style: normal; font-size: 11px; color: var(--mint); } .retriever.off i { color: var(--soft); }
.retriever b { font-size: 12px; } .retriever span { color: var(--soft); font-size: 11px; }
.ablation-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ablation-table th, .ablation-table td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--line-soft); }
.ablation-table th { color: var(--soft); font-weight: 600; font-size: 11px; }
.ablation-table td:not(:first-child) { text-align: right; font-family: ui-monospace, Menlo, monospace; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,.25); z-index: 90; }
.drawer { position: fixed; top: 0; right: 0; width: 400px; height: 100vh; padding: 20px; background: var(--panel); border-left: 1px solid var(--line); box-shadow: -8px 0 24px rgba(0,0,0,.1); z-index: 100; overflow-y: auto; }
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.drawer-eyebrow { margin: 0 0 4px; color: var(--soft); font-size: 11px; letter-spacing: .05em; }
.drawer-head b { font-size: 17px; }
.drawer-close { width: 30px; height: 30px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); color: var(--muted); cursor: pointer; flex-shrink: 0; }
.drawer-desc { margin: 10px 0 16px; color: var(--muted); font-size: 13px; }
.drawer-form { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field span { color: var(--muted); font-size: 12px; }
.field input { padding: 9px 11px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); font-size: 13px; }
.field input:focus { outline: none; border-color: var(--brand); }
.drawer-submit { margin-top: 16px; width: 100%; }
@media (max-width: 900px) { .src-types, .step-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .src-types, .step-row { grid-template-columns: 1fr; } .flow-canvas { flex-direction: column; } .flow-arrow { transform: rotate(90deg); } .drawer { width: 100vw; } }
</style>
