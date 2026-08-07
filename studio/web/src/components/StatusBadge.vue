<script setup lang="ts">
import type { CheckStatus, Integrity } from '../api/contracts'
defineProps<{ status: CheckStatus | Integrity }>()
const labels: Record<string, string> = { passed: '已通过', failed: '失败', unavailable: '不可用', indeterminate: '不确定', skipped: '已跳过', verified: '证据已验证' }
</script>
<template><span :class="['status', status]">{{ labels[status] || status }}</span></template>
