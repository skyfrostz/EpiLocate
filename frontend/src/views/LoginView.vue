<template>
  <main class="login-page">
    <div class="login-layout">
    <aside class="login-story" aria-label="EpiLocate 医学影像研究系统">
      <div class="brand"><span class="brand-symbol" aria-hidden="true"><span /></span><span class="brand-wordmark"><strong>EpiLocate</strong><small>医学影像研究系统</small></span></div>
      <div class="login-canvas-mark" aria-hidden="true"><svg viewBox="0 0 200 180" fill="none"><rect x="25" y="15" width="150" height="150" rx="20"/><rect x="45" y="35" width="110" height="110" rx="12"/><path d="M100 52v76M62 90h76M25 90H9M175 90h16M100 15V0M100 165v15"/><circle cx="100" cy="90" r="24"/></svg></div>
      <h2>以病例为起点。<br>让影像回到中心。</h2>
      <p>病例、任务与结果，在同一个工作空间有序衔接。</p>
      <p class="login-boundary">研究输出 ≠ 临床诊断</p>
    </aside>
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-mark" aria-hidden="true">+</div>
      <p class="login-kicker">个人工作空间</p>
      <h1 id="login-title">登录 EpiLocate</h1>
      <p class="page-intro">使用已分配的个人账号访问授权病例。</p>
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
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, login } from '../auth/session'
import { errorText } from '../api/errors'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//')
    && !route.query.next.startsWith('/login') ? route.query.next : '/'
  try {
    await login(username.value, password.value)
    await router.replace(next)
  } catch (cause) {
    error.value = errorText(cause)
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>
