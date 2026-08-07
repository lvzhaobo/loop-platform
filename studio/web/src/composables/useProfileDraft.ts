import { reactive } from 'vue'
import type { ComposerStage, ProfileDraft } from '../api/contracts'

const queueDefaults = () => ({ backlog_path: 'data/backlog.json', state_path: 'data/state.json' })
const githubDefaults = () => ({ repo: 'github.com/lvzhaobo/loop-sample.git', branch: 'main', prefix: 'sample', port_base: 1000, workflow_deploy: true })
const defaultDraft = (): ProfileDraft => ({
  id: 'custom-local', version: 1, description: '待保存的交付 Profile：本地需求 → 编译 → 生成 → 检查 → 交付。',
  source: { name: 'local_queue', config: queueDefaults() }, compiler: 'simple', maker: 'sample', checkers: ['security'], delivery: 'local_artifact', delivery_config: {},
  policy: { max_attempts: 1, allow_network: false, allow_model: false, allow_git: false, allow_ssh: false, allow_publish: false, allow_deploy: false, on_unavailable: 'block', timeout_seconds: 120, cost_limit_yuan: 0 },
})
const draft = reactive<ProfileDraft>(defaultDraft())
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
export function useProfileDraft() {
  function replaceDraft(next: ProfileDraft) { Object.assign(draft, clone(next)) }
  function resetDraft() { replaceDraft(defaultDraft()) }
  function updateStage(stage: Exclude<ComposerStage, 'checker'>, value: string) {
    if (stage === 'source') draft.source = { name: value, config: queueDefaults() }
    else if (stage === 'compiler') draft.compiler = value
    else if (stage === 'maker') draft.maker = value
    else { draft.delivery = value; draft.delivery_config = value === 'github_workflow' ? githubDefaults() : {} }
  }
  function toggleChecker(checker: string) { draft.checkers = draft.checkers.includes(checker) ? draft.checkers.filter(item => item !== checker) : [...draft.checkers, checker] }
  function moveChecker(checker: string, direction: -1 | 1) { const index = draft.checkers.indexOf(checker), target = index + direction; if (index < 0 || target < 0 || target >= draft.checkers.length) return; const values = [...draft.checkers]; [values[index], values[target]] = [values[target], values[index]]; draft.checkers = values }
  return { draft, replaceDraft, resetDraft, updateStage, toggleChecker, moveChecker }
}
