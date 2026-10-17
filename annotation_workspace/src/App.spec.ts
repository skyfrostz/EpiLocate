import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {mount,flushPromises} from '@vue/test-utils'
import {defineComponent,onMounted} from 'vue'
import App from './App.vue'
const id='11111111-1111-4111-8111-111111111111'
const g={width:112,height:80,ipp:[12,34,56],iop:[0,1,0,-1,0,0],spacing:[.7,1.2]}
const binding={case_id:'GENERATED_ANNOTATION_CASE',slice_id:'GENERATED_SLICE',study_uid:'2.25.1',series_uid:'2.25.2',sop_instance_uid:'2.25.3',frame_of_reference_uid:'2.25.4',ct_sha256:'a'.repeat(64),geometry_sha256:'b'.repeat(64),geometry_version:'DICOM_NATIVE_CENTRES_LPS_V1'}
const polygon=defineComponent({props:['revision'],emits:['ready','changed'],setup(_,ctx){onMounted(()=>ctx.emit('ready'));return()=>null}})
let rows:any[],events:any[],loggedIn:boolean,mode:string,fetchMock:any,last:any
const ok=(value:any,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json'}})
beforeEach(()=>{
 sessionStorage.clear();rows=[];events=[];loggedIn=false;mode='normal';last=null
 fetchMock=vi.fn(async(url:string,options:any={})=>{
  if(url==='/auth/session')return loggedIn?ok({username:'synthetic-doctor',csrf_token:'csrf'}):ok({code:'UNAUTHENTICATED'},401)
  if(url==='/auth/login'){loggedIn=true;return ok({username:'synthetic-doctor',csrf_token:'csrf'})}
  if(url==='/auth/logout'){loggedIn=false;return new Response(null,{status:204})}
  if(url.endsWith('/annotation-context'))return ok({binding:{...binding,geometry:g},actor:'synthetic-doctor',can_edit:true})
  if(url.endsWith('/dicom'))return new Response('generated')
  if(url.endsWith('/history')){if(mode==='history-failure'&&last)return ok({code:'TEMPORARY'},503);return ok({events})}
  if(url.includes('/annotation-operations/'))return last?ok(last):ok({code:'OPERATION_NOT_FOUND'},404)
  if(url.endsWith('/annotations')&&options.method==='POST'){
   if(mode==='conflict')return ok({code:'VERSION_CONFLICT'},409)
   const b=JSON.parse(options.body);last={...b,version:b.expected_version+1,author:'synthetic-doctor',author_id:'server-author',created_at:'generated-time',updated_at:'generated-time',review_status:'UNREVIEWED',revision_sha256:'c'.repeat(64),training_gt_eligible:false}
   rows=[last];events.push({revision_id:String(events.length),version:last.version,action:b.state==='WITHDRAWN'?'WITHDRAW':last.version===1?'CREATE':'UPDATE',actor:last.author,time:'generated-time'})
   if(mode==='lost-response')throw new TypeError('reply lost after commit')
   if(mode==='timeout')throw new DOMException('Request timed out','TimeoutError')
   return ok(last)
  }
  if(url.endsWith('/annotations'))return ok({items:rows})
  throw Error('unexpected route '+url)
 });vi.stubGlobal('fetch',fetchMock);vi.stubGlobal('confirm',()=>true)
})
afterEach(()=>vi.unstubAllGlobals())
const create=()=>mount(App,{global:{stubs:{PolygonViewport:polygon}}})
async function login(wrapper:any){await flushPromises();const inputs=wrapper.findAll('input');await inputs[0].setValue('synthetic-doctor');await inputs[1].setValue('not-a-real-secret');await wrapper.find('form').trigger('submit');await flushPromises()}
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text()===text)!
async function draw(w:any,x=10){w.findComponent(polygon).vm.$emit('changed',id,[[x,10],[50,10],[50,40],[10,40]]);await flushPromises()}
it('draw -> persist -> remount refresh -> edit new version -> withdraw retains audit',async()=>{
 let w=create();await login(w);await draw(w);expect(button(w,'保存新版本').attributes('disabled')).toBeUndefined();await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('已持久化版本 1');expect(last.author).toBe('synthetic-doctor');expect(last.binding).toEqual(binding)
 w.unmount();w=create();await flushPromises();expect(w.text()).toContain('v1');expect(w.findComponent(polygon).props('revision').vertices[0]).toEqual([10,10])
 await draw(w,11);await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('已持久化版本 2');expect(last.expected_version).toBe(1)
 await button(w,'撤回当前标注').trigger('click');await flushPromises();expect(w.text()).toContain('已撤回');expect(w.text()).toContain('WITHDRAW');expect(events).toHaveLength(3);expect(last.version).toBe(3);w.unmount()
})
it('409 keeps unsaved edit and offers explicit server reload',async()=>{
 const w=create();await login(w);await draw(w);mode='conflict';await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('409 版本或身份冲突');expect(w.text()).toContain('未保存更改');expect(rows).toHaveLength(0);w.unmount()
})
it('ambiguous save blocks repeat and reconciles committed operation after remount',async()=>{
 let w=create();await login(w);await draw(w);mode='lost-response';await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('上次保存结果待对账');expect(button(w,'保存新版本').attributes('disabled')).toBeDefined()
 const posts=()=>fetchMock.mock.calls.filter((x:any)=>x[0].endsWith('/annotations')&&x[1]?.method==='POST');expect(posts()).toHaveLength(1)
 w.unmount();w=create();await flushPromises();expect(w.text()).toContain('待对账');await button(w,'查询该操作收据').trigger('click');await flushPromises();expect(w.text()).not.toContain('上次保存结果待对账');expect(posts()).toHaveLength(1);expect(w.text()).toContain('已持久化版本 1');w.unmount()
})
it('successful POST followed by failed history read retains operation until reconciliation',async()=>{
 const w=create();await login(w);await draw(w);mode='history-failure';await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('待对账');expect(sessionStorage.length).toBe(1)
 mode='normal';await button(w,'查询该操作收据').trigger('click');await flushPromises();expect(sessionStorage.length).toBe(0);expect(w.text()).toContain('已持久化版本 1');expect(fetchMock.mock.calls.filter((x:any)=>x[1]?.method==='POST'&&x[0].endsWith('/annotations'))).toHaveLength(1);w.unmount()
})
it('timeout releases busy state while keeping unknown save blocked for explicit reconciliation',async()=>{
 const w=create();await login(w);await draw(w);mode='timeout';await button(w,'保存新版本').trigger('click');await flushPromises();expect(w.text()).toContain('TimeoutError');expect(button(w,'查询该操作收据').attributes('disabled')).toBeUndefined();expect(button(w,'保存新版本').attributes('disabled')).toBeDefined();expect(sessionStorage.length).toBe(1);w.unmount()
})
