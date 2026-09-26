import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient, type ApiClient } from '../api/client'
import type { HeatmapLayer, ResultRecord } from '../api/types'
import { errorText } from './cases'

export const useResultStore = defineStore('results', () => {
  const current = ref<ResultRecord | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const assetUrl = ref<string | null>(null)
  const assetLoading = ref(false)
  const assetError = ref<string | null>(null)
  let generation = 0
  let resultGeneration = 0

  function clearAsset() {
    generation++
    if (assetUrl.value) URL.revokeObjectURL(assetUrl.value)
    assetUrl.value = null
    assetLoading.value = false
    assetError.value = null
  }

  async function loadResult(resultId: string, client: ApiClient = apiClient) {
    const ownResultGeneration = ++resultGeneration
    clearAsset()
    current.value = null
    loading.value = true
    error.value = null
    try {
      const result = await client.getResult(resultId)
      if (ownResultGeneration !== resultGeneration) return
      if (result.result_id !== resultId || result.status !== 'COMPLETED' ||
          result.source !== 'LIVE_CASE' || result.contract_version !== '2.0') {
        throw new Error('结果来源或版本未通过校验。')
      }
      current.value = result
    } catch (cause) {
      if (ownResultGeneration === resultGeneration) error.value = errorText(cause)
    } finally {
      if (ownResultGeneration === resultGeneration) loading.value = false
    }
  }

  async function loadAsset(layer: HeatmapLayer | null, client: ApiClient = apiClient) {
    clearAsset()
    if (!layer || !current.value) return
    const result = current.value
    const descriptor = result.assets.find(asset => asset.asset_id === layer.asset_id)
    if (!descriptor || descriptor.layer_kind !== layer.layer_kind ||
        descriptor.coordinate_space !== layer.coordinate_space ||
        descriptor.width !== layer.width || descriptor.height !== layer.height ||
        descriptor.media_type !== 'image/png') {
      assetError.value = '图层元数据与当前结果不一致，无法显示。'
      return
    }
    const ownGeneration = generation
    assetLoading.value = true
    try {
      const blob = await client.getResultAsset(result.result_id, layer.asset_id)
      if (ownGeneration !== generation) return
      assetUrl.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (ownGeneration === generation) assetError.value = errorText(cause)
    } finally {
      if (ownGeneration === generation) assetLoading.value = false
    }
  }

  function clear() {
    resultGeneration++
    clearAsset()
    current.value = null
    loading.value = false
    error.value = null
  }

  return { current, loading, error, assetUrl, assetLoading, assetError, loadResult, loadAsset, clearAsset, clear }
})
