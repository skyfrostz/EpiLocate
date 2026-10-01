import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../App.vue'
import AppShell from '../layout/AppShell.vue'
import { auth, clearSession, login } from '../auth/session'
import { ApiClient } from '../api/client'

const wrappers: ReturnType<typeof mount>[] = []
const stores: Pinia[] = []
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
async function fixture(component: typeof App | typeof AppShell) {
  const pinia = createPinia(); stores.push(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/login', name: 'login', component: { template: '<p>Test login</p>' } },
    { path: '/cases/:id', component: { template: '<p>Old private record</p>' } },
    { path: '/results/:id', component: { template: '<p>New result</p>' } },
  ] })
  await router.push('/cases/A')
  const wrapper = mount(component, { global: { plugins: [pinia, router] } }); wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
beforeEach(() => { clearSession(); auth.username = 'alice'; auth.csrfToken = 'alice-csrf'; auth.loaded = true })
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  stores.splice(0).forEach(disposePinia)
  vi.restoreAllMocks(); vi.unstubAllGlobals()
})

describe('application session transitions', () => {
  it('does not redirect a newly logged-in user when an older logout completes', async () => {
    let resolveLogout!: (response: Response) => void
    const pendingLogout = new Promise<Response>(done => { resolveLogout = done })
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(pendingLogout)
      .mockResolvedValueOnce(json({ username: 'bob', csrf_token: 'bob-csrf' })))
    const { wrapper, router } = await fixture(AppShell)
    await wrapper.find('.logout-button').trigger('click')
    clearSession()
    await login('bob', 'synthetic-fixture-only')
    await router.push('/results/new-result')
    resolveLogout(new Response(null, { status: 204 }))
    await flushPromises()
    expect(auth.username).toBe('bob')
    expect(router.currentRoute.value.path).toBe('/results/new-result')
  })

  it('removes private views on 401 and preserves the original login destination', async () => {
    const { wrapper, router } = await fixture(App)
    expect(wrapper.text()).toContain('Old private record')
    const client = new ApiClient({ fetcher: vi.fn(async () => json({ code: 'UNAUTHENTICATED' }, 401)) })
    await expect(client.listCases()).rejects.toMatchObject({ status: 401 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Old private record')
    expect(wrapper.text()).toContain('Test login')
    expect(router.currentRoute.value.query.next).toBe('/cases/A')
  })
})
