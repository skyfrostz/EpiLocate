import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Component } from 'vue'
import { ApiClient, apiClient } from '../api/client'
import { ApiRequestError } from '../api/errors'
import type { CaseListResponse, CaseSummary, JobRecord } from '../api/types'
import { auth, clearSession } from '../auth/session'
import { useJobStore } from '../stores/jobs'
import { useWorkspaceStore } from '../stores/workspace'
import { createAppRouter } from '../router'
import DashboardView from '../views/DashboardView.vue'
import CasesView from '../views/CasesView.vue'
import JobsView from '../views/JobsView.vue'
import SystemView from '../views/SystemView.vue'

let pinia: Pinia
const wrappers: ReturnType<typeof mount>[] = []
const emptyPage: CaseListResponse = { items:[], next_cursor:null }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {status,headers:{'Content-Type':'application/json'}})
function deferred<T>() { let resolve!: (value:T)=>void; const promise = new Promise<T>(done=>{resolve=done}); return {promise,resolve} }
function job(id: string, status: JobRecord['status'] = 'RUNNING'): JobRecord {
  return {job_id:id,case_id:'case_alpha',kind:'PREDICTION',status,attempt_no:1,retry_count:0,lease_expire_time:null,last_heartbeat:null,failure_reason:null,progress:null,estimated_remaining_time_ms:null,result_id:status==='COMPLETED'?'result_alpha':null,error:null,created_at:'2026-10-03T00:00:00Z',finished_at:null}
}
function row(id: string, status: CaseSummary['status'] = 'READY'): CaseSummary {
  return {case_id:id,patient_id:'anonymous',status,created_at:'2026-10-03T00:00:00Z',input_expires_at:null}
}
async function render(component: Component) {
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
  await router.push('/')
  const wrapper=mount(component,{global:{plugins:[pinia,router],stubs:{'a-button':{template:'<button><slot /></button>'}}}})
  wrappers.push(wrapper); return wrapper
}
beforeEach(()=>{
  clearSession(false); auth.username='alice'; auth.loaded=true
  pinia=createPinia(); setActivePinia(pinia)
  vi.stubGlobal('scrollTo',vi.fn())
  vi.stubGlobal('fetch',vi.fn(async()=>{throw new Error('Unexpected network request')}))
})
afterEach(()=>{
  wrappers.splice(0).forEach(w=>w.unmount()); disposePinia(pinia)
  vi.restoreAllMocks(); vi.unstubAllGlobals()
})

