import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: 'Dashboard' } },
  { path: '/cases', name: 'cases', component: () => import('../views/CasesView.vue'), meta: { title: '病例中心' } },
  { path: '/cases/:id', name: 'case-detail', component: () => import('../views/CaseDetailView.vue'), meta: { title: '病例详情' } },
  { path: '/jobs/:id', name: 'job-detail', component: () => import('../views/JobDetailView.vue'), meta: { title: '任务详情' } },
  { path: '/results/:id', name: 'result-detail', component: () => import('../views/ResultDetailView.vue'), meta: { title: '结果详情' } },
]

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  return createRouter({ history, routes, scrollBehavior: () => ({ top: 0 }) })
}

export { routes }
export default createAppRouter()
