import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../App.vue'
import CasesView from '../views/CasesView.vue'
import AppShell from '../layout/AppShell.vue'
import { auth, clearSession, login } from '../auth/session'
import { sessionEpoch } from '../auth/lifecycle'
import { ApiClient } from '../api/client'
import { useUiStore } from '../stores/ui'
let media: { matches: boolean; addEventListener: ReturnType<typeof vi.fn>; removeEventListener: ReturnType<typeof vi.fn> }

const wrappers: ReturnType<typeof mount>[] = []
const stores: Pinia[] = []
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
async function fixture(component: typeof App | typeof AppShell, caseComponent = { template: '<p>Old private record</p>' } as object) {
  const pinia = createPinia(); stores.push(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<p>Workspace</p>' } },
    { path: '/cases', component: { template: '<p>Cases</p>' } },
    { path: '/login', name: 'login', component: { template: '<p>Test login</p>' } },
    { path: '/cases/:id', component: caseComponent },
    { path: '/results/:id', component: { template: '<p>New result</p>' } },
  ] })
  await router.push('/cases/A')
  const wrapper = mount(component, { attachTo: document.body, global: { plugins: [pinia, router], stubs: {
    'a-button': { props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot /></button>' },
    'a-tag': { template: '<span><slot /></span>' },
  } } }); wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
beforeEach(() => {
  clearSession(); auth.username = 'alice'; auth.csrfToken = 'alice-csrf'; auth.loaded = true
  media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }
  vi.stubGlobal('matchMedia', vi.fn(() => media))
  vi.spyOn(document, 'hasFocus').mockReturnValue(true)
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  stores.splice(0).forEach(disposePinia)
  document.body.innerHTML = ''
  vi.restoreAllMocks(); vi.unstubAllGlobals()
})