describe('bounded authorized known-task reads',()=>{
  it('requests at most 30 known job IDs, with no discovery endpoint and no more than 3 requests in flight',async()=>{
    const store=useJobStore()
    for(let i=0;i<35;i++) store.upsert(job(`job_${i}`),1)
    let active=0,maximum=0
    const fetcher=vi.fn(async(input:RequestInfo|URL)=>{
      const path=String(input); expect(path).toMatch(/^\/api\/v2\/jobs\/job_\d+$/)
      active++; maximum=Math.max(maximum,active)
      await Promise.resolve(); active--
      return json(job(path.split('/').at(-1)!,'COMPLETED'))
    })
    await store.refreshKnown(new ApiClient({fetcher:fetcher as typeof fetch}))
    expect(fetcher).toHaveBeenCalledTimes(30); expect(maximum).toBeLessThanOrEqual(3)
    expect(fetcher.mock.calls.map(call=>String(call[0]))).not.toContain('/api/v2/jobs/job_0')
    expect(store.byId.job_0?.status).toBe('RUNNING')
  })
  it('retains a failed job read and its observation time while independently updating successful reads',async()=>{
    const store=useJobStore(); store.upsert(job('job_ok'),11); store.upsert(job('job_bad'),22)
    const getJob=vi.fn(async(id:string)=>{
      if(id==='job_bad') throw new ApiRequestError(503,'BACKEND_UNAVAILABLE','/private/token',true,null)
      return job(id,'COMPLETED')
    })
    await store.refreshKnown({getJob} as unknown as ApiClient)
    expect(store.byId.job_ok?.status).toBe('COMPLETED'); expect(store.observedAtById.job_ok).toBeGreaterThan(11)
    expect(store.byId.job_bad?.status).toBe('RUNNING'); expect(store.observedAtById.job_bad).toBe(22)
    expect(store.collectionErrors.job_bad).toContain('服务暂时不可用')
    expect(store.collectionErrors.job_bad).not.toContain('/private/token')
  })
  it('aborts collection reads on session invalidation and rejects a late response even if transport ignores abort',async()=>{
    const store=useJobStore(); store.upsert(job('job_late'),20)
    const pending=deferred<JobRecord>(),getJob=vi.fn((_id:string,_signal?:AbortSignal)=>pending.promise)
    const request=store.refreshKnown({getJob} as unknown as ApiClient)
    clearSession(false)
    expect(getJob.mock.calls[0]![1]!.aborted).toBe(true)
    pending.resolve(job('job_late','COMPLETED')); await request
    expect(store.byId).toEqual({}); expect(store.observedAtById).toEqual({}); expect(store.collectionErrors).toEqual({}); expect(store.collectionLoading).toBe(false)
  })
  it('does not let an older refresh overwrite a newer terminal response',async()=>{
    const store=useJobStore(); store.upsert(job('job_order'),20)
    const pending=deferred<JobRecord>()
    const getJob=vi.fn((_id:string,_signal?:AbortSignal)=>pending.promise).mockImplementationOnce((_id,_signal)=>pending.promise).mockResolvedValueOnce(job('job_order','COMPLETED'))
    const client={getJob} as unknown as ApiClient
    const older=store.refreshKnown(client),newer=store.refreshKnown(client)
    await newer; const observed=store.observedAtById.job_order
    expect(getJob.mock.calls[0]![1]!.aborted).toBe(true)
    pending.resolve(job('job_order')); await older
    expect(store.byId.job_order?.status).toBe('COMPLETED'); expect(store.observedAtById.job_order).toBe(observed)
  })
})

