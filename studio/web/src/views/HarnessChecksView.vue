<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { CheckItem, ChecksResponse } from '../api/contracts'

// Harness 约束：按「前馈 / 反馈 × 计算型 / 推理型」四象限整理，支持筛选与点击查看详情。

const data = ref<ChecksResponse | null>(null)
const error = ref('')
const loading = ref(true)
const search = ref('')
const quadFilter = ref('all')
const selected = ref<CheckItem | null>(null)

const QUADRANT_META: Record<string, { feed: string; type: string; desc: string }> = {
  'inject-rule': { feed: '前馈', type: '计算型', desc: '生成前注入规则，机械确定' },
  'inject-infer': { feed: '前馈', type: '推理型', desc: '生成前注入意图，需模型推断' },
  'check-rule': { feed: '反馈', type: '计算型', desc: '生成后逐条检查，客观可复现' },
  'check-infer': { feed: '反馈', type: '推理型', desc: '生成后 LLM-as-Judge，主观判断' },
}
const QUADRANT_ORDER = ['inject-rule', 'inject-infer', 'check-rule', 'check-infer']
const QUADRANT_OPTIONS = [
  { value: 'all', label: '全部象限' },
  { value: 'inject-rule', label: '前馈 · 计算型' },
  { value: 'inject-infer', label: '前馈 · 推理型' },
  { value: 'check-rule', label: '反馈 · 计算型' },
  { value: 'check-infer', label: '反馈 · 推理型' },
]

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  const all = data.value?.checks || []
  return all.filter(c => {
    if (quadFilter.value !== 'all' && c.quadrant !== quadFilter.value) return false
    if (!q) return true
    return (c.name + c.id + c.category + c.description).toLowerCase().includes(q)
  })
})

const groups = computed(() => QUADRANT_ORDER.map(key => {
  const meta = QUADRANT_META[key]
  return { key, ...meta, items: filtered.value.filter(c => c.quadrant === key) }
}))

const total = computed(() => data.value?.summary?.total || 0)

function openDetail(c: CheckItem) { selected.value = c }
function closeDetail() { selected.value = null }

