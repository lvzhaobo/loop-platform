<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { studioRepository, type ProfilePreview, type RunPlanSummary } from '../data/repository'

const profiles = ref<ProfilePreview[]>([])
const plans = ref<RunPlanSummary[]>([])
const selectedId = ref('')
const warning = ref('')
const loading = ref(true)
const selected = computed(() => profiles.value.find(profile => profile.id === selectedId.value) ?? profiles.value[0])
onMounted(async () => { const [profileResult, planResult] = await Promise.all([studioRepository.listProfiles(), studioRepository.listRunPlans()]); profiles.value = profileResult.data; plans.value = planResult.data; selectedId.value = profiles.value[0]?.id ?? ''; warning.value = [profileResult.warning, planResult.warning].filter(Boolean).join(' ') ; loading.value = false })
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">PROFILE & IMMUTABLE RUN PLAN</p><h1>Profile 与 Run Plan</h1><p>只读展示已存在的 Profile 与不可变 Plan 摘要；不会创建 dry-run、执行或持久化计划。</p></div><button class="primary-button" disabled title="兼容读取模式不调用 POST">生成 Dry-run 不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><div class="plan-layout"><aside class="profile-list"><div class="panel-heading"><div><h2>Profile</h2><span>{{ loading ? '正在读取…' : `${profiles.length} 个安全摘要` }}</span></div></div><p v-if="!loading && !profiles.length" class="empty-state">旧接口未提供可用的 Profile 摘要。</p><button v-for="profile in profiles" :key="profile.id" :class="{ selected: selected?.id === profile.id }" @click="selectedId = profile.id"><span :class="['profile-tag', profile.tag]">{{ profile.tag }}</span><b>{{ profile.id }}</b><small>{{ profile.title }}</small><em>{{ profile.status }}</em></button></aside><article class="plan-main"><template v-if="selected"><p class="eyebrow">{{ selected.ref || selected.id }}</p><h2>{{ selected.title }}</h2><div class="plan-columns"><section><h3>组件摘要</h3><div class="policy-row"><span>Compiler</span><b>{{ selected.compiler || '未声明' }}</b></div><div class="policy-row"><span>Maker</span><b>{{ selected.maker }}</b></div><div class="policy-row"><span>Delivery</span><b>{{ selected.delivery }}</b></div><div class="policy-row"><span>Checker</span><b>{{ selected.checkers?.join(', ') || '未公开' }}</b></div></section><section><h3>安全边界</h3><ul class="permission-list"><li v-for="permission in selected.permissions" :key="permission">{{ permission }}</li></ul><p class="panel-note">策略、权限、预算、输入配置及完整 Plan 内容不会被兼容投影返回。</p></section></div></template><p v-else class="empty-state">等待可安全显示的 Profile。</p></article></div>
    <section class="workspace-panel plan-summary-panel"><div class="panel-heading"><div><h2>已持久化 Run Plan 摘要</h2><span>完整 Plan、task、components、policy 均不可用</span></div></div><p v-if="!plans.length" class="empty-state">没有可展示的 Plan 摘要。</p><div v-for="plan in plans" :key="plan.id" class="compat-row"><code>{{ plan.id }}</code><b>{{ plan.profileRef }}</b><span>{{ plan.status }} · {{ plan.createdAt }}</span><small>digest: {{ plan.digest }}</small></div></section>
  </section>
</template>
