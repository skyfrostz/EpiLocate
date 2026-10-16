import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ResearchEvidence from '../components/ResearchEvidence.vue'
import type { ApplicationRequest, ApplicationResult } from '../api/next-algorithm'
const request={task:{class_labels:['normal-source','infection-source'],target_class:0}} as ApplicationRequest
function output(): ApplicationResult { return {prediction:{logits:[-1,1],predicted_class:1,class_label:'infection-source',probabilities:null},diagnostics:{}} as ApplicationResult }
function f0() {return {schema:'EPI_NEXT_F0_CONSUMPTION_V1',explanation_target:0,predicted_class:1,raw_logits:[-1,1],effective_bias:[-1,1],signed_values:Array.from({length:2},()=>Array.from({length:4},()=>Array.from({length:4},()=>[-1,1,0,0]))),source_label:{scope:'SOURCE_GROUP',label:'Normal source'}}}
describe('R76 research evidence only',()=>{
 it('keeps signed grid and bias identity on remount without a model or asset request',async()=>{
  const o=output();o.diagnostics.f0=f0();const props={resultId:'result_generated',request,output:o};const w=mount(ResearchEvidence,{props})
  expect(w.text()).toContain('空间均值 0 + 有效 bias -1 = logit -1')
  expect(w.findAll('td')).toHaveLength(16);expect(w.find('td.negative').text()).toBe('-1.0000')
  await w.find('select').setValue('3');expect(w.find('select').element.value).toBe('3');expect(sessionStorage.getItem('epilocate:next-result:result_generated:research-slice')).toBe('3');expect(w.findAll('td')).toHaveLength(16);w.unmount()
  const fresh=mount(ResearchEvidence,{props});await nextTick();expect(fresh.text()).toContain('SOURCE_GROUP');expect(fresh.find('select').element.value).toBe('3');fresh.unmount()
 })
 it('refuses a broken signed-map identity and removes the coarse map',()=>{
  const o=output(),f=f0();f.effective_bias[0]=99;o.diagnostics.f0=f
  const w=mount(ResearchEvidence,{props:{resultId:'result_generated',request,output:o}});expect(w.text()).toContain('恒等式不一致');expect(w.find('table').exists()).toBe(false)
 })
 it('keeps explanation0, prediction1 and CASE label scope separate',()=>{
  const o=output();o.diagnostics.target_contract={contract_sha256:'d852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c',prediction_scope:'SLICE',predicted_class:1,class_labels:request.task.class_labels,explanation_target:{policy:'DECLARED_FIXED',declared_class:0,resolved_class:0},source_label:{label:'case-source',scope:'CASE'},loss_definition:{optimization_objective:'ALL_LOGITS',response_metric:'FIXED_TARGET_LOGIT_MARGIN'}}
  const w=mount(ResearchEvidence,{props:{resultId:'result_generated',request,output:o}});expect(w.text()).toContain('解释类别：normal-source');expect(w.text()).toContain('预测类别：infection-source');expect(w.text()).toContain('范围 CASE');expect(w.text()).toContain('不代表切片或病灶真值')
  const t=o.diagnostics.target_contract as {explanation_target:{resolved_class:number}};t.explanation_target.resolved_class=1
  const bad=mount(ResearchEvidence,{props:{resultId:'result_generated',request,output:o}});expect(bad.text()).toContain('契约不一致')
 })
})
