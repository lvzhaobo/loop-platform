<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DashboardOutlined, ApartmentOutlined, AppstoreOutlined, FileTextOutlined, PlayCircleOutlined, SafetyOutlined, ClusterOutlined } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

// Ant Design Pro 经典侧边栏：分组 + 项
const menuItems = [
  { type: 'group', label: '总览', children: [
    { key: '/', label: 'Dashboard', icon: () => h(DashboardOutlined) },
    { key: '/panorama', label: '架构与运行逻辑', icon: () => h(ApartmentOutlined) },
  ]},
  { type: 'group', label: '运行环境', children: [
    { key: '/knowledge', label: '知识工程', icon: () => h(ClusterOutlined) },
    { key: '/landing-zone', label: 'Landing Zone', icon: () => h(SafetyOutlined) },
    { key: '/checks', label: 'Harness 约束', icon: () => h(SafetyOutlined) },
  ]},
  { type: 'group', label: '可插拔模块', children: [
    { key: '/spec-flow', label: 'Spec 编译', icon: () => h(AppstoreOutlined) },
  ]},
  { type: 'group', label: '需求', children: [
    { key: '/requirements', label: '需求管理', icon: () => h(FileTextOutlined) },
  ]},
  { type: 'group', label: '执行与交付', children: [
    { key: '/plans', label: '受控执行', icon: () => h(PlayCircleOutlined) },
    { key: '/runs', label: '交付运行', icon: () => h(PlayCircleOutlined) },
    { key: '/trace', label: '日志与 Trace', icon: () => h(FileTextOutlined) },
  ]},
]

const selectedKeys = computed(() => [route.path])
const title = computed(() => (route.meta.title as string) || '任务中心')

function onMenuClick({ key }: { key: string }) {
  if (key.startsWith('/')) router.push(key)
}
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider v-model:collapsed="collapsed" collapsible theme="dark" :width="236">
      <div style="height: 56px; display: flex; align-items: center; gap: 8px; padding: 0 16px; color: #fff; overflow: hidden;">
        <span style="display: grid; place-items: center; width: 26px; height: 26px; border-radius: 6px; background: #1677ff; font-size: 14px; flex-shrink: 0;">↻</span>
        <div v-if="!collapsed" style="line-height: 1.15;">
          <div style="font-size: 14px; font-weight: 600;">Loop</div>
          <div style="font-size: 10px; color: rgba(255,255,255,.45); letter-spacing: .06em;">AI DELIVERY</div>
        </div>
      </div>
      <a-menu theme="dark" mode="inline" :items="menuItems" :selected-keys="selectedKeys" @click="onMenuClick" />
    </a-layout-sider>

    <a-layout>
      <a-layout-header style="background: #fff; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f0f0f0; height: 56px;">
        <span style="color: #888; font-size: 13px;">WORKSPACE / <b style="color: #222;">{{ title }}</b></span>
        <a-space>
          <a-badge status="processing" text="运行正常" />
          <a-button shape="circle" @click="() => {}">◐</a-button>
        </a-space>
      </a-layout-header>
      <a-layout-content style="padding: 20px 24px;">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
