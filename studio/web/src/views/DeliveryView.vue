<template>
  <section class="page"><div class="page-heading"><div><p class="eyebrow">APPLICATIONS · DELIVERY · DEPLOYMENT</p><h1>应用与交付</h1><p>旧 Flask 尚未提供经过审查的应用与 Delivery 结果投影，因此本页不从 <code>output/</code>、缓存或历史日志制造应用状态。</p></div><button class="primary-button" disabled>创建 Delivery 计划不可用</button></div>
    <section class="delivery-summary"><article><span>应用清单</span><b>—</b><small>未接入安全的 /api/apps 投影</small></article><article><span>交付计划</span><b>—</b><small>兼容模式不调用 POST</small></article><article><span>生产权限</span><b>关闭</b><small>默认页面不具备副作用能力</small></article></section>
    <section class="workspace-panel"><div class="panel-heading"><div><h2>Delivery 运营面等待受控合同</h2><span>未接入，不等于已通过或没有应用</span></div></div><div class="compatibility-note"><b>本页需要的最小数据</b><p>版本化 Run、不可变 artifact digest、Delivery 目标、审批记录、健康检查、回滚目标和明确的结果状态。它们必须与同一 run_id 绑定。</p><p>在这些字段有专门只读 API 之前，页面只显示边界说明，不展示 Mock 应用、部署渠道或“可交付”计数。</p></div></section>
  </section>
</template>
