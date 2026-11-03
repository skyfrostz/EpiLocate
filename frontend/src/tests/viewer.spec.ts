import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'

const mocks = vi.hoisted(() => ({
  setStack: vi.fn(), destroy: vi.fn(), remove: vi.fn(), removeImage: vi.fn(), unload: vi.fn(), clearMetadata: vi.fn(),
  images: new Map<string, { promise: Promise<void>; decache?: () => void }>(), datasets: new Set<string>(), nextId: 0,
  naturalized: new Map<string, unknown>(),
}))
vi.mock('@cornerstonejs/core', () => ({
  init: vi.fn(),
  cache: { getImageLoadObject: (id: string) => mocks.images.get(id), removeImageLoadObject: mocks.removeImage },
  Enums: { ViewportType: { STACK: 'stack' }, Events: { CAMERA_MODIFIED: 'camera', IMAGE_RENDERED: 'render' } },
  RenderingEngine: class {
    enableElement() {}
    resize() {}
    destroy = mocks.destroy
    getViewport() { return { setStack: mocks.setStack, getCornerstoneImage: () => ({ columns: 112, rows: 80 }),
      render: vi.fn(), getZoom: () => 1, getPan: () => [0, 0] } }
  },
}))
vi.mock('@cornerstonejs/dicom-image-loader', () => ({ init: vi.fn(),
  wadouri: { fileManager: { add: () => `dicomfile:${mocks.nextId++}`, remove: mocks.remove },
    dataSetCacheManager: { isLoaded: (uri: string) => mocks.datasets.has(uri), unload: mocks.unload } },
}))
vi.mock('@cornerstonejs/metadata', () => ({
  metaData: { clearQuery: mocks.clearMetadata }, Enums: { MetadataModules: { NATURALIZED: 'naturalized' } },
}))
const props = { file: null, sliceId: 'slice_test', sliceWidth: 112, sliceHeight: 80 } as const
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.clearAllMocks()
  mocks.images.clear()
  mocks.datasets.clear()
  mocks.naturalized.clear()
  mocks.nextId = 0
  mocks.setStack.mockReset().mockResolvedValue(undefined)
  mocks.unload.mockImplementation((uri: string) => { mocks.datasets.delete(uri) })
  mocks.removeImage.mockImplementation((id: string) => {
    mocks.images.get(id)?.decache?.()
    mocks.images.delete(id)
  })
  mocks.clearMetadata.mockImplementation((_type: string, id: string) => { mocks.naturalized.delete(id) })
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ setTransform: vi.fn(), clearRect: vi.fn() } as unknown as CanvasRenderingContext2D)
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('single-slice viewer recovery', () => {
  it('distinguishes loading, expiration and retryable input failures', async () => {
    const wrapper = mount(CornerstoneSliceViewer, { props: { ...props, inputState: 'loading' } })
    wrappers.push(wrapper)
    expect(wrapper.text()).toContain('正在读取原始 DICOM')
    expect(wrapper.text()).not.toContain('失败')
    await wrapper.setProps({ inputState: 'expired', inputMessage: '请重新上传病例。' })
    expect(wrapper.text()).toContain('原始影像已过期')
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({ inputState: 'error' })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('clears decoding state and destroys the renderer when the file disappears mid-decode', async () => {
    let resolve!: () => void
    mocks.setStack.mockReturnValue(new Promise<void>(done => { resolve = done }))
    const wrapper = mount(CornerstoneSliceViewer, { props: { ...props, file: new File(['dicom'], 'slice.dcm') } })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain('正在解码 DICOM')
    await wrapper.setProps({ file: null })
    resolve()
    await flushPromises()
    expect(wrapper.text()).not.toContain('正在解码 DICOM')
    expect(wrapper.find('[aria-label="影像视图控制"]').exists()).toBe(false)
    expect(mocks.destroy).toHaveBeenCalledTimes(1)
    expect(mocks.remove).toHaveBeenCalledTimes(1)
  })

  it('retries a decoding timeout locally with the same authorized file', async () => {
    vi.useFakeTimers()
    mocks.setStack.mockReturnValueOnce(new Promise(() => {})).mockResolvedValueOnce(undefined)
    const wrapper = mount(CornerstoneSliceViewer, { props: { ...props, file: new File(['dicom'], 'slice.dcm') } })
    wrappers.push(wrapper)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(15000)
    expect(wrapper.text()).toContain('DICOM 解码超时')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(mocks.setStack).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[aria-label="影像视图控制"]').exists()).toBe(true)
    expect(wrapper.emitted('retry')).toBeUndefined()
  })

  it('releases its decoded image and dataset while leaving another viewer cache intact', async () => {
    mocks.images.set('dicomfile:other', { promise: Promise.resolve() })
    mocks.datasets.add('other')
    mocks.naturalized.set('dicomfile:other', { PixelData: new Uint8Array([9]) })
    mocks.setStack.mockImplementation(([id]: string[]) => {
      const uri = id!.split(':')[1]!
      mocks.datasets.add(uri)
      mocks.naturalized.set(id!, { PixelData: new Uint8Array([1]) })
      mocks.images.set(id!, { promise: Promise.resolve(), decache: () => mocks.unload(uri) })
      return Promise.resolve()
    })
    const wrapper = mount(CornerstoneSliceViewer, { props: { ...props, file: new File(['dicom'], 'slice.dcm') } })
    wrappers.push(wrapper)
    await flushPromises()
    await wrapper.setProps({ file: null })
    expect(mocks.removeImage).toHaveBeenCalledWith('dicomfile:0', { force: true })
    expect(mocks.unload).toHaveBeenCalledTimes(1)
    expect(mocks.images.has('dicomfile:0')).toBe(false)
    expect(mocks.datasets.has('0')).toBe(false)
    expect(mocks.naturalized.has('dicomfile:0')).toBe(false)
    expect(mocks.clearMetadata).toHaveBeenCalledWith('naturalized', 'dicomfile:0')
    expect(mocks.images.has('dicomfile:other')).toBe(true)
    expect(mocks.datasets.has('other')).toBe(true)
    expect(mocks.naturalized.has('dicomfile:other')).toBe(true)
  })

  it('releases a dataset that finishes after unmount before its decache hook existed', async () => {
    let resolveImage!: () => void, resolveStack!: () => void
    const imagePromise = new Promise<void>(done => { resolveImage = done })
    const stackPromise = new Promise<void>(done => { resolveStack = done })
    mocks.setStack.mockImplementation(([id]: string[]) => {
      mocks.images.set(id!, { promise: imagePromise })
      return stackPromise
    })
    const wrapper = mount(CornerstoneSliceViewer, { props: { ...props, file: new File(['dicom'], 'slice.dcm') } })
    await flushPromises()
    wrapper.unmount()
    expect(mocks.images.has('dicomfile:0')).toBe(false)
    expect(mocks.destroy).toHaveBeenCalledTimes(1)
    mocks.datasets.add('0')
    mocks.naturalized.set('dicomfile:0', { PixelData: new Uint8Array([1]) })
    resolveImage()
    await flushPromises()
    expect(mocks.datasets.has('0')).toBe(false)
    expect(mocks.naturalized.has('dicomfile:0')).toBe(false)
    expect(mocks.unload).toHaveBeenCalledWith('0')
    resolveStack()
    await flushPromises()
    expect(mocks.remove).toHaveBeenCalledTimes(1)
    expect(mocks.unload).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('camera-change')).toBeUndefined()
  })
})