describe('application session transitions', () => {
  it('keeps the hard loading boundary for an unknown initial session', async () => {
    auth.loaded = false
    const { wrapper } = await fixture(App)
    expect(wrapper.find('.login-page').exists()).toBe(true)
    expect(wrapper.find('.session-workspace').exists()).toBe(false)
    expect(wrapper.findComponent(AppShell).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Old private record')
  })

  it('releases the main area when an open mobile navigation becomes desktop width', async () => {
    const { wrapper } = await fixture(AppShell)
    const ui = useUiStore(stores[stores.length - 1]!)
    ui.sidebarOpen = true
    await flushPromises()
    expect(wrapper.find('.main-area').attributes()).toHaveProperty('inert')
    media.matches = true
    media.addEventListener.mock.calls[0]![1]()
    await flushPromises()
    expect(ui.sidebarOpen).toBe(false)
    expect(wrapper.find('.main-area').attributes()).not.toHaveProperty('inert')
    wrapper.unmount()
    expect(media.removeEventListener).toHaveBeenCalled()
  })
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


  it('hides but retains the current view during an unchanged passive session check', async () => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper, router } = await fixture(App, { template: '<input aria-label="Unsaved field" />' })
    const input = wrapper.find('input')
    await input.setValue('unsaved selection')
    const original = input.element
    const shell = wrapper.findComponent(AppShell).element
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(wrapper.find('input').isVisible()).toBe(false)
    const boundary = wrapper.find('.session-workspace')
    expect(boundary.attributes('aria-hidden')).toBe('true')
    expect(boundary.attributes()).toHaveProperty('inert')
    expect((boundary.element as HTMLElement).style.opacity).toBe('0')
    expect((boundary.element as HTMLElement).style.display).not.toBe('none')
    expect(wrapper.find('.login-page').exists()).toBe(false)
    expect(wrapper.find('.session-verification-curtain').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在检查登录状态')
    expect(wrapper.findComponent(AppShell).element).toBe(shell)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' }))
    await flushPromises()
    expect(wrapper.find('input').element).toBe(original)
    expect((original as HTMLInputElement).value).toBe('unsaved selection')
    expect(auth.verifying).toBe(false)
    expect((shell.parentElement as HTMLElement).style.display).toBe('')
    expect(shell.parentElement?.hasAttribute('inert')).toBe(false)
    expect(router.currentRoute.value.path).toBe('/cases/A')
  })

  it('conceals an explicitly visible open mobile sidebar without collapsing its ancestor', async () => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper } = await fixture(App)
    const ui = useUiStore(stores[stores.length - 1]!)
    ui.sidebarOpen = true; await flushPromises()
    const sidebar = wrapper.find('.sidebar')
    ;(sidebar.element as HTMLElement).style.visibility = 'visible'
    window.dispatchEvent(new Event('focus')); await flushPromises()
    const boundary = wrapper.find('.session-workspace')
    expect(sidebar.isVisible()).toBe(false)
    expect(boundary.attributes()).toHaveProperty('inert')
    expect(boundary.attributes('aria-hidden')).toBe('true')
    expect((boundary.element as HTMLElement).style.display).not.toBe('none')
    expect(wrapper.find('.login-page').exists()).toBe(false)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(ui.sidebarOpen).toBe(true)
    const tabKey = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true })
    window.dispatchEvent(tabKey)
    expect(tabKey.defaultPrevented).toBe(false)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' })); await flushPromises()
    expect(wrapper.find('.sidebar').element).toBe(sidebar.element)
    expect(wrapper.find('.sidebar').isVisible()).toBe(true)
    expect(ui.sidebarOpen).toBe(true)
    expect(boundary.attributes()).not.toHaveProperty('aria-hidden')
    expect(boundary.attributes()).not.toHaveProperty('inert')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    await flushPromises()
    expect(ui.sidebarOpen).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('.mobile-menu').element)
  })

  it('restores open navigation focus after verification without stealing an existing menu focus', async () => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper } = await fixture(App)
    const ui = useUiStore(stores[stores.length - 1]!)
    ui.sidebarOpen = true; await flushPromises()
    const close = wrapper.find('.navigation-close').element as HTMLElement
    window.dispatchEvent(new Event('focus')); await flushPromises()
    // jsdom does not implement inert's browser blur. Model the observed BODY focus.
    close.blur()
    expect(document.activeElement).toBe(document.body)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' })); await flushPromises()
    expect(document.activeElement).toBe(close)
    const last = wrapper.findAll('#workspace-navigation a').at(-1)!.element as HTMLElement
    last.focus()
    window.dispatchEvent(new Event('focus')); await flushPromises()
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' })); await flushPromises()
    expect(document.activeElement).toBe(last)
  })

  it('does not focus a background page and restores on the next focused verification', async () => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper } = await fixture(App)
    const ui = useUiStore(stores[stores.length - 1]!)
    ui.sidebarOpen = true; await flushPromises()
    const close = wrapper.find('.navigation-close').element as HTMLElement
    window.dispatchEvent(new Event('focus')); await flushPromises()
    close.blur()
    vi.mocked(document.hasFocus).mockReturnValue(false)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' })); await flushPromises()
    expect(document.activeElement).toBe(document.body)
    vi.mocked(document.hasFocus).mockReturnValue(true)
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(document.activeElement).toBe(document.body)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' })); await flushPromises()
    expect(document.activeElement).toBe(close)
  })

  it.each([false, true])('traps Tab from outside an open navigation (shift=%s)', async shiftKey => {
    const { wrapper } = await fixture(AppShell)
    const ui = useUiStore(stores[stores.length - 1]!)
    ui.sidebarOpen = true; await flushPromises()
    ;(document.activeElement as HTMLElement).blur()
    const key = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, cancelable: true })
    window.dispatchEvent(key)
    const items = wrapper.findAll('#workspace-navigation a, #workspace-navigation button')
    expect(key.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(items[shiftKey ? items.length - 1 : 0]!.element)
    const wrap = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: !shiftKey, cancelable: true })
    window.dispatchEvent(wrap)
    expect(wrap.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(items[shiftKey ? 0 : items.length - 1]!.element)
  })

  it.each(['other-account', 'new-cookie'])('keeps old content concealed and remounts on %s verification', async outcome => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper } = await fixture(App, { setup: () => ({ initialOwner: auth.username }), template: '<p>{{ initialOwner }} private record</p>' })
    const shell = wrapper.findComponent(AppShell).element
    const epoch = sessionEpoch.value
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(wrapper.findComponent(AppShell).isVisible()).toBe(false)
    expect(wrapper.find('.session-workspace').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.session-workspace').attributes()).toHaveProperty('inert')
    resolveSession(json({ username: outcome === 'other-account' ? 'bob' : 'alice', csrf_token: 'new-csrf' }))
    await flushPromises()
    expect(sessionEpoch.value).toBeGreaterThan(epoch)
    expect(wrapper.findComponent(AppShell).element).not.toBe(shell)
    expect(wrapper.find('.session-verification-curtain').exists()).toBe(false)
    expect(wrapper.find('.session-workspace').attributes()).not.toHaveProperty('aria-hidden')
    if (outcome === 'other-account') {
      expect(wrapper.text()).not.toContain('alice private record')
      expect(wrapper.text()).toContain('bob private record')
    }
  })

  it('keeps the uncertain Case POST key across unchanged focus without automatically retrying', async () => {
    let resolveSession!: (response: Response) => void
    const keys: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      if (url === '/auth/session') return new Promise<Response>(resolve => { resolveSession = resolve })
      if (init.method === 'POST') {
        keys.push((init.headers as Record<string, string>)['Idempotency-Key']!)
        if (keys.length === 1) throw new TypeError('connection lost')
        return json({ case_id: 'case_accepted', patient_id: 'pat', status: 'CREATED', created_at: '' }, 201)
      }
      return json({ items: [], next_cursor: null })
    }))
    const { wrapper, router } = await fixture(App, CasesView)
    const create = () => wrapper.findAll('button').find(button => button.text() === '创建匿名病例')!
    await create().trigger('click'); await flushPromises()
    expect(keys).toHaveLength(1)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(create().isVisible()).toBe(false)
    resolveSession(json({ username: 'alice', csrf_token: 'alice-csrf' }))
    await flushPromises()
    expect(keys).toHaveLength(1)
    await create().trigger('click'); await flushPromises()
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    expect(router.currentRoute.value.path).toBe('/cases/case_accepted')
  })

  it.each([401, 503])('removes retained private views when passive verification fails with %s', async status => {
    let resolveSession!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSession = resolve })))
    const { wrapper, router } = await fixture(App)
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(wrapper.findComponent(AppShell).isVisible()).toBe(false)
    resolveSession(json({ code: 'UNAUTHENTICATED' }, status))
    await flushPromises()
    expect(wrapper.findComponent(AppShell).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Old private record')
    expect(router.currentRoute.value.query.next).toBe('/cases/A')
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
