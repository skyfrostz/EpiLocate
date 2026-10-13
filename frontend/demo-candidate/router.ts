import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { auth, loadSession } from '../auth/session'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
  { path: '/', name: 'demo-history', component: () => import('../views/DemoIndexView.vue'), meta: { title: '历史结果' } },
  { path: '/results/:id', name: 'result-detail', component: () => import('../views/ResultDetailView.vue'), meta: { title: '历史结果详情' } },
  { path: '/preferences', name: 'preferences', component: () => import('../views/PreferencesView.vue'), meta: { title: '显示偏好' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]
export function createAppRouter(history: RouterHistory = createWebHistory(import.meta.env.BASE_URL)) {
  const router = createRouter({ history, routes, scrollBehavior: () => ({ top: 0 }) })
  router.beforeEach(async to => {
    if (!auth.loaded) await loadSession()
    if (to.name === 'login') return auth.username ? '/' : true
    return auth.username ? true : { name: 'login', query: { next: to.fullPath } }
  })
  router.afterEach(to => { document.title = `${String(to.meta.title ?? '历史结果')} · EpiLocate` })
  return router
}
export { routes }
export default createAppRouter()
