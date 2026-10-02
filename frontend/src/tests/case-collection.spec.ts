import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import CaseCollection from '../components/CaseCollection.vue'
import type { CaseSummary } from '../api/types'
const items: CaseSummary[] = [
  { case_id: 'case_alpha', patient_id: 'anonymous', status: 'READY', created_at: '2026-10-01T00:00:00Z', input_expires_at: null },
  { case_id: 'case_beta', patient_id: 'anonymous', status: 'EXPIRED', created_at: '2026-10-01T00:00:00Z', input_expires_at: null },
]
async function render(url = '/cases') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/cases', component: { template: '<div />' } }, { path: '/cases/:id', component: { template: '<div />' } },
  ] })
  await router.push(url)
  const wrapper = mount(CaseCollection, { props: { items }, global: { plugins: [router] } })
  return { wrapper, router }
}
describe('case collection presentation and local filters', () => {
  it('switches cards/list repeatedly without losing records or changing source order', async () => {
    const { wrapper, router } = await render()
    for (let index = 0; index < 3; index++) {
      await wrapper.findAll('.segmented-control button')[1]!.trigger('click'); await flushPromises()
      expect(wrapper.find('.collection-cards').exists()).toBe(true)
      expect(router.currentRoute.value.query.view).toBe('cards')
      expect(wrapper.findAll('.case-link').map(link => link.attributes('href'))).toEqual(['/cases/case_alpha', '/cases/case_beta'])
      await wrapper.findAll('.segmented-control button')[0]!.trigger('click'); await flushPromises()
      expect(wrapper.find('.collection-cards').exists()).toBe(false)
      expect(wrapper.findAll('.segmented-control button')[0]!.attributes('aria-pressed')).toBe('true')
    }
    wrapper.unmount()
  })
  it('restores supported modes and status from URL, ignoring invalid options', async () => {
    const { wrapper, router } = await render('/cases?view=cards&status=EXPIRED')
    expect(wrapper.find('.collection-cards').exists()).toBe(true)
    expect(wrapper.findAll('.case-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('case_beta')
    await router.replace('/cases?view=bad&status=__proto__'); await flushPromises()
    expect(wrapper.find('.collection-cards').exists()).toBe(false)
    expect(wrapper.findAll('.case-row')).toHaveLength(2)
    wrapper.unmount()
  })
  it('combines ID search and status, keeps ID out of URL, and recovers from no match', async () => {
    const { wrapper, router } = await render()
    await wrapper.find('input').setValue('ALPHA')
    expect(wrapper.findAll('.case-row')).toHaveLength(1)
    expect(router.currentRoute.value.fullPath).toBe('/cases')
    await wrapper.find('select').setValue('EXPIRED'); await flushPromises()
    expect(wrapper.text()).toContain('没有匹配的病例')
    await wrapper.find('.recovery-action').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.case-row')).toHaveLength(2)
    wrapper.unmount()
  })
  it('keeps both choices when mode and filter are changed together', async () => {
    const { wrapper, router } = await render()
    await Promise.all([wrapper.findAll('.segmented-control button')[1]!.trigger('click'), wrapper.find('select').setValue('READY')])
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'cards', status: 'READY' })
    wrapper.unmount()
  })
  it('restores URL mode after detail navigation and browser back', async () => {
    const { wrapper, router } = await render('/cases?view=cards&status=READY')
    await router.push('/cases/case_alpha'); await flushPromises()
    router.back(); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/cases?view=cards&status=READY')
    expect(wrapper.find('.collection-cards').exists()).toBe(true)
    wrapper.unmount()
  })
})
