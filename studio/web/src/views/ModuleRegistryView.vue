<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ComponentDescriptor, ComposerStage, Profile, ProfileComposerCatalog } from '../api/contracts'
import { useProfileDraft } from '../composables/useProfileDraft'

// 单个可插拔模块的配置屏：按路由 props.stage 渲染该阶段已注册组件的列表/卡片视图。
// 数据源与「组件配置中心」一致（/api/profile-composer/catalog + /api/profiles），但只展示一个阶段。

const props = defineProps<{ stage: ComposerStage }>()
const router = useRouter()
const { draft, updateStage, toggleChecker } = useProfileDraft()

const STAGE_META: Record<ComposerStage, { en: string; title: string; detail: string; flow: string }> = {
  source: { en: 'SOURCE', title: '需求来源配置', detail: '决定任务从何处进入受控执行链。', flow: 'Source → Compiler → Maker → Checker → Delivery 的第 1 环' },
  compiler: { en: 'SPEC COMPILER', title: 'Spec 配置', detail: '把需求转换为可验收的 Spec 与 Acceptance。', flow: '第 2 环 · 需求转 Spec' },
  maker: { en: 'MAKER', title: 'Maker 配置', detail: '在 Profile Policy 约束下生成制品。', flow: '第 3 环 · 代码生成' },
  checker: { en: 'CHECKER', title: 'Checker 配置', detail: '承载计算型、反馈型与部分推理型约束判定。', flow: '第 4 环 · 质量闸口' },
  delivery: { en: 'DELIVERY', title: '交付配置', detail: '决定制品的本地保存或受控外部交付。', flow: '第 5 环 · 制品去向' },
}

const catalog = ref<ProfileComposerCatalog | null>(null)
const profiles = ref<Profile[]>([])
const error = ref('')
const loading = ref(true)

const meta = computed(() => STAGE_META[props.stage])
const items = computed(() => catalog.value?.stages[props.stage] || [])
const configFields = (item: ComponentDescriptor) => Object.keys((((item.config_schema || {}) as { properties?: Record<string, unknown> }).properties) || {})
const capabilities = (item: ComponentDescriptor) => Object.entries(item.capabilities).filter(([, allowed]) => allowed).map(([name]) => name).join(' · ') || '离线本地'
const references = (id: string) => profiles.value.filter(profile => props.stage === 'source' ? profile.source === id : props.stage === 'compiler' ? profile.compiler === id : props.stage === 'maker' ? profile.maker === id : props.stage === 'checker' ? profile.checkers?.includes(id) : profile.delivery === id).map(profile => profile.ref || profile.id)
const current = (id: string) => props.stage === 'source' ? draft.source.name === id : props.stage === 'compiler' ? draft.compiler === id : props.stage === 'maker' ? draft.maker === id : props.stage === 'checker' ? draft.checkers.includes(id) : draft.delivery === id
function apply(id: string) { if (props.stage === 'checker') { if (!draft.checkers.includes(id)) toggleChecker(id) } else updateStage(props.stage, id); router.push('/profile-composer/form') }
async function load() { loading.value = true; error.value = ''; try { const [catalogResponse, profileResponse] = await Promise.all([api.profileComposerCatalog(), api.profiles()]); catalog.value = catalogResponse.catalog; profiles.value = profileResponse.profiles.filter(item => item.valid) } catch (e) { error.value = e instanceof Error ? e.message : '无法读取模块目录' } finally { loading.value = false } }
onMounted(load)
</script>

