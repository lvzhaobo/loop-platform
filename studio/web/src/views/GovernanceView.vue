<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { studioRepository, type Check } from '../data/repository'

const checks = ref<Check[]>([])
const warning = ref('')
const loading = ref(true)
onMounted(async () => { const response = await studioRepository.listChecks(); checks.value = response.data; warning.value = response.warning ?? ''; loading.value = false })
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">HARNESS · CHECKERS · EVIDENCE</p><h1>Harness 与质量</h1><p>当前页面读取 Checker 注册表，而不是 Run 级质量结论；规则存在或启用不等于某次执行已经通过。</p></div><button class="quiet-button" disabled>编辑约束不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><section class="governance-notes"><article><i>!</i><div><b>注册表不是证据</b><p>兼容数据只表明旧系统声明了哪些检查，不能形成覆盖率、分数或通过结论。</p></div></article><article><i>?</i><div><b>未知保持未知</b><p>无版本化 RunEvent/evidence bundle 时，治理覆盖和检查结果均显示为未接入。</p></div></article></section>
    <section class="constraint-list"><div class="panel-heading"><div><h2>Checker 注册表</h2><span>{{ loading ? '正在读取脱敏投影…' : `${checks.length} 项 · 兼容读取` }}</span></div></div><p v-if="!loading && !checks.length" class="empty-state">没有读取到安全的 Checker 注册表。</p><div v-for="check in checks" :key="check.id" class="constraint-row"><i>◇</i><div><b>{{ check.name }}</b><small>{{ check.id }} · {{ check.quadrantLabel }}</small></div><span>{{ check.category }}</span><em>{{ check.active ? 'active' : 'inactive' }} · {{ check.auto ? 'auto' : 'manual' }}</em><button disabled>详情不可用</button></div></section>
    <section class="diagnosis-grid"><article class="diagnosis-score"><p class="eyebrow">ADVISORY ONLY</p><b>—</b><h2>Better Harness 未接入 Run 级证据</h2><p>不会显示评分、趋势或硬门禁结论；现有旧报告不具备受控 digest / scope / run 绑定。</p></article><article class="diagnosis-detail"><h2>需要的 Phase 4 证据</h2><div><span>run_id 与 task</span><b class="status unavailable">未接入</b></div><div><span>artifact digest 与 scope</span><b class="status unavailable">未接入</b></div><div><span>Provider / 版本 / 采集时间</span><b class="status unavailable">未接入</b></div><div><span>Hard gate 替代</span><b>禁止</b></div></article></section>
  </section>
</template>
