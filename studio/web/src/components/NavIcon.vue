<script setup lang="ts">
defineProps<{ name: string }>()
</script>

<template>
  <svg v-if="name === 'home'" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="8" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="15" width="7" height="6" rx="1.5"/></svg>
  <svg v-else-if="name === 'file'" viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>
  <svg v-else-if="name === 'runs'" viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.6"/><path d="M4 4v5h5M10 8l5 4-5 4z"/></svg>
  <svg v-else-if="name === 'shield'" viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.6-3 8-7 10-4-2-7-5.4-7-10V6z"/><path d="m9 12 2 2 4-4"/></svg>
  <svg v-else-if="name === 'apps'" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
  <svg v-else-if="name === 'chart'" viewBox="0 0 24 24"><path d="M4 18V5M4 18h16"/><path d="m7 14 4-4 3 2 5-6"/></svg>
  <svg v-else-if="name === 'settings'" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="m19 12 2-1-2-4-2 1a7 7 0 0 0-2-1l-.3-2H10l-.3 2a7 7 0 0 0-2 1L5.5 7 3.5 11l2 1a7 7 0 0 0 0 2l-2 1 2 4 2.2-1a7 7 0 0 0 2 1l.3 2h4.6l.3-2a7 7 0 0 0 2-1l2.2 1 2-4z"/></svg>
  <svg v-else-if="name === 'plans'" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/></svg>
  <svg v-else-if="name === 'flow'" viewBox="0 0 24 24"><rect x="2.5" y="9" width="5" height="6" rx="1.2"/><rect x="16.5" y="9" width="5" height="6" rx="1.2"/><rect x="9.5" y="3.5" width="5" height="5" rx="1.2"/><rect x="9.5" y="15.5" width="5" height="5" rx="1.2"/><path d="M7.5 12h2M14.5 12h2M12 8.5v7"/></svg>
  <svg v-else viewBox="0 0 24 24"><path d="M5 4h14v16H5z"/><path d="m8 9 3 3-3 3M13 15h3"/></svg>
</template>

<style scoped>
svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
</style>
