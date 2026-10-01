<template>
  <main v-if="!auth.loaded" class="login-page" role="status">正在检查登录状态…</main>
  <RouterView v-else-if="$route.name === 'login'" />
  <AppShell v-else-if="auth.username" :key="sessionEpoch"><RouterView /></AppShell>
  <main v-else class="login-page" role="status">登录状态已改变，正在返回登录页…</main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import AppShell from './layout/AppShell.vue'
import { auth, startSessionSync } from './auth/session'
import { sessionEpoch } from './auth/lifecycle'

const router = useRouter()
onBeforeUnmount(startSessionSync())
watch([() => auth.username, () => auth.loaded], ([username, loaded]) => {
  if (!loaded) return
  const route = router.currentRoute.value
  if (!username && route.name !== 'login') void router.replace({ name: 'login', query: { next: route.fullPath } })
  else if (username && route.name === 'login') {
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//')
      && !route.query.next.startsWith('/login') ? route.query.next : '/'
    void router.replace(next)
  }
})
</script>
