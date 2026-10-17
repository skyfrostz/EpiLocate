import {describe,it,expect,vi,afterEach} from 'vitest'
import {nativeToWorld,worldToNative,finiteInBounds,bindingOnly,api,setCsrf,ApiError,type Geometry} from './contract'
const g:Geometry={width:112,height:80,ipp:[12,34,56],iop:[0,1,0,-1,0,0],spacing:[.7,1.2]}
afterEach(()=>vi.unstubAllGlobals())
describe('authoritative native centre coordinates',()=>{
 it('uses asymmetric row/column spacing and LPS orientation without half-pixel shift',()=>{
  expect(nativeToWorld([10,10],g)).toEqual([5,46,56])
  for(const p of [[0,0],[111,79],[17.25,48.5]] as [number,number][]){const q=worldToNative(nativeToWorld(p,g),g);expect(q[0]).toBeCloseTo(p[0],10);expect(q[1]).toBeCloseTo(p[1],10)}
 })
 it('rejects nonfinite, off-plane and out-of-bounds points',()=>{
  expect(()=>worldToNative([NaN,0,0],g)).toThrow();expect(()=>worldToNative([12,34,57],g)).toThrow()
  expect(finiteInBounds([[0,0],[111,0],[0,79]],g)).toBe(true)
  expect(finiteInBounds([[0,0],[112,0],[0,79]],g)).toBe(false)
  expect(finiteInBounds([[0,0],[1,Infinity],[0,79]],g)).toBe(false)
 })
 it('strips server geometry from exact client binding',()=>{
  expect(bindingOnly({geometry:g,case_id:'generated'} as any)).toEqual({case_id:'generated'})
 })
})
it('posts with same-origin cookie and in-memory CSRF, never a browser bearer',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response('{}',{status:200}));vi.stubGlobal('fetch',fetch);setCsrf('test-csrf');await api('/api/v2/cases/generated/annotations',{expected_version:2})
 const options=fetch.mock.calls[0]![1];expect(options.credentials).toBe('same-origin');expect(options.headers['x-csrf-token']).toBe('test-csrf');expect(options.headers.Authorization).toBeUndefined()
})
it('does not automatically retry a conflict or ambiguous transport error',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response('{"code":"VERSION_CONFLICT"}',{status:409}));vi.stubGlobal('fetch',fetch)
 await expect(api('/api/v2/cases/generated/annotations',{})).rejects.toMatchObject({status:409,code:'VERSION_CONFLICT'});expect(fetch).toHaveBeenCalledTimes(1)
 fetch.mockRejectedValueOnce(new TypeError('network'));await expect(api('/api/v2/cases/generated/annotations',{})).rejects.toThrow('network');expect(fetch).toHaveBeenCalledTimes(2)
})
