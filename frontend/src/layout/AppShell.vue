<template>
  <div class="app-shell">
    <a class="skip-link" href="#workspace-content">跳转到主要内容</a>
    <button
      v-if="ui.sidebarOpen"
      class="mobile-scrim"
      type="button"
      aria-label="关闭导航"
      @click="ui.closeSidebar"
    />
    <aside id="workspace-navigation" class="sidebar" :class="{ 'sidebar-open': ui.sidebarOpen }" aria-label="主导航">
      <button v-if="ui.sidebarOpen" class="navigation-close" aria-label="关闭菜单" type="button" @click="ui.closeSidebar">关闭导航</button>
      <RouterLink class="brand" to="/" @click="ui.closeSidebar">
        <span class="brand-symbol" aria-hidden="true"><span /></span>
        <span class="brand-wordmark"><strong>EpiLocate</strong><small>医学影像研究系统</small></span>
      </RouterLink>

      <div class="sidebar-caption">WORKSPACE / 工作区</div>
      <nav class="nav-list" aria-label="工作区页面">
        <RouterLink to="/" class="nav-item" active-class="nav-active" exact-active-class="nav-active" @click="ui.closeSidebar">
          <span class="nav-icon nav-icon-dashboard" aria-hidden="true" />
          <span>工作台</span>
          <span class="nav-index">01</span>
        </RouterLink>
        <RouterLink to="/cases" class="nav-item" active-class="nav-active" @click="ui.closeSidebar">
          <span class="nav-icon nav-icon-cases" aria-hidden="true" />
          <span>病例中心</span>
          <span class="nav-index">02</span>
        </RouterLink>
      </nav>

      <div class="sidebar-caption secondary-caption">CONTEXT / 当前范围</div>
      <div class="sidebar-context">
        <span class="context-dot" />
        <span>单切片 CT · 研究用途</span>
      </div>
      <p class="sidebar-guidance">任务和结果页面由对应的匿名 ID 进入。页面不会生成示例诊断。</p>

      <div class="sidebar-bottom">
        <div class="sidebar-rule" />
        <span>WEB SYSTEM</span>
        <strong>V1.0</strong>
      </div>
    </aside>

    <div class="main-area" :inert="ui.sidebarOpen ? true : undefined">
      <header class="topbar">
        <button class="mobile-menu" type="button" :aria-expanded="ui.sidebarOpen" aria-controls="workspace-navigation" aria-label="打开导航" @click="ui.toggleSidebar">☰</button>
        <div class="breadcrumb"><span>EPILOCATE</span><b>/</b><strong>{{ title }}</strong></div>
        <div class="topbar-right">
          <span class="research-label">{{ auth.username }}</span>
          <button class="logout-button" type="button" :disabled="loggingOut" @click="signOut">退出</button>
          <span v-if="logoutError" class="login-error" role="alert">{{ logoutError }}</span>
          <span class="api-label"><i />API v2</span>
          <span class="topbar-divider" />
          <span class="research-label">仅供研究</span>
        </div>
      </header>
      <main id="workspace-content" class="content" tabindex="-1"><slot /></main>
      <footer class="page-footer"><span>EpiLocate · 医学影像研究系统</span><span>所有结果以服务端返回为准</span></footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useUiStore } from '../stores/ui'
import { auth, logout } from '../auth/session'
import { ref } from 'vue'
import { errorText } from '../api/errors'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const loggingOut = ref(false)
const logoutError = ref('')
const title = computed(() => String(route.meta.title ?? '工作台'))
watch(() => ui.sidebarOpen, async opened => {
  await nextTick()
  document.querySelector<HTMLElement>(opened ? '.navigation-close' : window.matchMedia('(min-width: 768px)').matches ? '#workspace-content' : '.mobile-menu')?.focus()
})
let desktopMedia: MediaQueryList | undefined
function restoreDesktopNavigation() { if (desktopMedia?.matches) ui.closeSidebar() }
function navigationKeys(event: KeyboardEvent) {
  if (!ui.sidebarOpen) return
  if (event.key === 'Escape') { event.preventDefault(); ui.closeSidebar(); return }
  if (event.key !== 'Tab') return
  const items = [...document.querySelectorAll<HTMLElement>('#workspace-navigation a, #workspace-navigation button')]
  const first = items[0], last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
onMounted(() => {
  window.addEventListener('keydown', navigationKeys)
  desktopMedia = window.matchMedia('(min-width: 768px)')
  desktopMedia.addEventListener('change', restoreDesktopNavigation)
  restoreDesktopNavigation()
})
onBeforeUnmount(() => { window.removeEventListener('keydown', navigationKeys); desktopMedia?.removeEventListener('change', restoreDesktopNavigation); ui.closeSidebar() })

async function signOut() {
  const epoch = sessionEpoch.value
  loggingOut.value = true
  logoutError.value = ''
  try {
    await logout()
    if (!auth.username) await router.replace({ name: 'login' })
  } catch (cause) {
    if (!isSessionCurrent(epoch)) return
    logoutError.value = errorText(cause)
  } finally {
    loggingOut.value = false
  }
}
</script>
