import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { CreatedCase } from '../api/types'
import { apiClient } from '../api/client'
import { auth, clearSession } from '../auth/session'
import { useCreateCase } from '../composables/useCreateCase'
import { inputStatus, jobStatus } from '../domain/clinical'

const created = {case_id:'case_created',patient_id:'anonymous',status:'CREATED' as const,created_at:'2026-10-03T00:00:00Z'}
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => { clearSession(false); auth.username='alice'; auth.loaded=true })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks() })
async function fixture() {
  const router = createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{render:()=>h('div')}},{path:'/cases/:id',component:{render:()=>h('div')}}]})
  await router.push('/')
  let action!: ReturnType<typeof useCreateCase>
  wrappers.push(mount(defineComponent({setup(){action=useCreateCase();return()=>h('div')}}),{global:{plugins:[router]}}))
  return {router, action}
}
describe('creation recovery review',()=>{
  it('does not create a second case after route loading rejects',async()=>{
    const {router,action}=await fixture()
    const create=vi.spyOn(apiClient,'createCase').mockResolvedValue(created)
    vi.spyOn(router,'push').mockRejectedValueOnce(new Error('Chunk unavailable')).mockResolvedValueOnce(undefined)
    await action.createCase(); await action.createCase()
    expect(create).toHaveBeenCalledTimes(1)
  })
  it('does not create a second case after navigation is aborted',async()=>{
    const {router,action}=await fixture()
    const create=vi.spyOn(apiClient,'createCase').mockResolvedValue(created)
    router.beforeEach(to => to.path.startsWith('/cases/') ? false : true)
    await action.createCase(); await action.createCase()
    expect(create).toHaveBeenCalledTimes(1)
  })
  it('blocks a duplicate click while the same creation is pending',async()=>{
    const {action}=await fixture()
    let resolve!: (value:CreatedCase)=>void
    const create=vi.spyOn(apiClient,'createCase').mockReturnValue(new Promise(done=>{resolve=done}))
    const first=action.createCase()
    await action.createCase()
    expect(create).toHaveBeenCalledTimes(1)
    resolve(created); await first
  })
  it('reuses the same key after an uncertain network result',async()=>{
    const {action}=await fixture()
    const create=vi.spyOn(apiClient,'createCase').mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(created)
    await action.createCase(); await action.createCase()
    expect(create).toHaveBeenCalledTimes(2)
    expect(create.mock.calls[0]![1]).toEqual(create.mock.calls[1]![1])
  })
  it('ignores a late creation response after identity invalidation',async()=>{
    const {router,action}=await fixture()
    let resolve!: (value:CreatedCase)=>void
    vi.spyOn(apiClient,'createCase').mockReturnValue(new Promise(done=>{resolve=done}))
    const navigate=vi.spyOn(router,'push')
    const request=action.createCase()
    clearSession(false); auth.username='bob'; auth.loaded=true
    resolve(created); await request
    expect(navigate).not.toHaveBeenCalled()
    expect(action.creating.value).toBe(false)
    expect(action.createError.value).toBeNull()
  })
  it.each(['constructor','toString','__proto__'])('treats inherited key %s as unknown',value=>{
    expect(inputStatus(value)).toEqual({label:'状态未知',tone:'neutral'})
    expect(jobStatus(value)).toEqual({label:'状态未知',tone:'neutral'})
  })
})
