<template>
  <main class="login-page">
    <div class="login-layout">
    <aside class="login-story" aria-label="工作台介绍">
      <p class="login-kicker">EPILOCATE / 影像研究</p>
      <h2>从一张 CT，<br>开始可追溯的分析。</h2>
      <p>准备匿名病例，查看任务状态，在影像中阅读模型响应。</p>
      <ol><li><span>01</span> 上传单切片 CT</li><li><span>02</span> 创建分类或遮挡任务</li><li><span>03</span> 阅读影像与模型响应</li></ol>
      <p class="login-boundary">仅供研究 · 模型响应不等同于病灶标注或临床诊断</p>
    </aside>
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
