import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { auth, loadSession } from '../auth/session'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '概览' } },
  { path: '/cases', name: 'cases', component: () => import('../views/CasesView.vue'), meta: { title: '病例中心' } },
  { path: '/cases/:id', name: 'case-detail', component: () => import('../views/CaseDetailView.vue'), meta: { title: '病例详情' } },
  { path: '/preferences', name: 'preferences', component: () => import('../views/PreferencesView.vue'), meta: { title:'显示偏好' } },
  { path: '/settings', redirect:'/preferences' },
  { path: '/jobs', name: 'jobs', component: () => import('../views/JobsView.vue'), meta: { title:'任务记录' } },
  { path: '/system', name: 'system', component: () => import('../views/SystemView.vue'), meta: { title:'系统状态' } },
  { path: '/jobs/:id', name: 'job-detail', component: () => import('../views/JobDetailView.vue'), meta: { title: '任务详情' } },
  { path: '/results/:id', name: 'result-detail', component: () => import('../views/ResultDetailView.vue'), meta: { title: '结果详情' } },
  { path: '/:pathMatch(.*)*', name:'not-found', component: () => import('../views/NotFoundView.vue'), meta:{title:'页面不存在'} },
]

export function createAppRouter(history: RouterHistory = createWebHistory(import.meta.env.BASE_URL)) {
  const router = createRouter({ history, routes, scrollBehavior: () => ({ top: 0 }) })
  router.beforeEach(async to => {
    if (!auth.loaded) await loadSession()
    if (to.name === 'login') return auth.username ? '/' : true
    if (!auth.username) return { name: 'login', query: { next: to.fullPath } }
    return true
  })
  router.afterEach(to => { document.title = `${String(to.meta.title ?? '工作空间')} · EpiLocate` })
  return router
}

export { routes }
export default createAppRouter()