describe('honest page scope and private session state',()=>{
  it('opens an empty task list without requesting a global queue or inventing records',async()=>{
    const read=vi.spyOn(apiClient,'getJob'),wrapper=await render(JobsView); await flushPromises()
    expect(read).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无已确认任务'); expect(wrapper.text()).toContain('本会话'); expect(wrapper.text()).toContain('历史范围不完整')
  })
  it('shows last known task state on failed re-read and never turns missing progress into a percentage',async()=>{
    useJobStore().upsert(job('job_old'),20)
    vi.spyOn(apiClient,'getJob').mockRejectedValue(new ApiRequestError(500,'BACKEND_UNAVAILABLE','token=/private',true,null))
    const wrapper=await render(JobsView); await flushPromises()
    expect(wrapper.text()).toContain('分析中'); expect(wrapper.text()).toContain('读取失败 · 上次状态'); expect(wrapper.text()).toContain('未提供')
    expect(wrapper.text()).not.toMatch(/\d+%/); expect(wrapper.text()).not.toContain('token=/private')
  })
  it('keeps recent visits in memory only and removes them when login state is invalidated',()=>{
    const write=vi.spyOn(Storage.prototype,'setItem'),workspace=useWorkspaceStore()
    workspace.visit('case_private'); workspace.visit('case_other')
    expect(workspace.visits).toHaveLength(2); expect(write).not.toHaveBeenCalled()
    clearSession(false); expect(workspace.visits).toEqual([]); expect(write).not.toHaveBeenCalled()
  })
  it('loads only a case page on Dashboard and keeps independent completed and failed tasks without case-level completion',async()=>{
    const cases=vi.spyOn(apiClient,'listCases').mockResolvedValue({items:[row('case_alpha')],next_cursor:null})
    const dicom=vi.spyOn(apiClient,'getCaseDicom'),result=vi.spyOn(apiClient,'getResult'),assets=vi.spyOn(apiClient,'getResultAsset')
    const store=useJobStore(); store.upsert(job('job_completed','COMPLETED'))
    store.upsert({...job('job_failed','FAILED'),kind:'OCCLUSION'})
    const wrapper=await render(DashboardView); await flushPromises()
    expect(cases).toHaveBeenCalledTimes(1); expect(dicom).not.toHaveBeenCalled(); expect(result).not.toHaveBeenCalled(); expect(assets).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
    expect(wrapper.findAll('.task-mini')).toHaveLength(2); expect(wrapper.text()).toContain('任务已完成'); expect(wrapper.text()).toContain('分析未完成')
    expect(wrapper.find('tbody').text()).toContain('未查询'); expect(wrapper.text()).not.toContain('分析已完成'); expect(wrapper.text()).not.toContain('正类概率')
  })
  it('filters only loaded case rows and clears a no-match filter without a server search',async()=>{
    const read=vi.spyOn(apiClient,'listCases').mockResolvedValue({items:[row('case_alpha'),row('case_beta','EXPIRED')],next_cursor:'next'})
    const wrapper=await render(CasesView); await flushPromises()
    await wrapper.find('input[type=search]').setValue('ALPHA')
    expect(wrapper.findAll('.case-link').map(e=>e.text())).toEqual(['case_alpha'])
    await wrapper.findAll('select')[0]!.setValue('EXPIRED')
    expect(wrapper.text()).toContain('没有符合筛选条件'); expect(wrapper.text()).not.toContain('暂无病例')
    await wrapper.findAll('button').find(e=>e.text()==='清空筛选')!.trigger('click')
    expect(wrapper.findAll('.case-link')).toHaveLength(2); expect(read).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('筛选已加载病例')
  })
  it('keeps local filters active while cursor pagination brings matching cases into the loaded scope',async()=>{
    const read=vi.spyOn(apiClient,'listCases').mockResolvedValueOnce({items:[row('case_alpha')],next_cursor:'opaque_cursor'}).mockResolvedValueOnce({items:[row('case_later')],next_cursor:null})
    const wrapper=await render(CasesView); await flushPromises()
    await wrapper.find('input[type=search]').setValue('later')
    expect(wrapper.text()).toContain('没有符合筛选条件')
    await wrapper.findAll('button').find(e=>e.text()==='加载更多')!.trigger('click'); await flushPromises()
    expect(read).toHaveBeenLastCalledWith('opaque_cursor',30,expect.any(AbortSignal))
    expect(wrapper.findAll('.case-link').map(e=>e.text())).toEqual(['case_later'])
    expect(wrapper.text()).toContain('已加载 2 例')
  })
  it('does not probe internal services or grant system details to a username named admin',async()=>{
    auth.username='admin'; const wrapper=await render(SystemView); await flushPromises()
    expect(fetch).not.toHaveBeenCalled(); expect(wrapper.findAll('.ep-status').filter(e=>e.text()==='未接入')).toHaveLength(4)
    expect(wrapper.text()).toContain('尚未提供角色与系统详情权限')
    expect(wrapper.text()).not.toMatch(/GPU Online|在线率|利用率\s*\d|system:read/)
  })
  it('limits the manual system check to Case API and preserves the last observation without claiming health after a later failure',async()=>{
    const read=vi.spyOn(apiClient,'listCases').mockResolvedValueOnce(emptyPage).mockRejectedValueOnce(new ApiRequestError(500,'BACKEND_UNAVAILABLE','secret/path',true,null))
    const wrapper=await render(SystemView),check=wrapper.findAll('button').find(e=>e.text()==='检查病例 API')!
    await check.trigger('click'); await flushPromises()
    const observed=wrapper.findAll('.availability-row')[1]!.find('small').text()
    expect(observed).toContain('最近响应：'); expect(wrapper.text()).toContain('曾响应')
    await check.trigger('click'); await flushPromises()
    expect(read).toHaveBeenLastCalledWith(undefined,1,expect.any(AbortSignal))
    expect(wrapper.findAll('.availability-row')[1]!.find('small').text()).toBe(observed)
    expect(wrapper.text()).toContain('读取失败'); expect(wrapper.text()).toContain('查询失败不能确定组件离线')
    expect(wrapper.text()).not.toContain('secret/path'); expect(wrapper.findAll('.ep-status').filter(e=>e.text()==='未接入')).toHaveLength(4)
  })
  it.each(['/jobs','/system'])('requires a session for new route %s and retains the intended destination',async(path)=>{
    clearSession(false)
    const router=createAppRouter(createMemoryHistory()); await router.push(path)
    expect(router.currentRoute.value.name).toBe('login'); expect(router.currentRoute.value.query.next).toBe(path)
  })
})
