import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import CaseCollection from '../components/CaseCollection.vue'
import type { CaseSummary } from '../api/types'
import { sessionEpoch } from '../auth/lifecycle'

const items: CaseSummary[] = [
  { case_id:'case_alpha', patient_id:'synthetic_a', status:'READY', created_at:'2026-01-01', input_expires_at:null },
  { case_id:'case_beta', patient_id:'synthetic_b', status:'EXPIRED', created_at:'2026-01-01', input_expires_at:null },
]

async function render(url = '/cases') {
  const router = createRouter({ history:createMemoryHistory(), routes:[
    { path:'/cases', component:{ template:'<div />' } }, { path:'/cases/:id', component:{ template:'<div />' } },
  ] })
  await router.push(url)
  const wrapper = mount(CaseCollection, { props:{ items }, global:{ plugins:[router] } })
  return { router, wrapper }
}

describe('loaded case records', () => {
  it('restores allowed query values on reload and Back; rejects malformed, repeated or unsupported choices', async () => {
    const { router, wrapper } = await render('/cases?view=cards&status=EXPIRED')
    expect(wrapper.findAll('.case-cards .case-link').map(link => link.text())).toEqual(['case_beta'])
    await router.push('/cases/case_beta')
    router.back(); await flushPromises()
    expect(wrapper.findAll('.case-cards .case-link')).toHaveLength(1)
    await router.replace('/cases?view=cards&view=list&status=__proto__')
    await flushPromises()
    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.findAll('.case-link').map(link => link.text())).toEqual(['case_alpha','case_beta'])
    wrapper.unmount()
  })

  it('merges simultaneous mode and status changes; searches locally and clears the search on identity changes', async () => {
    const { router, wrapper } = await render()
    await wrapper.get('input[type=search]').setValue('CASE_ALPHA')
    const buttons = wrapper.get('[role=group]').findAll('button')
    await Promise.all([buttons[1]!.trigger('click'), wrapper.get('select').setValue('EXPIRED')])
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view:'cards', status:'EXPIRED' })
    expect(wrapper.text()).toContain('没有符合筛选条件')
    sessionEpoch.value++; await flushPromises()
    expect((wrapper.get('input[type=search]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.get('.case-cards .case-link').text()).toBe('case_beta')
    await buttons[0]!.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ status:'EXPIRED' })
    expect(wrapper.find('table').exists()).toBe(true)
    wrapper.unmount()
  })
})
