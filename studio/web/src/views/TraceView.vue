<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { TraceEvent } from '../api/contracts'

// 日志与 Trace：运行事件时间线，数据来自 /api/trace（append-only 事件流）。

const events = ref<TraceEvent[]>([])
const error = ref('')
const loading = ref(true)
const filter = ref('')

const filtered = computed(() => {
  const q = filter.value.trim().toLowerCase()
  if (!q) return events.value
  return events.value.filter(e => JSON.stringify(e).toLowerCase().includes(q))
})

// 事件类型 → 语义中文 + 颜色
const EVENT_META: Record<string, { label: string; tone: string }> = {
  batch_start: { label: '批次开始', tone: 'tone-blue' },
  batch_done: { label: '批次结束', tone: 'tone-blue' },
  gen_start: { label: '生成开始', tone: 'tone-stat' },
  gen_done: { label: '生成完成', tone: 'tone-stat' },
  verify_start: { label: '验收开始', tone: 'tone-stat' },
  verify_done: { label: '验收完成', tone: 'tone-stat' },
  deliver_start: { label: '交付开始', tone: 'tone-ok' },
  deliver_done: { label: '交付完成', tone: 'tone-ok' },
}
const metaOf = (e: TraceEvent) => EVENT_META[e.event || ''] || { label: e.event || '事件', tone: 'tone-muted' }
const detailOf = (e: TraceEvent) => {
  const parts: string[] = []
  if (e.case) parts.push(String(e.case))
  if (e.attempt !== undefined) parts.push(`attempt ${e.attempt}`)
  if (e.ok !== undefined) parts.push(e.ok ? '通过' : '未通过')
  if (e.passed !== undefined && e.total !== undefined) parts.push(`${e.passed}/${e.total}`)
  if (e.files !== undefined) parts.push(`${e.files} 文件`)
  if (e.cost_yuan !== undefined) parts.push(`¥${e.cost_yuan}`)
  return parts.join(' · ')
}

onMounted(async () => {
  loading.value = true; error.value = ''
  try { const r = await api.trace(); events.value = r.events }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取 Trace 事件' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page trace">
    <div class="page-heading">
      <div>
        <p class="eyebrow">LOGS &amp; TRACE</p>
        <h1>日志与 Trace</h1>
        <p>每次运行的 append-only 事件流，可回放、可追溯。</p>
      </div>
      <input v-model="filter" class="trace-filter" placeholder="搜索事件 / case / 关键字" />
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取 Trace 事件…</p>
    <p v-else-if="!filtered.length" class="empty-state">没有匹配的事件。</p>

    <div v-else class="trace-list">
      <div v-for="(e, i) in filtered" :key="i" class="trace-row">
        <span class="trace-time">{{ e._ts || '—' }}</span>
        <span class="trace-tag" :class="metaOf(e).tone">{{ metaOf(e).label }}</span>
        <span class="trace-detail">{{ detailOf(e) || e.event }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.trace-filter { padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); font-size: 13px; min-width: 220px; }
.trace-filter:focus { outline: none; border-color: var(--brand); }
.trace-list { border: 1px solid var(--line); border-radius: 12px; background: var(--panel); overflow: hidden; }
.trace-row { display: grid; grid-template-columns: 130px 92px minmax(0, 1fr); gap: 12px; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--line-soft); font-size: 12px; }
.trace-row:last-child { border-bottom: 0; }
.trace-row:hover { background: var(--panel-2); }
.trace-time { color: var(--soft); font: 10px ui-monospace, Menlo, monospace; }
.trace-tag { justify-self: start; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
.trace-detail { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tone-blue { background: color-mix(in srgb, var(--blue) 12%, transparent); color: var(--blue); }
.tone-stat { background: color-mix(in srgb, var(--violet) 12%, transparent); color: var(--violet); }
.tone-ok { background: color-mix(in srgb, var(--mint) 12%, transparent); color: var(--mint); }
.tone-muted { background: var(--panel-2); color: var(--soft); }
@media (max-width: 700px) { .trace-row { grid-template-columns: 1fr; gap: 4px; } }
</style>
