<script setup lang="ts">
const endpoints = [
  ['GET', '/api/compat/overview', '当前：Vue 的脱敏旧 API 兼容投影（只读）'],
  ['GET', '/api/observability/runs', 'Phase 4：版本化 Run 列表投影'],
  ['GET', '/api/observability/runs/:run_id', 'Phase 4：单个 Run、阶段、证据与事件'],
  ['GET', '/api/observability/governance-coverage', 'Phase 4：治理覆盖矩阵'],
]
</script>

<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">DEVELOPER & API</p><h1>API 与开发者</h1><p>前端只读取按合同序列化的数据，不直接扫描 output、日志路径、外部缓存或携带副作用的接口。</p></div><button class="quiet-button" disabled>API 参考待收敛</button></div><section class="developer-intro"><article><span>01</span><h2>先使用只读投影</h2><p>兼容投影在服务端执行字段白名单，避免需求正文、token、策略和原始 trace 进入浏览器。</p></article><article><span>02</span><h2>再接受受控命令</h2><p>任何 trigger、publish、deploy 都必须经由 Profile、dry-run、权限和审计边界。</p></article><article><span>03</span><h2>最后扩展 Adapter</h2><p>Provider 与社区插件需要声明能力、权限、fixture 和证据要求。</p></article></section><section class="api-panel"><div class="panel-heading"><div><h2>接口目录</h2><span>当前可用与规划中的只读合同</span></div><span class="api-version">v1 draft</span></div><div v-for="endpoint in endpoints" :key="endpoint[1]" class="api-row"><code class="get">{{ endpoint[0] }}</code><b>{{ endpoint[1] }}</b><span>{{ endpoint[2] }}</span><button disabled>复制不可用</button></div></section><section class="code-panel"><div><p class="eyebrow">FRONTEND DATA MODEL</p><h2>兼容读取不等于事件事实</h2><p>浏览器只接收审查后的摘要；Phase 4 再以可复算事件与证据替换该临时适配层。</p></div><pre>type RunSummary = {
  run_id: string
  status: 'passed' | 'failed' | 'unavailable' | 'indeterminate' | 'skipped'
  source: 'event-verified' | 'compatibility-read'
}</pre></section></section>
</template>
