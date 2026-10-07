<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const paths: Record<string, string> = {
 overview:'M3 3h7v7H3zM14 3h7v4h-7zM14 11h7v10h-7zM3 14h7v7H3z',
 cases:'M3 7h18v13H3zM3 7V4h7l3 3', jobs:'M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1',
 system:'M3 12h4l3-7 4 14 3-7h4', settings:'M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6',
 plus:'M12 5v14M5 12h14', arrow:'M5 12h14M13 6l6 6-6 6', scan:'M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M8 12h8M12 8v8',
 moon:'M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5', menu:'M4 6h16M4 12h16M4 18h16',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.scan" /></svg></template>
