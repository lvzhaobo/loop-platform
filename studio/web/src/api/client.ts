import { currentDataSource } from '../data/repository'
import type { ApiEnvelope, ArtifactResponse, BacklogResponse, ChecksResponse, ConfirmResponse, CoverageResponse, KnowledgeResponse, LifecycleResponse, PipelineResponse, PlanResponse, ProfileComposerCatalogResponse, ProfileComposerPreflightResponse, ProfileDraft, ProfileSaveResponse, ProfilesResponse, RequirementDraft, RequirementsResponse, RunExecutionState, RunResponse, RunsResponse, SpecCompileResponse, TasksResponse, TraceResponse } from './contracts'

const base = import.meta.env.DEV ? '/studio-api' : ''
export const officialSource = { kind: 'event-verified' as const, label: '正式 Studio · 权威 API', detail: '页面只消费 Profile、冻结 Plan 与已验证 RunEvent / Evidence 投影；API 失败不会回退到 Mock、目录扫描或旧 trace。', refreshedAt: '请求时读取' }
currentDataSource.value = officialSource

export class ApiError extends Error { constructor(readonly status: number, message: string) { super(message) } }
async function call<T extends { ok: boolean; error?: string }>(path: string, init: RequestInit = {}, allowBusinessFailure = false): Promise<T> {
  const response = await fetch(`${base}${path}`, { ...init, headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  const body = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` })) as T
  if (!response.ok || (!body.ok && !allowBusinessFailure)) throw new ApiError(response.status, body.error || `HTTP ${response.status}`)
  return body
}
export const api = {
  profiles: () => call<ProfilesResponse>('/api/profiles'),
  saveProfileDraft: (profile: ProfileDraft) => call<ProfileSaveResponse>('/api/profile-composer/profiles', { method: 'POST', body: JSON.stringify({ profile }) }),
  pendingTasks: (profileId: string) => call<TasksResponse>(`/api/profiles/${encodeURIComponent(profileId)}/pending-tasks`),
  previewPlan: (profileId: string, taskId: string) => call<PlanResponse>('/api/run-plans/preview', { method: 'POST', body: JSON.stringify({ profile_id: profileId, task_id: taskId }) }),
  previewDraftPlan: (profileId: string, task: RequirementDraft) => call<PlanResponse>('/api/run-plans/preview', { method: 'POST', body: JSON.stringify({ profile_id: profileId, task }) }),
  freezePlan: (profileId: string, taskId: string) => call<PlanResponse>('/api/run-plans/freeze', { method: 'POST', body: JSON.stringify({ profile_id: profileId, task_id: taskId }) }, true),
  addBacklog: (title: string, specText: string, priority: number, profileId: string) => call<BacklogResponse>('/api/backlog', { method: 'POST', body: JSON.stringify({ title, spec_text: specText, priority, profile_id: profileId }) }),
  confirmRun: (profileId: string, taskId: string, planId: string, planDigest: string) => call<ConfirmResponse>('/api/profile-runs/confirm', { method: 'POST', body: JSON.stringify({ confirmed: true, profile_id: profileId, task_id: taskId, plan_id: planId, plan_digest: planDigest }) }, true),
  retryDelivery: (runId: string) => call<ConfirmResponse>(`/api/profile-runs/${encodeURIComponent(runId)}/retry-delivery`, { method: 'POST', body: JSON.stringify({ confirmed: true }) }, true),
  runPlan: (planId: string) => call<PlanResponse>(`/api/run-plans/${encodeURIComponent(planId)}`),
  runs: (status?: string) => call<RunsResponse>(`/api/observability/runs?limit=50${status ? `&status=${encodeURIComponent(status)}` : ''}`),
  run: (runId: string) => call<RunResponse>(`/api/observability/runs/${encodeURIComponent(runId)}`),
  runState: (runId: string) => call<ApiEnvelope & RunExecutionState>(`/api/profile-runs/${encodeURIComponent(runId)}/state`),
  artifact: (runId: string) => call<ArtifactResponse>(`/api/profile-runs/${encodeURIComponent(runId)}/artifact`),
  openArtifactFolder: (runId: string) => call<ApiEnvelope>(`/api/profile-runs/${encodeURIComponent(runId)}/artifact/open`, { method: 'POST' }),
  requirements: () => call<RequirementsResponse>('/api/requirements'),
  lifecycle: () => call<LifecycleResponse>('/api/observability/lifecycle'),
  coverage: () => call<CoverageResponse>('/api/observability/governance-coverage'),
  profileComposerCatalog: () => call<ProfileComposerCatalogResponse>('/api/profile-composer/catalog'),
  preflightProfileDraft: (profile: ProfileDraft) => call<ProfileComposerPreflightResponse>('/api/profile-composer/preflight', { method: 'POST', body: JSON.stringify({ profile }) }, true),
  checks: () => call<ChecksResponse>('/api/checks'),
  knowledge: () => call<KnowledgeResponse>('/api/knowledge'),
  trace: () => call<TraceResponse>('/api/trace'),
  pipeline: () => call<PipelineResponse>('/api/pipeline'),
  specCompile: (requirement: string, name: string, mock: boolean) => call<SpecCompileResponse>('/api/spec/compile', { method: 'POST', body: JSON.stringify({ requirement, name, mock }) }),
}
