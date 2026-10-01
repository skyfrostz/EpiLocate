import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'

const mocks = vi.hoisted(() => ({ setStack: vi.fn(), destroy: vi.fn(), remove: vi.fn() }))
vi.mock('@cornerstonejs/core', () => ({
  init: vi.fn(),
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
  wadouri: { fileManager: { add: () => 'dicomfile:0', remove: mocks.remove } },
}))
const props = { file: null, sliceId: 'slice_test', sliceWidth: 112, sliceHeight: 80 } as const
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.clearAllMocks()
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
})
