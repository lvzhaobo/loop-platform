<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ComponentDescriptor, ComposerStage, Profile, ProfileComposerCatalog } from '../api/contracts'
import { useProfileDraft } from '../composables/useProfileDraft'

// 单个可插拔组件的详情页：显示完整配置信息（能力、可配置字段、Schema、Profile 引用），
// 数据源与模块列表一致（/api/profile-composer/catalog + /api/profiles）。

const props = defineProps<{ stage: ComposerStage; componentId: string }>()
const router = useRouter()
const { draft, updateStage, toggleChecker } = useProfileDraft()

const STAGE_META: Record<ComposerStage, { en: string; title: string }> = {
  source: { en: 'SOURCE', title: '需求来源' },
  compiler: { en: 'SPEC COMPILER', title: 'Spec 配置' },
  maker: { en: 'MAKER', title: 'Maker 配置' },
  checker: { en: 'CHECKER', title: 'Checker 配置' },
  delivery: { en: 'DELIVERY', title: '交付配置' },
}
const CAP_LABEL: Record<string, string> = {
  network: '网络访问', model: '调用模型', git: 'Git 操作', publish: '发布', deploy: '部署', ssh: 'SSH',
}

const catalog = ref<ProfileComposerCatalog | null>(null)
const profiles = ref<Profile[]>([])
const error = ref('')
const loading = ref(true)

const meta = computed(() => STAGE_META[props.stage])
const item = computed<ComponentDescriptor | null>(() => catalog.value?.stages[props.stage]?.find(c => c.id === props.componentId) || null)

const configProps = computed(() => {
  const schema = item.value?.config_schema as { properties?: Record<string, { type?: string; description?: string; default?: unknown }> } | undefined
  return Object.entries(schema?.properties || {}).map(([name, def]) => ({
    name, type: def.type || '—', description: def.description || '', default: def.default,
  }))
})
const capabilities = computed(() => Object.entries(item.value?.capabilities || {}).map(([name, allowed]) => ({ name, label: CAP_LABEL[name] || name, allowed })))
const references = computed(() => profiles.value.filter(p => {
  if (props.stage === 'source') return p.source === props.componentId
  if (props.stage === 'compiler') return p.compiler === props.componentId
  if (props.stage === 'maker') return p.maker === props.componentId
  if (props.stage === 'checker') return p.checkers?.includes(props.componentId)
  return p.delivery === props.componentId
}).map(p => p.ref || p.id))
const isCurrent = computed(() => props.stage === 'source' ? draft.source.name === props.componentId : props.stage === 'compiler' ? draft.compiler === props.componentId : props.stage === 'maker' ? draft.maker === props.componentId : props.stage === 'checker' ? draft.checkers.includes(props.componentId) : draft.delivery === props.componentId)

function apply() {
  if (!item.value) return
  if (props.stage === 'checker') { if (!draft.checkers.includes(props.componentId)) toggleChecker(props.componentId) }
  else updateStage(props.stage, props.componentId)
  router.push('/profile-composer/form')
}

