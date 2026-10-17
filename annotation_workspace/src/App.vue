<template>
<main>
 <header><h1>EpiLocate · 医生标注工作区</h1><p><strong>棋盘测试影像（非真实CT）</strong> · 用于标注与坐标验证 · 不运行 AI · 不自动形成训练 GT</p></header>
 <form v-if="!authenticated" @submit.prevent="login" class="login"><h2>本机合成账号登录</h2><label>账号<input v-model="username" autocomplete="username" required></label><label>密码<input v-model="password" autocomplete="current-password" type="password" required></label><button :disabled="busy">登录</button></form>
 <template v-else>
  <nav><span>已登录：{{ actor }}</span><button @click="logout" :disabled="busy">退出登录</button><button @click="reload" :disabled="busy">重新载入已保存标注</button></nav>
  <p v-if="context">病例 {{ context.binding.case_id }} · {{ context.binding.geometry.width }}×{{ context.binding.geometry.height }} · 棋盘测试影像（非真实CT）</p>
  <div class="layout" v-if="file&&context">
   <section>
    <PolygonViewport :file="file" :geometry="context.binding.geometry" :ct-sha="context.binding.ct_sha256" :revision="selected" :reset-key="resetKey" @ready="viewerReady=true" @changed="changed" />
    <div class="actions"><button @click="fresh" :disabled="busy||!!pending">新建多边形</button><label>类别<select v-model="category" @change="dirty=true"><option value="SUSPECTED_INFECTION">疑似感染（未审核）</option><option value="OTHER">其他</option></select></label><label>备注<input v-model="note" maxlength="1000" @input="dirty=true"></label><button @click="save('ACTIVE')" :disabled="busy||!dirty||!viewerReady||!!pending||!valid">保存新版本</button><button @click="save('WITHDRAWN')" :disabled="busy||!selected||selected.state==='WITHDRAWN'||dirty||!!pending">撤回当前标注</button><button v-if="selected?.state==='WITHDRAWN'" @click="restore" :disabled="busy||!!pending">恢复为新版本</button></div>
    <p role="status">{{ dirty?'未保存更改':'当前无未保存更改' }} · 顶点 {{ vertices.length }} · {{ selected?'版本 '+selected.version:'新标注' }}</p>
    <p v-if="vertices.length&&!valid" role="alert">顶点须有限且位于原生影像内；保存时服务端还将检查自交和退化。</p>
    <details v-if="vertices.length"><summary>核对原生像素中心 / LPS 坐标</summary><table><thead><tr><th>顶点</th><th>原生 x,y</th><th>LPS mm</th></tr></thead><tbody><tr v-for="(point,i) in vertices" :key="i"><td>{{ i }}</td><td>{{ point.map(x=>x.toFixed(3)).join(', ') }}</td><td>{{ nativeToWorld(point,context.binding.geometry).map(x=>x.toFixed(3)).join(', ') }}</td></tr></tbody></table></details>
   </section>
   <aside><h2>已保存标注（含撤回）</h2><p v-if="!rows.length">尚无已保存标注</p><button v-for="row in rows" :key="row.annotation_id" class="record" @click="choose(row)" :disabled="busy||!!pending">{{ row.annotation_id.slice(0,8) }} · v{{ row.version }} · {{ row.state==='WITHDRAWN'?'已撤回':'有效' }}<br>{{ row.author }} · {{ row.category }}</button><h2>不可变修订与操作记录</h2><ol><li v-for="event in history" :key="event.revision_id">v{{ event.version }} {{ event.action }}<br>{{ event.actor }}<br>{{ event.time }}</li></ol><p>审核状态：UNREVIEWED。保存者由服务端认证确定；删除使用撤回新版本，保留历史。</p></aside>
  </div>
  <div v-if="pending" role="alert">上次保存结果待对账；不会自动重复提交。<button @click="reconcile" :disabled="busy">查询该操作收据</button></div>
 </template>
 <p v-if="message" role="status" class="message">{{ message }}</p><p v-if="error" role="alert" class="error">{{ error }}</p>
