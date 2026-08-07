<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { studioRepository, type Requirement } from '../data/repository'

const requirements = ref<Requirement[]>([])
const selectedId = ref('')
const filter = ref<'all' | 'pending' | 'complete'>('all')
const warning = ref('')
const loading = ref(true)
const selected = computed(() => requirements.value.find(item => item.id === selectedId.value) ?? requirements.value[0])
const filtered = computed(() => requirements.value.filter(item => filter.value === 'all' || (filter.value === 'pending' ? item.pending : !item.pending)))
onMounted(async () => { const response = await studioRepository.listRequirements(); requirements.value = response.data; selectedId.value = response.data[0]?.id ?? ''; warning.value = response.warning ?? ''; loading.value = false })
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">REQUIREMENTS & SPEC</p><h1>需求与 Spec</h1><p>兼容模式只展示脱敏的需求队列摘要；原始文档、token 与 Spec 正文不会发送到浏览器。</p></div><button class="primary-button" disabled title="兼容读取模式不支持写入">添加需求不可用</button></div>
    <p v-if="warning" class="data-warning">⚠ {{ warning }}</p><div class="contract-toolbar"><div class="chip-group"><button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button><button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待处理</button><button :class="{ active: filter === 'complete' }" @click="filter = 'complete'">已完成</button></div><span class="compat-caption">{{ loading ? '正在读取脱敏投影…' : `共 ${filtered.length} 项` }}</span></div>
    <div class="contract-workspace"><aside class="requirement-list"><p v-if="!loading && !filtered.length" class="empty-state">没有可显示的需求摘要。</p><button v-for="item in filtered" :key="item.id" :class="{ selected: selected?.id === item.id }" @click="selectedId = item.id"><span>{{ item.id }} · P{{ item.priority }}</span><b>{{ item.title }}</b><small>{{ item.pending ? '待处理' : '已完成' }} · {{ item.status }}</small><em>{{ item.profileId }}</em></button></aside><article class="contract-detail"><template v-if="selected"><p class="eyebrow">{{ selected.id }} · 脱敏兼容摘要</p><h2>{{ selected.title }}</h2><div class="contract-summary"><div><b>P{{ selected.priority }}</b><span>优先级</span></div><div><b>{{ selected.attempts ?? '—' }}</b><span>历史尝试</span></div><div><b>{{ selected.pending ? '待处理' : '已完成' }}</b><span>旧队列状态</span></div></div><div class="compatibility-note"><b>安全边界</b><p>原始需求正文、来源 token、Spec 文档追溯、关联 Run 与验收结论均未在该兼容接口中提供，因此显示为暂不可用。</p><code>profile_id: {{ selected.profileId }}</code></div></template><p v-else class="empty-state">等待可安全展示的需求摘要。</p></article></div>
  </section>
</template>