onMounted(async () => {
  loading.value = true; error.value = ''
  try { const [c, p] = await Promise.all([api.profileComposerCatalog(), api.profiles()]); catalog.value = c.catalog; profiles.value = p.profiles.filter(x => x.valid) }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取模块详情' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page module-detail">
    <nav class="crumb">
      <RouterLink to="/modules/source">可插拔模块</RouterLink>
      <span>/</span>
      <RouterLink :to="`/modules/${props.stage}`">{{ meta.title }}</RouterLink>
      <span>/</span>
      <b>{{ item?.label || props.componentId }}</b>
    </nav>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取组件详情…</p>
    <p v-else-if="!item" class="empty-state">未找到组件「{{ props.componentId }}」。</p>

    <template v-else-if="item">
      <!-- 头部 -->
      <div class="detail-head">
        <div>
          <p class="eyebrow">{{ meta.en }} · {{ item.id }}</p>
          <h1>{{ item.label }}</h1>
          <p class="detail-desc">{{ item.description }}</p>
          <div class="detail-chips">
            <span v-if="item.available === false" class="chip chip-planned">待接入</span>
            <span v-else-if="isCurrent" class="chip chip-current">草稿已选择</span>
            <span v-else class="chip chip-registered">已注册</span>
            <span v-if="item.experimental" class="chip chip-exp">实验性</span>
          </div>
        </div>
        <div class="detail-actions">
          <button v-if="item.available === false" class="primary-button" disabled title="待接入：尚未实现适配器">待接入</button>
          <button v-else class="primary-button" @click="apply">{{ isCurrent ? '已在草稿中' : '应用到草稿并配置' }}</button>
          <RouterLink class="ghost-button" :to="`/modules/${props.stage}`">返回列表</RouterLink>
        </div>
      </div>

      <!-- 能力 -->
      <section class="detail-panel">
        <h2>能力与权限</h2>
        <p class="panel-sub">该组件在受控执行中能触碰哪些外部边界；未开放的能力不会暴露给浏览器。</p>
        <div class="cap-grid">
          <div v-for="cap in capabilities" :key="cap.name" class="cap" :class="{ on: cap.allowed }">
            <i>{{ cap.allowed ? '✓' : '—' }}</i>
            <span>{{ cap.label }}</span>
            <small>{{ cap.name }}</small>
          </div>
        </div>
      </section>

      <!-- 配置字段 -->
      <section class="detail-panel">
        <h2>配置字段</h2>
        <p class="panel-sub">Profile 级可公开配置的字段（凭据、插件代码与全局运行时配置不在此列）。</p>
        <p v-if="!configProps.length" class="empty-inline">当前无 Profile 级公开字段。</p>
        <div v-else class="field-list">
          <div v-for="f in configProps" :key="f.name" class="field">
            <b>{{ f.name }}</b>
            <span class="field-type">{{ f.type }}</span>
            <p>{{ f.description || '无说明' }}<template v-if="f.default !== undefined"><small> · 默认 {{ String(f.default) }}</small></template></p>
          </div>
        </div>
      </section>

      <!-- Profile 引用 -->
      <section class="detail-panel">
        <h2>正式 Profile 引用</h2>
        <p class="panel-sub">哪些已保存 Profile 选用了本组件。</p>
        <p v-if="!references.length" class="empty-inline">暂无 Profile 引用。</p>
        <div v-else class="ref-chips">
          <RouterLink v-for="ref in references" :key="ref" :to="`/profiles`" class="chip chip-ref">{{ ref }}</RouterLink>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.crumb { display: flex; align-items: center; gap: 8px; margin: 6px 0 18px; color: var(--soft); font-size: 12px; }
.crumb a { color: var(--muted); }
.crumb a:hover { color: var(--blue); }
.crumb b { color: var(--ink); font-weight: 600; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
.detail-head h1 { margin: 0; font-size: 26px; letter-spacing: -.03em; }
.detail-desc { margin: 8px 0 0; max-width: 620px; color: var(--muted); font-size: 13px; }
.detail-chips { display: flex; gap: 8px; margin-top: 12px; }
.chip { display: inline-block; padding: 4px 9px; border-radius: 6px; font-size: 11px; font-weight: 600; }
.chip-current { background: color-mix(in srgb, var(--blue) 13%, transparent); color: var(--blue); }
.chip-registered { background: color-mix(in srgb, var(--mint) 13%, transparent); color: var(--mint); }
.chip-exp { background: color-mix(in srgb, var(--violet) 13%, transparent); color: var(--violet); }
.chip-planned { background: color-mix(in srgb, var(--amber) 13%, transparent); color: var(--amber); }
.chip-ref { background: var(--panel-2); color: var(--muted); border: 1px solid var(--line); }
.detail-actions { display: flex; gap: 10px; flex-shrink: 0; }
.ghost-button { display: inline-flex; align-items: center; padding: 10px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); font-size: 13px; font-weight: 600; }
.ghost-button:hover { border-color: var(--brand); color: var(--brand); }
.detail-panel { margin-top: 14px; padding: 18px 20px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.detail-panel h2 { margin: 0; font-size: 14px; }
.panel-sub { margin: 4px 0 0; color: var(--soft); font-size: 11px; }
.cap-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-top: 14px; }
.cap { display: flex; flex-direction: column; gap: 2px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel-2); }
.cap i { font-style: normal; font-size: 13px; color: var(--soft); }
.cap.on i { color: var(--mint); }
.cap span { font-size: 12px; font-weight: 600; }
.cap small { color: var(--soft); font-size: 10px; }
.field-list { margin-top: 12px; border-top: 1px solid var(--line-soft); }
.field { padding: 12px 2px; border-bottom: 1px solid var(--line-soft); }
.field b { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
.field-type { display: inline-block; margin-left: 10px; padding: 1px 6px; border-radius: 4px; background: var(--panel-2); color: var(--soft); font: 10px ui-monospace, Menlo, monospace; }
.field p { margin: 5px 0 0; color: var(--muted); font-size: 12px; }
.field p small { color: var(--soft); }
.ref-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.empty-inline { margin: 12px 0 0; color: var(--soft); font-size: 12px; }
@media (max-width: 900px) { .cap-grid { grid-template-columns: repeat(3, 1fr); } .detail-head { flex-direction: column; } }
@media (max-width: 560px) { .cap-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
