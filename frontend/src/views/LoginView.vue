<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-mark" aria-hidden="true">+</div>
      <p class="login-kicker">EPILOCATE · TEAM ACCESS</p>
      <h1 id="login-title">登录工作台</h1>
      <p class="page-intro">使用管理员分配的个人账号。病例与结果仅对其所属成员可见。</p>
      <form @submit.prevent="submit">
        <label for="username">账号</label>
        <input id="username" v-model.trim="username" autocomplete="username" required :disabled="busy" />
        <label for="password">密码</label>
        <input id="password" v-model="password" type="password" autocomplete="current-password" required :disabled="busy" />
        <p v-if="error || auth.error" class="login-error" role="alert">{{ error || auth.error }}</p>
        <button type="submit" :disabled="busy">{{ busy ? '正在登录…' : '登录' }}</button>
      </form>
      <p class="login-foot">单切片 CT · 研究用途 · 请仅上传合成或合规去标识影像</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, login } from '../auth/session'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await login(username.value, password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//')
      ? route.query.next : '/'
    await router.replace(next)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败，请重试。'
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>
