<script setup lang="ts">
defineProps<{ collapsed: boolean }>()
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M9 4v16" />
    <path v-if="collapsed" d="m13 9 3 3-3 3" />
    <path v-else d="m16 9-3 3 3 3" />
  </svg>
</template>

<style scoped>
svg{width:16px;height:16px}
</style>
