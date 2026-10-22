<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import NavIcon from './components/NavIcon.vue'
import SidebarToggleIcon from './components/SidebarToggleIcon.vue'
import { currentDataSource } from './data/repository'

const route = useRoute()
// 主题态挂在 <html> 而不是 .app-shell：body 背景能跟随主题，深色时窗口四周不会露出浏览器默认白边。
// 初值从 index.html 内联脚本预置的 class 读，避免两处状态源不一致导致首帧闪烁。
const dark = ref(document.documentElement.classList.contains('dark'))
const collapsed = ref(false)
watchEffect(() => {
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('loop-theme', dark.value ? 'dark' : 'light')
})
const sourceOpen = ref(false)
const groups = [
  { label: '正式 Studio', items: [['/', 'home', '交付概览'], ['/panorama', 'flow', '交付全景图'], ['/pipeline-graph', 'flow', '流水线拓扑'], ['/intake', 'file', '新建需求'], ['/requirements', 'file', '需求列表'], ['/plans', 'plans', '受控执行'], ['/profiles', 'plans', 'Profile 库'], ['/profile-components', 'settings', '组件配置中心'], ['/profile-composer/form', 'plans', 'Profile 编排'], ['/profile-composer/canvas', 'chart', 'Profile 画布'], ['/runs', 'runs', '交付运行'], ['/governance', 'shield', '治理覆盖']] },
  { label: '保留的预览页面', items: [['/preview', 'file', '预览：任务中心'], ['/preview/runs', 'runs', '预览：运行历史'], ['/preview/governance', 'chart', '预览：质量面板']] },
]
const title = computed(() => route.meta.title ?? '任务中心')
</script>

<template>
  <div class="app-shell" :class="{ collapsed }">
    <aside class="nav-panel"><header class="sidebar-header"><div class="sidebar-brand"><span class="brand-symbol">↻</span><div class="brand-copy"><b>Loop</b><small>AI DELIVERY</small></div></div><button class="collapse-button" @click="collapsed = !collapsed" :title="collapsed ? '展开菜单' : '收起菜单'"><SidebarToggleIcon :collapsed="collapsed" /></button></header><nav class="sidebar-nav"><section v-for="group in groups" :key="group.label" class="nav-group"><p class="nav-label">{{ group.label }}</p><RouterLink v-for="item in group.items" :key="item[0]" :to="item[0]" class="nav-link" :title="item[2]"><span class="nav-icon"><NavIcon :name="item[1]" /></span><span class="nav-copy">{{ item[2] }}</span></RouterLink></section></nav><footer class="sidebar-footer"><button class="theme-switch" @click="dark = !dark" :title="dark ? '切换浅色' : '切换深色'"><span>{{ dark ? '☼' : '◐' }}</span><b>{{ dark ? '浅色主题' : '深色主题' }}</b></button><div class="sidebar-user"><span>LV</span><div><b>lvzhaobo</b><small>平台管理员</small></div></div></footer></aside>
    <main class="content"><header class="topbar"><span>WORKSPACE / <b>{{ title }}</b></span><div class="top-actions"><div class="source-wrap"><button class="source source-button" @click="sourceOpen = !sourceOpen"><i></i>{{ currentDataSource.label }}</button><div v-if="sourceOpen" class="source-popover"><b>{{ currentDataSource.label }}</b><p>{{ currentDataSource.detail }}</p><small>刷新时间：{{ currentDataSource.refreshedAt }}</small></div></div><button class="theme-button" @click="dark = !dark">{{ dark ? '浅色' : '深色' }}</button></div></header><RouterView /></main>
  </div>
</template>
