<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ChecksResponse } from '../api/contracts'

// Landing Zone：把 Harness 约束装配成一套可复用的 AI 运行环境底座。
// 底座可替换：当前 Loop Platform（自研沙箱），未来可切 dsh 底座。

const checks = ref<ChecksResponse | null>(null)
const error = ref('')
const loading = ref(true)
const base = ref<'loop' | 'dsh'>('loop')

const QUADRANTS = [
  { key: 'inject-rule', feed: '前馈', type: '计算型', note: '生成前注入规则，机械确定' },
  { key: 'inject-infer', feed: '前馈', type: '推理型', note: '生成前注入意图，需模型推断' },
  { key: 'check-rule', feed: '反馈', type: '计算型', note: '生成后逐条检查，客观可复现' },
  { key: 'check-infer', feed: '反馈', type: '推理型', note: '生成后 LLM-as-Judge，主观判断' },
]

const quadStats = computed(() => QUADRANTS.map(q => ({
  ...q,
  count: (checks.value?.summary?.by_quadrant || {})[q.key] || 0,
})))
const total = computed(() => checks.value?.summary?.total || 0)

onMounted(async () => {
  loading.value = true; error.value = ''
  try { checks.value = await api.checks() }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取约束清单' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page landing-zone">
    <div class="page-heading">
      <div>
        <p class="eyebrow">LANDING ZONE</p>
        <h1>Landing Zone 装配</h1>
        <p>把 Harness 约束（前馈 + 反馈）装配成一套可复用的 AI 运行环境底座，可落地在 Loop Platform 沙箱或 dsh 底座。</p>
      </div>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>

    <!-- 装配底座 -->
    <section class="lz-panel">
      <h2>装配目标底座</h2>
      <p class="lz-sub">同一套约束，可装配到不同底座上；底座可替换，约束语义不变。</p>
      <div class="base-grid">
        <button class="base-card" :class="{ on: base === 'loop' }" @click="base = 'loop'">
          <div class="base-head"><b>Loop Platform</b><span class="chip chip-on">当前 · 自研沙箱</span></div>
          <p>项目开发沙箱：契约驱动生成 + 硬验收 + 证据留痕。</p>
          <small>生成、验收、交付在沙箱内受控执行</small>
        </button>
        <button class="base-card" :class="{ on: base === 'dsh' }" @click="base = 'dsh'">
          <div class="base-head"><b>DSH 底座</b><span class="chip chip-later">可替换 · 待接入</span></div>
          <p>DeepSeek Harness：capability seam 可拆卸装配。</p>
          <small>后续接入，作为 Loop 底座的可替换实现</small>
        </button>
      </div>
    </section>

    <!-- 约束四象限装配 -->
    <section class="lz-panel">
      <h2>约束装配 · 四象限</h2>
      <p class="lz-sub">前馈约束在生成前注入，反馈约束在生成后判定；计算型确定性执行，推理型由模型判断。</p>
      <p v-if="loading" class="empty-state">正在读取约束清单…</p>
      <div v-else class="quad-grid">
        <div v-for="q in quadStats" :key="q.key" class="quad-card">
          <span class="quad-feed" :class="q.feed === '前馈' ? 'feed' : 'back'">{{ q.feed }}</span>
          <b>{{ q.count }}</b>
          <span class="quad-type">{{ q.type }}</span>
          <p>{{ q.note }}</p>
        </div>
      </div>
      <div class="lz-total">共 <b>{{ total }}</b> 项约束已装配</div>
    </section>

    <!-- 装配流程 -->
    <section class="lz-panel">
      <h2>装配流程</h2>
      <div class="lz-flow">
        <div class="lz-step"><span class="step-no">1</span><b>定义约束</b><small>Harness 约束 + 知识工程</small></div>
        <span class="step-arrow">→</span>
        <div class="lz-step"><span class="step-no">2</span><b>选择底座</b><small>Loop Platform / dsh</small></div>
        <span class="step-arrow">→</span>
        <div class="lz-step"><span class="step-no">3</span><b>装配 Landing Zone</b><small>生成可复用的运行环境</small></div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.lz-panel { margin-top: 16px; padding: 20px 22px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.lz-panel h2 { margin: 0; font-size: 15px; }
.lz-sub { margin: 4px 0 14px; color: var(--soft); font-size: 12px; }
.base-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.base-card { text-align: left; padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel-2); cursor: pointer; }
.base-card:hover { border-color: var(--brand); }
.base-card.on { border-color: var(--brand); box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 18%, transparent); }
.base-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.base-head b { font-size: 14px; }
.base-card p { margin: 8px 0 0; color: var(--muted); font-size: 12px; }
.base-card small { display: block; margin-top: 6px; color: var(--soft); font-size: 11px; }
.chip { padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 600; }
.chip-on { background: color-mix(in srgb, var(--mint) 13%, transparent); color: var(--mint); }
.chip-later { background: color-mix(in srgb, var(--amber) 13%, transparent); color: var(--amber); }
.quad-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 11px; }
.quad-card { padding: 15px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); }
.quad-feed { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 10px; font-weight: 700; }
.quad-feed.feed { background: color-mix(in srgb, var(--blue) 13%, transparent); color: var(--blue); }
.quad-feed.back { background: color-mix(in srgb, var(--violet) 13%, transparent); color: var(--violet); }
.quad-card b { display: block; margin: 9px 0 2px; font-size: 26px; letter-spacing: -.03em; }
.quad-type { color: var(--ink); font-size: 12px; font-weight: 600; }
.quad-card p { margin: 6px 0 0; color: var(--soft); font-size: 11px; }
.lz-total { margin-top: 12px; color: var(--soft); font-size: 12px; }
.lz-total b { color: var(--ink); }
.lz-flow { display: flex; align-items: center; gap: 14px; }
.lz-step { flex: 1; padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); text-align: center; }
.step-no { display: grid; place-items: center; width: 24px; height: 24px; margin: 0 auto 8px; border-radius: 50%; background: var(--brand); color: #fff; font-size: 12px; font-weight: 700; }
.lz-step b { display: block; font-size: 13px; }
.lz-step small { display: block; margin-top: 3px; color: var(--soft); font-size: 11px; }
.step-arrow { color: var(--soft); font-size: 18px; }
@media (max-width: 760px) { .base-grid, .quad-grid { grid-template-columns: 1fr; } .lz-flow { flex-direction: column; } .step-arrow { transform: rotate(90deg); } }
</style>