</main>
</template>
<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import PolygonViewport from './PolygonViewport.vue'
import {api,setCsrf,ApiError,bindingOnly,finiteInBounds,nativeToWorld,REQUEST_TIMEOUT_MS,type Binding,type Geometry,type Point,type Revision} from './contract'
const authenticated=ref(false),username=ref(''),password=ref(''),actor=ref(''),error=ref(''),message=ref(''),busy=ref(false),viewerReady=ref(false)
const context=ref<{binding:Binding&{geometry:Geometry};actor:string}|null>(null),file=ref<File|null>(null),rows=ref<Revision[]>([]),selected=ref<Revision|null>(null),vertices=ref<Point[]>([]),history=ref<any[]>([]),dirty=ref(false),resetKey=ref(0)
const category=ref('SUSPECTED_INFECTION'),note=ref(''),annotationId=ref<string>(crypto.randomUUID()),pending=ref<any>(null)
const caseId='GENERATED_ANNOTATION_CASE',root='/api/v2/cases/'+caseId,path=root+'/annotations'
const pendingKey=()=>`epilocate.annotation.pending.${actor.value}.${caseId}`
const valid=computed(()=>!!context.value&&finiteInBounds(vertices.value,context.value.binding.geometry))
async function run(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';message.value='';try{await action()}catch(e){error.value=e instanceof ApiError?`${e.status} · ${e.code}（未自动重试）`:String(e)}finally{busy.value=false}}
async function loadRows(){rows.value=(await api(path)).items}
async function showHistory(){history.value=selected.value?(await api(path+'/'+selected.value.annotation_id+'/history')).events:[]}
async function load(){
 context.value=await api(root+'/annotation-context');actor.value=context.value!.actor
 const response=await fetch(root+'/dicom',{credentials:'same-origin',signal:AbortSignal.timeout(REQUEST_TIMEOUT_MS)});if(!response.ok)throw new ApiError(response.status,'CT_READ_FAILED')
 file.value=new File([await response.blob()],'GENERATED_ANNOTATION_CT.dcm',{type:'application/dicom'})
 await loadRows();pending.value=JSON.parse(sessionStorage.getItem(pendingKey())??'null')
 select(rows.value.find(r=>r.state==='ACTIVE')??rows.value[0]??null);await showHistory()
}
function select(row:Revision|null){selected.value=row;annotationId.value=row?.annotation_id??crypto.randomUUID();vertices.value=row?.vertices.map(p=>[...p] as Point)??[];category.value=row?.category??'SUSPECTED_INFECTION';note.value=row?.note??'';dirty.value=false;resetKey.value++}
async function login(){await run(async()=>{const r=await api('/auth/login',{username:username.value,password:password.value});setCsrf(r.csrf_token);actor.value=r.username;password.value='';authenticated.value=true;await load()})}
async function logout(){await run(async()=>{await api('/auth/logout',{});authenticated.value=false;file.value=null;context.value=null;selected.value=null;rows.value=[];setCsrf('')})}
function discard(){return !dirty.value||window.confirm('放弃当前未保存更改并读取服务器版本？')}
async function reload(){if(!discard()||pending.value)return;await run(async()=>{const id=selected.value?.annotation_id;await loadRows();select(rows.value.find(r=>r.annotation_id===id)??null);await showHistory();message.value='已从数据库重新读取'})}
async function choose(row:Revision){if(!discard())return;await run(async()=>{select(row);await showHistory()})}
function fresh(){if(discard()){select(null);history.value=[]}}
function changed(id:string,points:Point[]){annotationId.value=id;vertices.value=points;dirty.value=true;if(selected.value&&id!==selected.value.annotation_id)selected.value=null}
function clearPending(){sessionStorage.removeItem(pendingKey());pending.value=null}
async function accept(saved:Revision){await loadRows();select(rows.value.find(r=>r.annotation_id===saved.annotation_id)??saved);await showHistory();clearPending();message.value=`已持久化版本 ${saved.version}；作者 ${saved.author}`}
async function save(state:'ACTIVE'|'WITHDRAWN'){if(pending.value||!context.value)return;await run(async()=>{
 const value={annotation_id:annotationId.value,operation_id:crypto.randomUUID(),expected_version:selected.value?.version??0,binding:bindingOnly(context.value!.binding),vertices:vertices.value,category:category.value,state,note:note.value}
 pending.value=value;sessionStorage.setItem(pendingKey(),JSON.stringify(value))
 let saved:Revision
 try{saved=await api(path,value)}catch(e){if(e instanceof ApiError&&e.status<500){clearPending();if(e.status===409){error.value='409 版本或身份冲突；请重新载入服务器版本，不会覆盖他人更改';return}else throw e}else throw e}
 await accept(saved)
})}
async function restore(){if(selected.value){vertices.value=selected.value.vertices.map(p=>[...p] as Point);await save('ACTIVE')}}
async function reconcile(){if(!pending.value)return;await run(async()=>{const r=await api(root+'/annotation-operations/'+pending.value.operation_id);await accept(r)})}
onMounted(()=>run(async()=>{try{const r=await api('/auth/session');setCsrf(r.csrf_token);actor.value=r.username;authenticated.value=true;await load()}catch(e){if(e instanceof ApiError&&e.status===401){authenticated.value=false;return}throw e}}))
</script>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#203247;font:15px/1.6 system-ui}main{max-width:1460px;margin:auto;padding:24px}header{border-bottom:1px solid #ccd5df;margin-bottom:18px}h1{font-size:25px}h2{font-size:18px}header p{color:#52667b}button,input,select{font:inherit;padding:7px 12px;border:1px solid #9eadbe;border-radius:5px;background:white;color:inherit}button{cursor:pointer}button:hover:not(:disabled){background:#e6eef8}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #3477c4;outline-offset:2px}label{display:inline-flex;gap:6px;align-items:center}.login{display:grid;gap:14px;max-width:380px}.login label{justify-content:space-between}nav,.actions,.view-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}.layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px}.viewport{height:520px;position:relative;background:#111b26;touch-action:none}.viewport canvas{position:absolute;inset:0}aside{border-left:1px solid #ccd5df;padding-left:20px}.record{display:block;width:100%;text-align:left;margin:8px 0}.error{color:#8c2020;background:#fff1f1;padding:12px}.message{color:#185233;background:#e5f6ed;padding:12px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #b9c6d4;padding:6px;text-align:left}ol{padding-left:22px;font-size:13px;overflow-wrap:anywhere}@media(max-width:900px){.layout{grid-template-columns:1fr}.viewport{height:420px}aside{border-left:0}}
</style>
