<template>
  <main v-if="!auth.loaded" class="login-page" role="status">正在检查登录状态…</main>
  <RouterView v-else-if="$route.name === 'login'" />
  <AppShell v-else><RouterView /></AppShell>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { RouterView } from 'vue-router'
import AppShell from './layout/AppShell.vue'
import { auth } from './auth/session'

watch(() => auth.username, (username, previous) => {
  if (previous && !username) window.location.assign('/login')
})
</script>
