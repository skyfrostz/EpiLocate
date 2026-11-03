<script setup lang="ts">
import type { StatusLabel } from '../domain/clinical'
defineProps<StatusLabel>()
</script>
<template><span class="ep-status" :data-tone="tone">{{ label }}</span></template>
