import { describe, expect, it } from 'vitest'
import { cssToNative, polygonError } from './geometry'
describe('RAW_PIXEL_EDGE ROI geometry',()=>{
 it('inverts CSS affine with letterbox and ignores DPR',()=>{const m={a:2,b:0,c:0,d:3,e:10,f:20};expect(cssToNative(14,26,m,100,100)).toEqual([2,2]);expect(cssToNative(214,326,m,100,100)).toEqual([102,102])})
 it('rejects invalid polygons and accepts finite nondegenerate closed ones',()=>{expect(polygonError([[0,0],[10,0],[10,10]],100,100)).toBeNull();expect(polygonError([[0,0],[10,10],[0,10],[10,0]],100,100)).toContain('自交');expect(polygonError([[0,0],[1,1],[2,2]],100,100)).toContain('共线');expect(polygonError([[0,0],[10,0]],100,100)).toContain('3')})
})
