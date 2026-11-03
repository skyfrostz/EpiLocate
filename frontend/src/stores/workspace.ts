import { defineStore } from 'pinia'
import { ref } from 'vue'
import { onSessionReset } from '../auth/lifecycle'
export const useWorkspaceStore = defineStore('workspace', () => {
  const visits = ref<{caseId:string;observedAt:number}[]>([])
  function visit(caseId: string) { visits.value = [{caseId, observedAt:Date.now()}, ...visits.value.filter(v => v.caseId !== caseId)].slice(0,8) }
  onSessionReset(() => { visits.value = [] })
  return { visits, visit }
})
