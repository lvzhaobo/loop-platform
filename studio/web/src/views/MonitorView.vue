<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { studioRepository, type TraceEvent } from '../data/repository'

const events = ref<TraceEvent[]>([])
const warning = ref('')
const loading = ref(true)
onMounted(async () => { const response = await studioRepository.listTraceEvents(); events.value = response.data; warning.value = response.warning ?? ''; loading.value = false })
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">OBSERVABILITY & TRACE</p><h1>监控与追溯</h1><p>这里仅显示旧 trace 中可安全、明确映射的 <code>case_done</code> 事件。它不是 append-only 事件系统，也不提供指标结论。</p></div><button class="quiet-button" disabled>导出不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><section class="governance-notes"><article><i>—</i><div><b>聚合指标未接入</b><p>通过率、成本、尝试次数、证据完整度与趋势需要可复算的 Phase 4 事件投影。</p></div></article><article><i>✓</i><div><b>保守映射</b><p>只有事件自身显式写入 pass 或 fail 时才显示；其他原始 trace 字段不会发送到浏览器。</p></div></article></section>
    <section class="trace-panel"><div class="panel-heading"><div><h2>兼容事件流</h2><span>{{ loading ? '正在读取…' : `${events.length} 个可映射事件` }}</span></div></div><p v-if="!loading && !events.length" class="empty-state">没有可安全映射的 trace 事件。</p><div v-for="event in events" :key="`${event.time}-${event.runId}`" class="trace-row"><time>{{ event.time }}</time><span :class="['trace-dot', event.result === 'fail' ? 'error' : 'success']"></span><code>{{ event.event }}</code><div><b>{{ event.title }}</b><small>{{ event.runId || 'run_id 未提供' }} · {{ event.profile }} · attempts: {{ event.attempts ?? '—' }} · elapsed: {{ event.elapsed }}</small></div><span :class="['status', event.result === 'pass' ? 'passed' : 'failed']">{{ event.result === 'pass' ? '已通过' : '未通过' }}</span></div></section>
  </section>
</template>
