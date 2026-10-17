<template>
 <div>
  <div class="view-controls"><button @click="setMode('polygon')" :disabled="!ready">多边形 / 编辑顶点</button><button @click="setMode('pan')" :disabled="!ready">平移</button><button @click="zoom(1.25)" :disabled="!ready">放大</button><button @click="zoom(.8)" :disabled="!ready">缩小</button><button @click="reset" :disabled="!ready">重置视图</button><span>{{ mode==='polygon'?'逐点单击，点击起点闭合；拖动顶点编辑':'拖动平移' }}</span></div>
  <div ref="element" class="viewport" aria-label="棋盘测试影像（非真实CT）多边形标注查看器" @contextmenu.prevent></div>
  <p role="status">{{ ready?'棋盘测试影像（非真实CT）已加载 · 原生像素中心坐标 · '+mode:'正在加载棋盘测试影像 DICOM（非真实CT）…' }}</p><p v-if="error" role="alert">{{ error }}</p>
 </div>
</template>
<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref,watch} from 'vue'
import {nativeToWorld,worldToNative,type Geometry,type Point,type Revision} from './contract'
import {imaging} from './imaging'
const props=defineProps<{file:File;geometry:Geometry;revision:Revision|null;resetKey:number;ctSha:string}>()
const emit=defineEmits<{changed:[id:string,vertices:Point[]];ready:[]}>()
const element=ref<HTMLDivElement>();const ready=ref(false);const error=ref('');const mode=ref('polygon')
let viewport:any,engine:any,group:any,core:any,tools:any,dicom:any,imageId='',fileIndex=0,groupId='',viewportId='',disposed=false
let observer:ResizeObserver|undefined
const owned=new Set<string>()
function clear(){for(const id of owned)tools?.annotation.state.removeAnnotation(id);owned.clear()}
function hydrate(){
 if(!ready.value)return
 clear();error.value=''
 const r=props.revision
 if(r&&r.state==='ACTIVE'){
  tools.SplineROITool.hydrate(viewportId,r.vertices.map(p=>nativeToWorld(p,props.geometry)),{annotationUID:r.annotation_id,splineType:tools.SplineROITool.SplineTypes.Linear,toolInstance:group.getToolInstance(tools.SplineROITool.toolName),referencedImageId:imageId})
  owned.add(r.annotation_id)
 }
 viewport.render();setMode('polygon')
}
function setMode(value:string){
 if(!group)return
 mode.value=value;tools.cancelActiveManipulations(element.value)
 group.setToolPassive(tools.SplineROITool.toolName,{removeAllBindings:true});group.setToolPassive(tools.PanTool.toolName,{removeAllBindings:true})
 group.setToolActive(value==='polygon'?tools.SplineROITool.toolName:tools.PanTool.toolName,{bindings:[{mouseButton:tools.Enums.MouseBindings.Primary}]})
}
function zoom(factor:number){viewport?.setZoom(Math.min(8,Math.max(.25,viewport.getZoom()*factor)));viewport?.render()}
function reset(){viewport?.resetCamera();viewport?.render()}
function changed(event:Event){
 const a=(event as CustomEvent).detail?.annotation
 if(!a||a.metadata?.referencedImageId!==imageId||a.metadata?.toolName!==tools.SplineROITool.toolName)return
 if(!a.annotationUID||!a.data?.contour?.closed)return
 try{
  const vertices=a.data.handles.points.map((p:number[])=>worldToNative(p,props.geometry))
  for(const id of owned)if(id!==a.annotationUID){tools.annotation.state.removeAnnotation(id);owned.delete(id)}
  owned.add(a.annotationUID);emit('changed',a.annotationUID,vertices);error.value=''
 }catch(e){error.value=String(e)}
}
watch([()=>props.revision,()=>props.resetKey],hydrate)
onMounted(async()=>{
 try{
  const bytes=await props.file.arrayBuffer();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('')
  if(hash!==props.ctSha)throw Error('测试 DICOM 字节 SHA 不匹配，禁止标注')
  ;({core,dicom,tools}=await imaging())
  if(disposed)return
  imageId=dicom.wadouri.fileManager.add(props.file);fileIndex=Number(imageId.split(':')[1])
  engine=new core.RenderingEngine('annotation-engine-'+crypto.randomUUID());viewportId='annotation-view-'+crypto.randomUUID()
  engine.enableElement({viewportId,type:core.Enums.ViewportType.STACK,element:element.value})
  viewport=core.getEnabledElement(element.value).viewport
  await viewport.setStack([imageId]);if(disposed){engine?.destroy();return}
  const image=viewport.getImageData();const g=props.geometry
  if(image.dimensions[0]!==g.width||image.dimensions[1]!==g.height)throw Error('原生影像尺寸不匹配')
  for(const [x,y] of [[0,0],[g.width-1,0],[0,g.height-1]]){
   const actual=image.imageData.indexToWorld([x,y,0]);const expected=nativeToWorld([x!,y!],g)
   if(actual.some((v:number,i:number)=>Math.abs(v-expected[i]!)>1e-3))throw Error('Cornerstone 原生坐标映射不匹配')
  }
  groupId='annotation-tools-'+crypto.randomUUID();group=tools.ToolGroupManager.createToolGroup(groupId)
  group.addTool(tools.SplineROITool.toolName,{calculateStats:false,spline:{type:tools.SplineROITool.SplineTypes.Linear},allowOpenSplines:false})
  group.addTool(tools.PanTool.toolName);group.addViewport(viewportId,engine.id)
  core.eventTarget.addEventListener(tools.Enums.Events.ANNOTATION_COMPLETED,changed);core.eventTarget.addEventListener(tools.Enums.Events.ANNOTATION_MODIFIED,changed)
  observer=new ResizeObserver(()=>engine?.resize());observer.observe(element.value!)
  viewport.render();ready.value=true;hydrate();emit('ready')
 }catch(e){error.value=String(e);ready.value=false}
})
onBeforeUnmount(()=>{
 disposed=true;observer?.disconnect()
 if(tools&&core){core.eventTarget.removeEventListener(tools.Enums.Events.ANNOTATION_COMPLETED,changed);core.eventTarget.removeEventListener(tools.Enums.Events.ANNOTATION_MODIFIED,changed);clear();tools.ToolGroupManager.destroyToolGroup(groupId)}
 engine?.destroy()
 if(imageId){if(core.cache.getImageLoadObject(imageId))core.cache.removeImageLoadObject(imageId,{force:true});dicom.wadouri.fileManager.remove(fileIndex)}
})
</script>
