<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { studioRepository } from '../data/repository'
import { statusMeta, type Run, type RunStatus } from '../data/mock'

const runs = ref<Run[]>([])
const warning = ref('')
const loading = ref(true)
const summary = computed(() => (Object.keys(statusMeta) as RunStatus[]).map(status => ({ status, count: runs.value.filter(run => run.status === status).length })))
const milestones = [{ title: '并行迁移与 Vue 应用壳', percent: 100, state: '已完成', detail: '旧 Flask 页面保持默认入口；Vue 仅在 5175 预览。' }, { title: '页面结构与视觉验收', percent: 80, state: '进行中', detail: '已覆盖 9 个入口，仍需人工完成桌面与窄屏走查。' }, { title: '脱敏兼容读取', percent: 60, state: '进行中', detail: '需求、Profile/Plan、Checker 与明确 trace 事件已接入只读投影。' }, { title: '事件、证据与 Observability API', percent: 0, state: '未开始', detail: '需要 RunEvent、evidence bundle 和五态可复算投影。' }]
onMounted(async () => { const response = await studioRepository.listRuns(); runs.value = response.data; warning.value = response.warning ?? ''; loading.value = false })
</script>

<template>
  <section class="page"><div class="hero"><div><p class="eyebrow">AI DELIVERY CONTROL</p><h1>让交付状态<br>可追溯，而非猜测。</h1><p class="lede">当前工作台优先呈现有明确来源的事实；对旧系统无法证明的生命周期、证据和交付结果保持暂不可用。</p></div><button class="primary-button" disabled>创建交付计划不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><section class="metric-grid"><article v-for="item in summary" :key="item.status" class="metric-card"><span>{{ statusMeta[item.status].label }}</span><b>{{ loading ? '—' : item.count }}</b><small>当前数据源可映射的 Run</small></article></section>
    <section class="workspace-panel"><div class="panel-heading"><div><h2>来源与边界</h2><span>当前摘要不扫描 output、不读取最新日志，也不触发任何执行操作</span></div></div><div class="compatibility-note"><b>何时可以显示完整运营面？</b><p>Phase 4 建立版本化 append-only RunEvent、artifact / Spec / check evidence bundle 与只读 Observability 投影后，才会展示生命周期、覆盖率、健康趋势和 Delivery 结论。</p></div></section>
    <div class="section-title"><h2>最近可映射 Run</h2><RouterLink to="/runs">查看全部 →</RouterLink></div><div v-if="runs.length" class="run-table"><RouterLink v-for="run in runs" :key="run.id" to="/runs" class="run-row"><span class="run-icon">{{ statusMeta[run.status].icon }}</span><div><b>{{ run.title }}</b><small>{{ run.id }}</small></div><span :class="['status', run.status]">{{ statusMeta[run.status].label }}</span><span>{{ run.profile }}</span><span>{{ run.evidence }}</span></RouterLink></div><p v-else-if="!loading" class="empty-state">当前没有可保守映射的 Run；这不代表没有执行历史。</p><p v-else class="empty-state">正在读取 Run 投影…</p>
    <div class="section-title"><h2>改造进度与下一步</h2><RouterLink to="/developer">查看接口边界 →</RouterLink></div><section class="roadmap-panel"><div class="roadmap-summary"><p class="eyebrow">FRONTEND MIGRATION ESTIMATE</p><b>前端迁移估算</b><strong>65%</strong><span>这是页面和适配层的实施估算，不是平台完成度或运行质量指标。</span><i><em></em></i></div><div class="roadmap-list"><article v-for="milestone in milestones" :key="milestone.title"><div><b>{{ milestone.title }}</b><span>{{ milestone.detail }}</span></div><em :class="milestone.percent === 100 ? 'done' : milestone.percent ? 'active' : ''">{{ milestone.state }} · {{ milestone.percent }}%</em><i><small :style="{ width: `${milestone.percent}%` }"></small></i></article></div></section>
  </section>
</template>
