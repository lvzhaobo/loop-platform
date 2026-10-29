<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { PendingTask, Profile, RunPlan } from '../api/contracts'
const router = useRouter(), route = useRoute(), profiles = ref<Profile[]>([]), tasks = ref<PendingTask[]>([]), profileId = ref(''), taskId = ref(''), plan = ref<RunPlan | null>(null), error = ref(''), loading = ref(true), previewing = ref(false), confirming = ref(false), requestConfirm = ref(false)
const profile = computed(() => profiles.value.find(item => item.id === profileId.value))
const executionBlocker = computed(() => profile.value?.execution_blocker || '该 Profile 不满足当前受控执行组合。')
const queryValue = (name: string) => typeof route.query[name] === 'string' ? route.query[name] : ''
const executable = computed(() => profile.value?.execution_eligible === true)
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
async function preview() { if (!taskId.value) return; previewing.value = true; error.value = ''; requestConfirm.value = false; try { const result = await api.freezePlan(profileId.value, taskId.value); if (!result.ok || !result.plan) { error.value = result.error || '冻结 Run Plan 失败'; return }; plan.value = result.plan } catch (e) { error.value = e instanceof Error ? e.message : '冻结 Run Plan 失败' } finally { previewing.value = false } }
async function confirm() {
  if (!plan.value || !executionReady.value) return
  confirming.value = true; error.value = ''
  try {
    const result = await api.confirmRun(plan.value.profile.id, plan.value.task.id, plan.value.id, plan.value.digest)
    const runId = result.run?.run_id
    if (!runId) { error.value = result.error || '执行请求未被接受；未创建 Run。'; return }
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

<template>
  <section class="page plans">
    <div class="page-heading">
      <div>
        <p class="eyebrow">CONTROLLED EXECUTION</p>
        <h1>受控执行</h1>
        <p>浏览器只选择任务，服务器先冻结并返回 Plan，用户明确确认后才执行。任务或策略变化必须重新冻结与审阅。</p>
      </div>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="profile && !executionReady" class="data-warning">⚠ 执行环境未就绪：{{ readinessMessage }}。可以审阅冻结 Plan，但不能确认执行。</p>

    <!-- 步骤指示器 -->
    <div class="step-bar">
      <div class="step" :class="{ done: !!profile, on: !plan }"><span class="step-dot">1</span><b>选择 Profile</b></div>
      <span class="step-line"></span>
      <div class="step" :class="{ done: !!taskId, on: !!taskId && !plan }"><span class="step-dot">2</span><b>选择任务</b></div>
      <span class="step-line"></span>
      <div class="step" :class="{ done: !!plan, on: !!plan && !requestConfirm }"><span class="step-dot">3</span><b>冻结审阅</b></div>
      <span class="step-line"></span>
      <div class="step" :class="{ on: !!requestConfirm }"><span class="step-dot">4</span><b>确认执行</b></div>
    </div>

    <!-- 步骤 1 + 2：选择 -->
    <section class="plan-panel">
      <h2>选择执行组合与任务</h2>
      <div class="plan-form">
        <label><span>Profile（执行组合）</span><select v-model="profileId" :disabled="loading"><option v-for="item in profiles" :key="item.id" :value="item.id">{{ item.ref || item.id }} · {{ item.description || '已验证 Profile' }}</option></select></label>
        <template v-if="executable">
          <label><span>{{ taskLabel }}</span><select v-model="taskId" :disabled="!tasks.length" @change="plan = null; requestConfirm = false"><option v-for="task in tasks" :key="task.id" :value="task.id">{{ task.title }} · {{ task.id }} · P{{ task.priority }}</option></select></label>
          <button class="primary-button" :disabled="!taskId || previewing" @click="preview">{{ previewing ? '正在冻结…' : '冻结 Run Plan 供审阅' }}</button>
          <p v-if="!tasks.length" class="empty-state">{{ realDelivery ? '没有待执行的真实 GitHub 交付任务；请在「需求管理」中使用 deepseek-github 入池。' : localDeepSeek ? '没有待执行的 DeepSeek 本地生成任务；请在「需求管理」中使用 deepseek-local 入池。' : '没有待执行的安全 Fixture 任务。' }}</p>
        </template>
        <p v-else class="empty-state">此 Profile 当前只支持查看或 Plan Review，不能从正式 Studio 发起执行：{{ executionBlocker }}</p>
      </div>
    </section>

    <!-- 步骤 3：冻结审阅 -->
    <section v-if="plan" class="plan-panel">
      <div class="panel-title-row"><h2>冻结 Run Plan（待确认）</h2><code class="runid">{{ plan.run_id }}</code></div>
      <div class="plan-grid">
        <div class="plan-item"><b>任务</b><span>{{ plan.task.title }} · {{ plan.task.id }}</span></div>
        <div class="plan-item"><b>组件链</b>
          <div class="chain">
            <span class="chain-node">{{ plan.components.source }}</span><i>→</i>
            <span class="chain-node">{{ plan.components.compiler }}</span><i>→</i>
            <span class="chain-node">{{ plan.components.maker }}</span><i>→</i>
            <span class="chain-node">{{ plan.components.checkers.join(' + ') }}</span><i>→</i>
            <span class="chain-node">{{ plan.components.delivery }}</span>
          </div>
        </div>
        <div class="plan-item"><b>Plan digest</b><code class="digest">{{ plan.digest }}</code></div>
      </div>
      <button v-if="!requestConfirm" class="quiet-button" @click="requestConfirm = true">进入确认步骤</button>
    </section>

    <!-- 步骤 4：确认执行 -->
    <section v-if="requestConfirm" class="plan-panel confirm-panel">
      <h2>确认执行</h2>
      <div class="confirm-box">
        <b v-if="realDelivery">确认后将调用 DeepSeek、执行 Security/E2E Checker，并向目标 GitHub 仓库推送新 sample；目标仓 Workflow 会继续尝试 ECS 部署。这会产生模型成本和外部副作用。GitHub 推送成功不代表 ECS 已健康，须以后续 Workflow 与部署证据为准。</b>
        <b v-else-if="localDeepSeek">确认后将调用 DeepSeek，执行确定性检查并在本地保存生成代码、RunEvent 与 Evidence；不会使用 Git、SSH、发布或部署。</b>
        <b v-else>确认后将执行本地 fixture-local 流程，并写入 RunEvent/Evidence；不会调用网络、模型、Git、SSH、发布或部署。</b>
        <button class="primary-button" :disabled="confirming || !executionReady" @click="confirm">{{ confirming ? '正在创建受控 Run…' : realDelivery ? '确认并启动真实交付' : localDeepSeek ? '确认并调用 DeepSeek 生成' : '确认并真实运行' }}</button>
      </div>
    </section>
  </section>
</template>

<style scoped>
.step-bar { display: flex; align-items: center; gap: 8px; margin: 8px 0 16px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.step { display: flex; align-items: center; gap: 8px; color: var(--soft); }
.step-dot { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--panel-2); border: 1px solid var(--line); font-size: 11px; font-weight: 700; }
.step b { font-size: 12px; font-weight: 500; }
.step.done .step-dot { background: color-mix(in srgb, var(--mint) 16%, transparent); border-color: var(--mint); color: var(--mint); }
.step.done b { color: var(--mint); }
.step.on .step-dot { background: var(--brand); border-color: var(--brand); color: #fff; }
.step.on b { color: var(--brand); font-weight: 600; }
.step-line { flex: 1; height: 1px; background: var(--line); }
.plan-panel { margin-top: 14px; padding: 20px 22px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.plan-panel h2 { margin: 0 0 14px; font-size: 15px; }
.panel-title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.panel-title-row h2 { margin: 0; }
.runid { color: var(--soft); font: 11px ui-monospace, Menlo, monospace; }
.plan-form { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.plan-form label { display: grid; gap: 6px; min-width: 240px; color: var(--muted); font-size: 11px; }
.plan-form label span { font-size: 11px; }
.plan-form select { border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); padding: 9px; color: var(--ink); }
.plan-form .empty-state { flex-basis: 100%; margin: 0; }
.plan-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 14px; }
.plan-item { display: grid; gap: 4px; }
.plan-item b { color: var(--soft); font-size: 10px; font-weight: 600; }
.plan-item span { color: var(--ink); font-size: 13px; }
.chain { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.chain-node { padding: 3px 9px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--line); color: var(--ink); font-size: 12px; }
.chain i { color: var(--soft); font-style: normal; }
.digest { color: var(--muted); font: 11px ui-monospace, Menlo, monospace; overflow-wrap: anywhere; }
.confirm-panel { border-color: color-mix(in srgb, var(--amber) 45%, var(--line)); }
.confirm-box { display: flex; align-items: center; gap: 16px; justify-content: space-between; padding: 14px; border: 1px solid color-mix(in srgb, var(--amber) 45%, var(--line)); border-radius: 10px; background: color-mix(in srgb, var(--amber) 7%, transparent); color: var(--amber); font-size: 12px; }
.confirm-box b { font-weight: 500; line-height: 1.6; }
.confirm-box .primary-button { flex-shrink: 0; }
@media (max-width: 700px) { .step-bar { flex-wrap: wrap; } .step-line { display: none; } .confirm-box { align-items: stretch; flex-direction: column; } }
</style>
