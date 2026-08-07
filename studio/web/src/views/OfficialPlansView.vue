<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { PendingTask, Profile, RunPlan } from '../api/contracts'
const router = useRouter(), route = useRoute(), profiles = ref<Profile[]>([]), tasks = ref<PendingTask[]>([]), profileId = ref(''), taskId = ref(''), plan = ref<RunPlan | null>(null), error = ref(''), loading = ref(true), previewing = ref(false), confirming = ref(false), requestConfirm = ref(false)
const profile = computed(() => profiles.value.find(item => item.id === profileId.value))
const permission = (name: string) => profile.value?.policy?.[name] === true
const queryValue = (name: string) => typeof route.query[name] === 'string' ? route.query[name] : ''
const executable = computed(() => {
  const selected = profile.value
  if (!selected) return false
  const noExternalPermissions = ['allow_network', 'allow_model', 'allow_git', 'allow_ssh', 'allow_publish', 'allow_deploy'].every(name => !permission(name))
  if (selected.maker === 'sample' && selected.delivery === 'local_artifact') return noExternalPermissions
  if (selected.maker !== 'deepseek' || !permission('allow_network') || !permission('allow_model')) return false
  if (selected.delivery === 'local_artifact') return ['allow_git', 'allow_ssh', 'allow_publish', 'allow_deploy'].every(name => !permission(name))
  return selected.delivery === 'github_workflow' && selected.checkers?.includes('security') && selected.checkers?.includes('e2e') && permission('allow_git') && permission('allow_publish') && permission('allow_deploy') && !permission('allow_ssh')
})
const executionReady = computed(() => profile.value?.execution_readiness?.ready !== false)
const readinessMessage = computed(() => profile.value?.execution_readiness?.blockers.join('；') || '')
const realDelivery = computed(() => profile.value?.delivery === 'github_workflow')
const localDeepSeek = computed(() => profile.value?.maker === 'deepseek' && profile.value?.delivery === 'local_artifact')
const taskLabel = computed(() => realDelivery.value ? '真实 GitHub 交付任务' : localDeepSeek.value ? '真实 DeepSeek 本地生成任务' : '安全 Fixture 任务')
async function loadTasks() {
  plan.value = null; requestConfirm.value = false; tasks.value = []; taskId.value = ''; error.value = ''
  if (!executable.value) return
  try {
    tasks.value = (await api.pendingTasks(profileId.value)).tasks
    const requestedTask = queryValue('task')
    if (requestedTask && tasks.value.some(task => task.id === requestedTask)) taskId.value = requestedTask
    else {
      taskId.value = tasks.value[0]?.id || ''
      if (requestedTask) error.value = `请求的任务 ${requestedTask} 不属于当前 Profile 的待执行队列；请重新选择。`
    }
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取 Profile 任务' }
}
watch(profileId, () => { if (!loading.value) void loadTasks() })
watch(() => route.query.task, () => { if (!loading.value && profileId.value) void loadTasks() })
watch(() => route.query.profile, value => {
  if (loading.value) return
  const requested = typeof value === 'string' ? value : ''
  if (!requested) return
  if (!profiles.value.some(item => item.id === requested)) { error.value = `请求的 Profile ${requested} 不可用；已保留当前选择。`; return }
  if (profileId.value !== requested) profileId.value = requested
  else void loadTasks()
})
async function preview() { if (!taskId.value) return; previewing.value = true; error.value = ''; requestConfirm.value = false; try { plan.value = (await api.freezePlan(profileId.value, taskId.value)).plan } catch (e) { error.value = e instanceof Error ? e.message : '冻结 Run Plan 失败' } finally { previewing.value = false } }
async function confirm() {
  if (!plan.value || !executionReady.value) return
  confirming.value = true; error.value = ''
  try {
    const result = await api.confirmRun(plan.value.profile.id, plan.value.task.id, plan.value.id, plan.value.digest)
    const runId = result.run?.run_id
    if (!runId) { error.value = result.error || '执行请求未被接受；未创建 Run。'; return }
    // 不论业务结论 passed/failed，只要后端已经创建 Run 都进入详情并继续追踪事件。
    await router.push({ path: `/runs/${encodeURIComponent(runId)}`, query: { follow: '1' } })
  } catch (e) { error.value = e instanceof Error ? e.message : '执行请求失败；未跳转到 Run Detail' }
  finally { confirming.value = false }
}
onMounted(async () => {
  try {
    profiles.value = (await api.profiles()).profiles.filter(item => item.valid)
    const requested = queryValue('profile')
    profileId.value = profiles.value.some(item => item.id === requested) ? requested : profiles.value.find(item => item.id === 'deepseek-local')?.id || profiles.value.find(item => item.id === 'deepseek-github')?.id || profiles.value.find(item => item.id === 'fixture-local')?.id || profiles.value[0]?.id || ''
    await loadTasks()
    if (requested && requested !== profileId.value) error.value = `请求的 Profile ${requested} 不可用；已选择默认可执行 Profile。`
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取 Profile' }
  finally { loading.value = false }
})
</script>
<template><section class="page"><div class="page-heading"><div><p class="eyebrow">PROFILE → FROZEN PLAN → CONFIRM RUN</p><h1>受控执行</h1><p>浏览器只选择 Adapter 提供且绑定当前 Profile 的任务；服务器先冻结并返回 Plan，再由用户明确确认。确认只会执行该 Plan，任务或策略变化必须重新冻结与审阅。</p></div></div><p v-if="error" class="data-warning">⚠ {{ error }}</p><p v-if="profile && !executionReady" class="data-warning">⚠ 执行环境未就绪：{{ readinessMessage }}。可以审阅冻结 Plan，但不能确认执行。</p><section class="workspace-panel plan-form"><label>Profile<select v-model="profileId" :disabled="loading"><option v-for="item in profiles" :key="item.id" :value="item.id">{{ item.ref || item.id }} · {{ item.description || '已验证 Profile' }}</option></select></label><template v-if="executable"><label>{{ taskLabel }}<select v-model="taskId" :disabled="!tasks.length" @change="plan = null; requestConfirm = false"><option v-for="task in tasks" :key="task.id" :value="task.id">{{ task.title }} · {{ task.id }} · P{{ task.priority }}</option></select></label><button class="primary-button" :disabled="!taskId || previewing" @click="preview">{{ previewing ? '正在冻结…' : '冻结 Run Plan 供审阅' }}</button><p v-if="!tasks.length" class="empty-state">{{ realDelivery ? '没有待执行的真实 GitHub 交付任务；请在“新建需求”中使用 deepseek-github 入池。' : localDeepSeek ? '没有待执行的 DeepSeek 本地生成任务；请在“新建需求”中使用 deepseek-local 入池。' : '没有待执行的安全 Fixture 任务。' }}</p></template><p v-else class="empty-state">此 Profile 当前只支持查看或 Plan Review，不能从正式 Studio 发起执行。</p></section><section v-if="plan" class="workspace-panel plan-preview"><div class="panel-heading"><div><h2>冻结 Run Plan（待确认）</h2><span>{{ plan.run_id }}</span></div></div><div class="plan-grid"><p><b>任务</b>{{ plan.task.title }} · {{ plan.task.id }}</p><p><b>组件</b>{{ plan.components.source }} → {{ plan.components.compiler }} → {{ plan.components.maker }} → {{ plan.components.checkers.join(', ') }} → {{ plan.components.delivery }}</p><p><b>Plan digest</b><code>{{ plan.digest }}</code></p></div><button v-if="!requestConfirm" class="quiet-button" @click="requestConfirm = true">进入确认步骤</button><div v-else class="confirm-box"><b v-if="realDelivery">确认后将调用 DeepSeek、执行 Security/E2E Checker，并向目标 GitHub 仓库推送新 sample；目标仓 Workflow 会继续尝试 ECS 部署。这会产生模型成本和外部副作用。GitHub 推送成功不代表 ECS 已健康，须以后续 Workflow 与部署证据为准。</b><b v-else-if="localDeepSeek">确认后将调用 DeepSeek，执行确定性检查并在本地保存生成代码、RunEvent 与 Evidence；不会使用 Git、SSH、发布或部署。</b><b v-else>确认后将执行本地 fixture-local 流程，并写入 RunEvent/Evidence；不会调用网络、模型、Git、SSH、发布或部署。</b><button class="primary-button" :disabled="confirming || !executionReady" @click="confirm">{{ confirming ? '正在执行…' : realDelivery ? '确认并启动真实交付' : localDeepSeek ? '确认并调用 DeepSeek 生成' : '确认并真实运行' }}</button></div></section></section></template>
<style scoped>.plan-form{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.plan-form label{display:grid;gap:6px;min-width:240px;color:var(--muted);font-size:11px}.plan-form select{border:1px solid var(--line);border-radius:8px;background:var(--panel-2);padding:9px;color:var(--ink)}.plan-form .empty-state{flex-basis:100%;margin:0}.plan-preview{margin-top:14px}.plan-grid{display:grid;gap:10px;margin:15px 0}.plan-grid p{display:grid;gap:4px;margin:0;color:var(--muted);font-size:12px}.plan-grid b{color:var(--soft);font-size:10px}.plan-grid code{overflow-wrap:anywhere}.confirm-box{display:flex;align-items:center;gap:14px;justify-content:space-between;padding:13px;margin-top:13px;border:1px solid color-mix(in srgb,var(--amber) 45%,var(--line));border-radius:10px;color:var(--amber);font-size:12px}@media(max-width:620px){.confirm-box{align-items:stretch;flex-direction:column}}</style>
