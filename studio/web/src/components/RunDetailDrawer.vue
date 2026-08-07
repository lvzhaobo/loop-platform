<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { statusMeta, type Run } from '../data/mock'

const props = defineProps<{ open: boolean; run: Run | null; sourceKind: string }>()
const emit = defineEmits<{ close: [] }>()
const activeTab = ref('overview')
const tabs = [['overview', '概览'], ['lifecycle', '生命周期'], ['checks', '检查'], ['evidence', '证据'], ['events', '原始事件'], ['artifacts', '产物']]
const status = computed(() => props.run ? statusMeta[props.run.status] : null)
const stages = computed(() => [
  ['需求绑定', '已关联到任务来源'],
  ['Spec 编译', '当前来源未提供阶段事件'],
  ['Maker 生成', '当前来源未提供阶段事件'],
  ['确定性检查', props.run?.stage || '尚未接入'],
  ['Delivery 计划', '当前来源未提供阶段事件'],
])
const closeOnEscape = (event: KeyboardEvent) => { if (props.open && event.key === 'Escape') emit('close') }
watch(() => props.run?.id, () => { activeTab.value = 'overview' })
onMounted(() => window.addEventListener('keydown', closeOnEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', closeOnEscape))
</script>

<template>
  <div v-if="open" class="drawer-mask" @click.self="emit('close')">
    <aside class="run-drawer" role="dialog" aria-modal="true" aria-label="Run 详情">
      <header class="drawer-header">
        <div>
          <p class="eyebrow">{{ run?.id }}</p>
          <h2>{{ run?.title }}</h2>
          <span v-if="status && run" :class="['status', run.status]">{{ status.label }}</span>
        </div>
        <button class="drawer-close" type="button" aria-label="关闭详情" @click="emit('close')">×</button>
      </header>
      <nav class="drawer-tabs" aria-label="Run detail sections">
        <button v-for="tab in tabs" :key="tab[0]" type="button" :class="{ active: activeTab === tab[0] }" @click="activeTab = tab[0]">{{ tab[1] }}</button>
      </nav>
      <main class="drawer-body">
        <section v-if="activeTab === 'overview'" class="drawer-overview">
          <div class="drawer-kpis"><article><span>Profile</span><b>{{ run?.profile || '—' }}</b></article><article><span>耗时</span><b>{{ run?.elapsed || '—' }}</b></article><article><span>数据来源</span><b>{{ sourceKind }}</b></article></div>
          <h3>当前结论</h3>
          <p>{{ run?.stage || '暂无阶段结论' }}。当前页面只展示 repository 提供的保守投影，不会从目录、产物或“最近日志”推断状态。</p>
          <div class="drawer-action"><span>下一步</span><b>{{ run?.status === 'failed' ? '待任务级 CheckReport 接入后分析失败原因' : run?.status === 'indeterminate' ? '待核对 evidence 的 digest、scope 与 Run 绑定' : '待接入任务级事件与证据投影' }}</b></div>
        </section>
        <section v-else-if="activeTab === 'lifecycle'" class="drawer-timeline">
          <article v-for="(stage, index) in stages" :key="stage[0]" :class="{ current: stage[0] === run?.stage }"><i>{{ index + 1 }}</i><div><b>{{ stage[0] }}</b><span>{{ stage[1] }}</span></div></article>
        </section>
        <section v-else-if="activeTab === 'checks'" class="drawer-empty"><span>⊘</span><h3>检查明细尚未绑定到此 Run</h3><p>兼容 trace 不含 task-bound CheckReport；不会把全局 Checker 清单或最近报告拼接为当前 Run 的检查结论。</p></section>
        <section v-else-if="activeTab === 'evidence'" class="drawer-evidence"><div><span>来源</span><b>{{ sourceKind }}</b></div><div><span>Run ID</span><b>{{ run?.id }}</b></div><div><span>当前证据状态</span><b>{{ run?.evidence || '未接入' }}</b></div><div><span>digest / scope</span><b>当前投影未提供</b></div><p>正式事件接口接入后，缺失证据应为 unavailable；跨 Run、scope 或 digest 不匹配应为 indeterminate。</p></section>
        <section v-else-if="activeTab === 'events'" class="drawer-empty"><span>⌁</span><h3>暂无可展示的原始事件序列</h3><p>当前兼容层只映射明确的 <code>case_done + pass/fail</code> 摘要，不暴露未审查的历史 trace 字段。接入 verified-event-projection 后，此处将按 sequence 展示脱敏事件元数据。</p></section>
        <section v-else class="drawer-empty"><span>□</span><h3>产物尚未任务级绑定</h3><p>当前不会根据 output 目录、文件名或“最新产物”猜测当前 Run 的制品。待不可变 artifact 与 evidence bundle 关联后再展示。</p></section>
      </main>
      <footer class="drawer-footer"><span>按 <kbd>Esc</kbd> 关闭</span><span>{{ sourceKind }}</span></footer>
    </aside>
  </div>
</template>

<style scoped>
.drawer-mask{position:fixed;inset:0;z-index:50;display:flex;justify-content:flex-end;background:rgba(10,14,24,.28);backdrop-filter:blur(2px)}
.run-drawer{display:flex;flex-direction:column;width:min(680px,100vw);height:100%;border-left:1px solid var(--line);background:var(--panel);box-shadow:-22px 0 60px rgba(19,27,49,.16);animation:slide-in .2s ease-out}
.drawer-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:26px 27px 18px;border-bottom:1px solid var(--line-soft)}
.drawer-header h2{max-width:540px;margin:4px 0 11px;font-size:23px;line-height:1.25;letter-spacing:-.035em}.drawer-close{display:grid;flex:0 0 auto;place-items:center;width:31px;height:31px;border:1px solid var(--line);border-radius:9px;background:transparent;color:var(--muted);font-size:22px;line-height:1;cursor:pointer}.drawer-close:hover{border-color:var(--blue);color:var(--blue)}
.drawer-tabs{display:flex;gap:3px;overflow-x:auto;padding:0 20px;border-bottom:1px solid var(--line-soft)}.drawer-tabs button{flex:0 0 auto;border:0;border-bottom:2px solid transparent;background:transparent;padding:13px 8px 11px;color:var(--muted);font-size:12px;font-weight:700;cursor:pointer}.drawer-tabs button:hover{color:var(--ink)}.drawer-tabs button.active{border-bottom-color:var(--blue);color:var(--blue)}
.drawer-body{flex:1;overflow:auto;padding:24px 27px}.drawer-body h3{margin:21px 0 7px;font-size:13px}.drawer-body p{margin:0;color:var(--muted);font-size:12px;line-height:1.75}.drawer-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.drawer-kpis article{min-height:76px;padding:12px;border:1px solid var(--line-soft);border-radius:10px;background:var(--panel-2)}.drawer-kpis span,.drawer-kpis b{display:block}.drawer-kpis span{color:var(--soft);font-size:10px}.drawer-kpis b{margin-top:7px;overflow-wrap:anywhere;font-size:12px}.drawer-action{display:grid;gap:5px;margin-top:18px;padding:14px;border:1px solid color-mix(in srgb,var(--blue) 25%,var(--line));border-radius:10px;background:color-mix(in srgb,var(--blue) 6%,var(--panel))}.drawer-action span{color:var(--blue);font-size:10px;font-weight:800}.drawer-action b{font-size:12px}
.drawer-timeline{display:grid;gap:0;margin:4px 0}.drawer-timeline article{position:relative;display:flex;gap:12px;padding:0 0 24px 4px}.drawer-timeline article:not(:last-child)::after{content:'';position:absolute;top:27px;bottom:4px;left:15px;width:1px;background:var(--line)}.drawer-timeline i{position:relative;z-index:1;display:grid;place-items:center;flex:0 0 23px;width:23px;height:23px;border:1px solid var(--line);border-radius:50%;background:var(--panel);color:var(--soft);font-style:normal;font-size:10px}.drawer-timeline b,.drawer-timeline span{display:block;font-size:12px}.drawer-timeline span{margin-top:3px;color:var(--soft);font-size:11px}.drawer-timeline .current i{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 14%,var(--panel));color:var(--blue);box-shadow:0 0 0 4px color-mix(in srgb,var(--blue) 10%,transparent)}
.drawer-evidence{display:grid;gap:0;border:1px solid var(--line-soft);border-radius:11px;overflow:hidden}.drawer-evidence>div{display:grid;grid-template-columns:130px 1fr;gap:12px;padding:12px 14px;border-bottom:1px solid var(--line-soft);font-size:12px}.drawer-evidence>div:last-of-type{border-bottom:0}.drawer-evidence span{color:var(--soft)}.drawer-evidence b{overflow-wrap:anywhere}.drawer-evidence p{padding:14px;background:var(--panel-2)}
.drawer-empty{display:grid;justify-items:start;padding:29px 7px}.drawer-empty>span{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:color-mix(in srgb,var(--violet) 12%,transparent);color:var(--violet);font-size:18px}.drawer-empty h3{margin-top:15px}.drawer-empty code{padding:1px 4px;border-radius:4px;background:var(--panel-2);font-size:10px}.drawer-footer{display:flex;justify-content:space-between;gap:12px;padding:12px 27px;border-top:1px solid var(--line-soft);color:var(--soft);font-size:10px}.drawer-footer kbd{padding:1px 4px;border:1px solid var(--line);border-radius:4px;background:var(--panel-2);font:inherit}
@keyframes slide-in{from{transform:translateX(16px);opacity:.45}to{transform:translateX(0);opacity:1}}@media(max-width:620px){.drawer-header,.drawer-body{padding-inline:18px}.drawer-kpis{grid-template-columns:1fr}.drawer-evidence>div{grid-template-columns:1fr;gap:4px}.drawer-footer{padding-inline:18px}}
</style>
