<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import RunDetailDrawer from '../components/RunDetailDrawer.vue'
import { studioRepository } from '../data/repository'
import { statusMeta, type Run, type RunStatus } from '../data/mock'

const runs = ref<Run[]>([])
const selectedId = ref('')
const drawerOpen = ref(false)
const filter = ref<'all' | RunStatus>('all')
const warning = ref('')
const loading = ref(true)
const filtered = computed(() => runs.value.filter(run => filter.value === 'all' || run.status === filter.value))
const selected = computed(() => runs.value.find(run => run.id === selectedId.value) ?? filtered.value[0] ?? null)
const openRun = (run: Run) => { selectedId.value = run.id; drawerOpen.value = true }
onMounted(async () => { const response = await studioRepository.listRuns(); runs.value = response.data; selectedId.value = response.data[0]?.id ?? ''; warning.value = response.warning ?? ''; loading.value = false })
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">DELIVERY RUNS & GENERATION HISTORY</p><h1>运行与生成历史</h1><p>当前仅映射明确记录为 <code>case_done + pass/fail</code> 的兼容事件；不会从日志、目录或产物推断状态。点击 Run 可查看其可用事实与未接入项。</p></div><button class="quiet-button" disabled>导出不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><div class="filter-row"><button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button><button v-for="status in (Object.keys(statusMeta) as RunStatus[])" :key="status" :class="{ active: filter === status }" @click="filter = status">{{ statusMeta[status].label }}</button></div>
    <div class="runs-layout run-list-only"><div class="run-cards"><p v-if="loading" class="empty-state">正在读取 Run 投影…</p><p v-else-if="!filtered.length" class="empty-state">没有可保守映射的 Run；这不代表没有历史执行记录。</p><button v-for="run in filtered" :key="run.id" :class="['run-card', { selected: selected?.id === run.id }]" :aria-label="`打开 ${run.title} 的运行详情`" @click="openRun(run)"><span :class="['status', run.status]">{{ statusMeta[run.status].label }}</span><h3>{{ run.title }}</h3><p>{{ run.id }} · {{ run.profile }}</p><div><span>{{ run.stage }}</span><span>{{ run.elapsed }}</span><span>{{ run.evidence }}</span><b>查看详情 →</b></div></button></div></div>
    <RunDetailDrawer :open="drawerOpen" :run="selected" :source-kind="studioRepository.source.label" @close="drawerOpen = false" />
  </section>
</template>