<template>
  <section class="page module-registry">
    <div class="page-heading">
      <div>
        <p class="eyebrow">PLUGGABLE MODULE · {{ meta.en }}</p>
        <h1>{{ meta.title }}</h1>
        <p>{{ meta.detail }} 本模块在 Profile 中可插拔替换，下面是服务端已注册的全部候选组件（列表/卡片视图）。</p>
      </div>
      <RouterLink class="primary-button" to="/pipeline-graph">查看整体运行逻辑</RouterLink>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取模块目录…</p>

    <template v-else-if="catalog">
      <header class="module-meta">
        <div><p>{{ meta.en }}</p><h2>已注册组件</h2><span>{{ meta.flow }}</span></div>
        <small>{{ items.length }} 个候选</small>
      </header>

      <div class="component-grid">
        <article v-for="item in items" :key="item.id" class="workspace-panel component-card">
          <div class="component-head">
            <div>
              <span v-if="item.available === false" class="planned-chip">待接入</span>
              <span v-else :class="current(item.id) ? 'selected-chip' : 'passed'">{{ current(item.id) ? '草稿已选择' : '已注册' }}</span>
              <h3>{{ item.label }}</h3>
            </div>
            <span v-if="item.experimental" class="experiment-chip">实验性</span>
          </div>
          <p>{{ item.description }}</p>
          <dl>
            <div><dt>能力</dt><dd :class="{ risk: capabilities(item) !== '离线本地' }">{{ capabilities(item) }}</dd></div>
            <div><dt>可配置字段</dt><dd>{{ configFields(item).length ? configFields(item).join('、') : '当前无 Profile 级公开字段' }}</dd></div>
            <div><dt>正式 Profile 引用</dt><dd>{{ references(item.id).length ? references(item.id).join('、') : '暂无' }}</dd></div>
          </dl>
          <footer>
            <RouterLink class="quiet-button" :to="`/modules/${props.stage}/${item.id}`">查看详情</RouterLink>
            <button v-if="item.available === false" class="quiet-button" disabled title="待接入：尚未实现适配器">待接入</button>
            <button v-else class="quiet-button" @click="apply(item.id)">{{ props.stage === 'checker' && current(item.id) ? '已在草稿中' : '应用到草稿并配置' }}</button>
          </footer>
        </article>
      </div>

      <section class="workspace-panel registry-boundary">
        <h2>暂未开放的操作</h2>
        <ul>
          <li>从浏览器新增 {{ meta.en }} 类插件。</li>
          <li>在浏览器中填写 API Key、Token、密码、SSH 私钥或其他凭据。</li>
          <li>把组件草稿直接注册为可执行生产组件。</li>
        </ul>
        <p>这些按钮保持置灰，待补齐插件签名、版本化、审计、RBAC 与受控凭据注入后再开放。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.module-meta { display: flex; justify-content: space-between; gap: 15px; align-items: center; margin-bottom: 12px; }
.module-meta h2 { margin: 0; font-size: 15px; }
.module-meta p { margin: 0 0 5px; color: var(--violet); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.module-meta span { color: var(--muted); font-size: 12px; }
.module-meta small { color: var(--soft); font-size: 11px; }
.component-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 11px; }
.component-card { display: flex; flex-direction: column; }
.component-head { display: flex; justify-content: space-between; gap: 10px; }
.component-head h3 { margin: 9px 0 0; font-size: 15px; }
.component-card > p { min-height: 35px; color: var(--muted); font-size: 12px; }
.experiment-chip { height: max-content; padding: 4px 6px; border-radius: 6px; background: color-mix(in srgb, var(--violet) 13%, transparent); color: var(--violet); font-size: 10px; }
.selected-chip { display: inline-block; padding: 4px 6px; border-radius: 6px; background: color-mix(in srgb, var(--blue) 13%, transparent); color: var(--blue); font-size: 10px; font-weight: 800; }
.passed { display: inline-block; padding: 4px 6px; border-radius: 6px; background: color-mix(in srgb, var(--mint) 13%, transparent); color: var(--mint); font-size: 10px; font-weight: 800; }
.planned-chip { display: inline-block; padding: 4px 6px; border-radius: 6px; background: color-mix(in srgb, var(--amber) 13%, transparent); color: var(--amber); font-size: 10px; font-weight: 800; }
.component-card dl { margin: 6px 0; }
.component-card dl div { display: grid; grid-template-columns: 88px 1fr; gap: 8px; padding: 7px 0; border-top: 1px solid var(--line-soft); font-size: 10px; }
.component-card dt { color: var(--soft); }
.component-card dd { margin: 0; color: var(--mint); overflow-wrap: anywhere; }
.component-card dd.risk { color: var(--amber); }
.component-card footer { display: flex; gap: 8px; margin-top: auto; padding-top: 11px; }
.component-card footer .quiet-button { margin: 0; }
.component-card footer button[disabled] { border: 1px solid var(--line); border-radius: 8px; background: transparent; padding: 9px; color: var(--soft); cursor: not-allowed; }
.registry-boundary { margin: 16px 0; }
.registry-boundary h2 { margin: 0; font-size: 13px; }
.registry-boundary ul, .registry-boundary p { color: var(--muted); font-size: 12px; }
.registry-boundary p { margin-bottom: 0; }
@media (max-width: 760px) { .module-meta { align-items: stretch; flex-direction: column; } .component-grid { grid-template-columns: 1fr; } .component-card footer { align-items: stretch; flex-direction: column; } }
</style>
