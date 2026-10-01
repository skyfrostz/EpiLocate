<template>
  <main v-if="!auth.loaded" class="login-page" role="status">正在检查登录状态…</main>
  <RouterView v-else-if="$route.name === 'login'" />
  <AppShell v-else-if="auth.username" :key="sessionEpoch"><RouterView /></AppShell>
  <main v-else class="login-page" role="status">登录状态已改变，正在返回登录页…</main>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import AppShell from './layout/AppShell.vue'
import { auth } from './auth/session'
import { sessionEpoch } from './auth/lifecycle'

const router = useRouter()
watch(() => auth.username, (username, previous) => {
  if (previous && !username) void router.replace({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
})
</script>
