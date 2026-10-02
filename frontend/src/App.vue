<template>
  <main v-if="!auth.loaded" class="login-page" role="status">正在检查登录状态…</main>
  <!-- Conceal unknown identity immediately without collapsing retained imaging layout. -->
  <div v-if="auth.loaded" class="session-workspace"
    :style="{ opacity: auth.verifying ? 0 : undefined, pointerEvents: auth.verifying ? 'none' : undefined }"
    :inert="auth.verifying ? true : undefined" :aria-hidden="auth.verifying ? true : undefined">
    <RouterView v-if="$route.name === 'login'" />
    <AppShell v-else-if="auth.username" :key="sessionEpoch"><RouterView /></AppShell>
    <main v-else class="login-page" role="status">登录状态已改变，正在返回登录页…</main>
  </div>
  <div v-if="auth.loaded && auth.verifying" class="session-verification-curtain" role="status" aria-live="polite" aria-atomic="true">
    <p>正在检查登录状态…</p>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import AppShell from './layout/AppShell.vue'
import { auth, startSessionSync } from './auth/session'
import { sessionEpoch } from './auth/lifecycle'

const router = useRouter()
onBeforeUnmount(startSessionSync())
watch([() => auth.username, () => auth.loaded, () => auth.verifying], ([username, loaded, verifying]) => {
  if (!loaded || verifying) return
  const route = router.currentRoute.value
  if (!username && route.name !== 'login') void router.replace({ name: 'login', query: { next: route.fullPath } })
  else if (username && route.name === 'login') {
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//')
      && !route.query.next.startsWith('/login') ? route.query.next : '/'
    void router.replace(next)
  }
})
</script>

<style scoped>
.session-workspace { transition: none; }
.session-verification-curtain {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  background: #f5f6f8;
  color: var(--ink);
}
.session-verification-curtain p { margin: 0; padding: 1.5rem; }
</style>
