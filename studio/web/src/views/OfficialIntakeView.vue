<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Profile, RequirementDraft, RunPlan } from '../api/contracts'

const router = useRouter()
const profiles = ref<Profile[]>([])
const profileId = ref('')
const title = ref('')
const description = ref('')
const priority = ref(2)
const plan = ref<RunPlan | null>(null)
const error = ref('')
const loading = ref(true)
const previewing = ref(false)
const saving = ref(false)
const selected = computed(() => profiles.value.find(item => item.id === profileId.value))
const fixture = computed(() => profileId.value === 'fixture-local')
const draft = (): RequirementDraft => ({ id: `draft-${Date.now()}`, title: title.value.trim(), source: 'studio_vue_text', priority: priority.value, spec_text: description.value.trim() })
function resetReview() { plan.value = null }
watch([profileId, title, description, priority], resetReview)
async function preview() {
  if (!profileId.value || !title.value.trim() || !description.value.trim()) { error.value = '请填写 Profile、标题和需求描述'; return }
  previewing.value = true; error.value = ''
  try { plan.value = (await api.previewDraftPlan(profileId.value, draft())).plan }
  catch (e) { error.value = e instanceof Error ? e.message : 'Plan Review 生成失败' }
  finally { previewing.value = false }
}
async function save() {
  if (!plan.value || fixture.value) return
  saving.value = true; error.value = ''
  try {
    const saved = await api.addBacklog(title.value.trim(), description.value.trim(), priority.value, profileId.value)
    await router.push(`/requirements/${encodeURIComponent(saved.id)}`)
  } catch (e) { error.value = e instanceof Error ? e.message : '需求入池失败' }
  finally { saving.value = false }
}
onMounted(async () => {
  try {
    profiles.value = (await api.profiles()).profiles.filter(item => item.valid)
    profileId.value = profiles.value.find(item => item.id === 'deepseek-local')?.id || ''
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取 Profile' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page">
    <div class="page-heading"><div><p class="eyebrow">REQUIREMENT INTAKE → REQUIREMENTS LIST</p><h1>新建需求</h1><p>先审阅无副作用 Plan；保存后立即进入需求列表。入池不会冻结 Plan、调用模型或执行任务。</p></div><RouterLink class="quiet-button" to="/requirements">查看需求列表</RouterLink></div>
    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <section class="workspace-panel intake-form">
      <label>交付 Profile<select v-model="profileId" :disabled="loading"><option disabled value="">请选择已校验 Profile</option><option v-for="item in profiles" :key="item.id" :value="item.id">{{ item.ref || item.id }} · {{ item.description || '已校验 Profile' }}</option></select></label>
      <p v-if="fixture" class="data-warning">fixture-local 是离线安全基线，只能执行预置 fixture 任务，不能用于自定义需求。</p>
      <label>需求标题<input v-model="title" placeholder="例：小朋友暑假记录" maxlength="120" /></label>
      <label>优先级<select v-model.number="priority"><option :value="1">P1</option><option :value="2">P2</option><option :value="3">P3</option></select></label>
      <label class="wide">需求描述<textarea v-model="description" rows="10" placeholder="描述页面、功能、数据字段、交互和验收要求…" /></label>
      <button class="primary-button" :disabled="previewing || !profileId" @click="preview">{{ previewing ? '正在生成 Plan Review…' : '查看 Plan Review' }}</button>
    </section>
    <section v-if="plan" class="workspace-panel review">
      <div class="panel-heading"><div><h2>Plan Review（尚未入池）</h2><span>{{ selected?.ref || profileId }}</span></div></div>
      <div class="plan-grid"><p><b>需求</b>{{ plan.task.title }} · P{{ plan.task.priority }}</p><p><b>执行链</b>{{ plan.components.source }} → {{ plan.components.compiler }} → {{ plan.components.maker }} → {{ plan.components.checkers.join(', ') }} → {{ plan.components.delivery }}</p><p><b>权限</b>网络 {{ plan.policy.allow_network ? '允许' : '禁止' }} · 模型 {{ plan.policy.allow_model ? '允许' : '禁止' }} · Git {{ plan.policy.allow_git ? '允许' : '禁止' }} · 发布 {{ plan.policy.allow_publish ? '允许' : '禁止' }}</p><p><b>Preview digest</b><code>{{ plan.digest }}</code></p></div>
      <template v-if="fixture"><p class="data-warning">该 Profile 不接受自定义需求；请选择其它 Profile 后再保存。</p></template>
      <template v-else><button class="quiet-button" :disabled="saving" @click="save">{{ saving ? '正在保存…' : '保存到需求列表（不执行）' }}</button></template>
    </section>
  </section>
</template>

<style scoped>
.intake-form{display:grid;grid-template-columns:1fr 150px;gap:13px}.intake-form label{display:grid;gap:6px;color:var(--muted);font-size:11px}.intake-form select,.intake-form input,.intake-form textarea{width:100%;border:1px solid var(--line);border-radius:8px;background:var(--panel-2);padding:9px;color:var(--ink);font:inherit}.intake-form .wide,.intake-form .data-warning,.intake-form .primary-button{grid-column:1/-1}.review{margin-top:14px}.plan-grid{display:grid;gap:10px;margin:15px 0}.plan-grid p{display:grid;gap:4px;margin:0;color:var(--muted);font-size:12px}.plan-grid b{color:var(--soft);font-size:10px}.plan-grid code{overflow-wrap:anywhere}@media(max-width:620px){.intake-form{grid-template-columns:1fr}}
</style>