onMounted(async () => {
  loading.value = true; error.value = ''
  try { data.value = await api.checks() }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取约束清单' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page checks">
    <div class="page-heading">
      <div>
        <p class="eyebrow">HARNESS CONSTRAINTS</p>
        <h1>Harness 约束</h1>
        <p>装配运行环境的前馈约束与反馈检查，按「前馈/反馈 × 计算型/推理型」四象限组织。点击条目查看详情。</p>
      </div>
      <div class="checks-total">共 <b>{{ loading ? '—' : total }}</b> 项约束</div>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <input v-model="search" class="search" placeholder="搜索名称 / 类别 / 描述" />
      <select v-model="quadFilter" class="quad-select">
        <option v-for="o in QUADRANT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <span class="filter-count">{{ filtered.length }} 项</span>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取约束清单…</p>

    <!-- 四象限 2×2 -->
    <template v-else>
      <div class="quad-matrix">
        <section v-for="g in groups" :key="g.key" class="quad-panel">
          <header class="quad-head">
            <span class="quad-feed" :class="g.feed === '前馈' ? 'feed' : 'back'">{{ g.feed }}</span>
            <span class="quad-type">{{ g.type }}</span>
            <small>{{ g.items.length }} 项</small>
          </header>
          <p class="quad-desc">{{ g.desc }}</p>
          <div v-if="g.items.length" class="check-list">
            <button v-for="c in g.items" :key="c.id" class="check-item" @click="openDetail(c)">
              <span class="check-name">{{ c.name }}</span>
              <span class="check-cat">{{ c.category }}</span>
            </button>
          </div>
          <p v-else class="quad-empty">无匹配约束</p>
        </section>
      </div>
    </template>

    <!-- 详情侧边栏 -->
    <div v-if="selected" class="drawer-mask" @click="closeDetail"></div>
    <aside v-if="selected" class="drawer">
      <div class="drawer-head">
        <div>
          <p class="drawer-eyebrow">{{ QUADRANT_META[selected.quadrant]?.feed }} · {{ QUADRANT_META[selected.quadrant]?.type }}</p>
          <b>{{ selected.name }}</b>
        </div>
        <button class="drawer-close" @click="closeDetail">&lt;</button>
      </div>
      <p class="drawer-desc">{{ selected.description }}</p>
      <dl class="drawer-meta">
        <div><dt>ID</dt><dd>{{ selected.id }}</dd></div>
        <div><dt>类别</dt><dd>{{ selected.category }}</dd></div>
        <div><dt>象限</dt><dd>{{ selected.quadrant_label }}</dd></div>
        <div><dt>自动</dt><dd>{{ selected.auto ? '是' : '否' }}</dd></div>
        <div><dt>Mock</dt><dd>{{ selected.mock ? '是' : '否' }}</dd></div>
        <div><dt>状态</dt><dd>{{ selected.active ? '启用' : '停用' }}</dd></div>
      </dl>
    </aside>
  </section>
</template>

<style scoped>
.checks-total { color: var(--soft); font-size: 12px; }
.checks-total b { color: var(--ink); font-size: 18px; margin-left: 2px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.search { flex: 1; max-width: 340px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); font-size: 13px; }
.search:focus { outline: none; border-color: var(--brand); }
.quad-select { padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); font-size: 13px; }
.filter-count { color: var(--soft); font-size: 12px; }

.quad-matrix { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.quad-panel { padding: 16px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.quad-head { display: flex; align-items: center; gap: 8px; }
.quad-feed { padding: 2px 8px; border-radius: 5px; font-size: 10px; font-weight: 700; }
.quad-feed.feed { background: color-mix(in srgb, var(--blue) 13%, transparent); color: var(--blue); }
.quad-feed.back { background: color-mix(in srgb, var(--violet) 13%, transparent); color: var(--violet); }
.quad-type { font-size: 12px; font-weight: 600; }
.quad-head small { margin-left: auto; color: var(--soft); font-size: 11px; }
.quad-desc { margin: 8px 0 10px; color: var(--soft); font-size: 11px; }
.check-list { display: flex; flex-direction: column; gap: 6px; }
.check-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 11px; border: 1px solid var(--line-soft); border-radius: 8px; background: var(--panel-2); cursor: pointer; text-align: left; }
.check-item:hover { border-color: var(--brand); background: color-mix(in srgb, var(--brand) 6%, transparent); }
.check-name { font-size: 12px; font-weight: 600; color: var(--ink); }
.check-cat { color: var(--soft); font-size: 10px; flex-shrink: 0; }
.quad-empty { color: var(--soft); font-size: 12px; padding: 8px 0; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,.25); z-index: 90; }
.drawer { position: fixed; top: 0; right: 0; width: 380px; height: 100vh; padding: 20px; background: var(--panel); border-left: 1px solid var(--line); box-shadow: -8px 0 24px rgba(0,0,0,.1); z-index: 100; overflow-y: auto; }
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.drawer-eyebrow { margin: 0 0 4px; color: var(--soft); font-size: 11px; letter-spacing: .05em; }
.drawer-head b { font-size: 17px; }
.drawer-close { width: 30px; height: 30px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); color: var(--muted); cursor: pointer; flex-shrink: 0; }
.drawer-close:hover { background: var(--line); }
.drawer-desc { margin: 12px 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.drawer-meta { margin: 0; }
.drawer-meta div { display: grid; grid-template-columns: 60px 1fr; gap: 10px; padding: 9px 0; border-top: 1px solid var(--line-soft); font-size: 12px; }
.drawer-meta dt { color: var(--soft); }
.drawer-meta dd { margin: 0; color: var(--ink); }
@media (max-width: 760px) { .quad-matrix { grid-template-columns: 1fr; } .drawer { width: min(380px, 100vw); } }
</style>
