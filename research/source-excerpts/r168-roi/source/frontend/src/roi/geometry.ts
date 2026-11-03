/** Native image edges, not screen/device pixels. No patient-world assertion. */
export type Vertex = [number, number]
export const ROI_GEOMETRY_VERSION = 'RAW_PIXEL_EDGE_V1'
export const MAX_VERTICES = 256
const EPS = 1e-8
const cross = (a: Vertex,b: Vertex,c: Vertex) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
const on = (a:Vertex,b:Vertex,c:Vertex) => Math.abs(cross(a,b,c))<=EPS && c[0]>=Math.min(a[0],b[0])-EPS && c[0]<=Math.max(a[0],b[0])+EPS && c[1]>=Math.min(a[1],b[1])-EPS && c[1]<=Math.max(a[1],b[1])+EPS
function intersects(a:Vertex,b:Vertex,c:Vertex,d:Vertex) {
 const x=cross(a,b,c),y=cross(a,b,d),z=cross(c,d,a),w=cross(c,d,b)
 return ((x>EPS&&y< -EPS||x< -EPS&&y>EPS)&&(z>EPS&&w< -EPS||z< -EPS&&w>EPS)) || on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b)
}
export function polygonError(points: Vertex[],width:number,height:number,closed=true):string|null {
 if(!closed)return '请先完成闭合轮廓。'
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<=0||height<=0)return '原生图像尺寸未验证。'
 if(!Array.isArray(points)||points.length<3||points.length>MAX_VERTICES)return '多边形需要 3–256 个顶点。'
 if(points.some(p=>!Array.isArray(p)||p.length!==2||p.some(n=>typeof n!=='number'||!Number.isFinite(n))||p[0]<0||p[0]>width||p[1]<0||p[1]>height))return '顶点必须是图内有限原生像素坐标。'
 for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++)if(Math.hypot(points[i]![0]-points[j]![0],points[i]![1]-points[j]![1])<=EPS)return '不能使用重复顶点或退化边。'
 let area=0
 for(let i=0;i<points.length;i++) {
  const a=points[i]!,b=points[(i+1)%points.length]!;area+=a[0]*b[1]-a[1]*b[0]
  for(let j=i+1;j<points.length;j++) {
   if(j===i+1||i===0&&j===points.length-1)continue
   if(intersects(a,b,points[j]!,points[(j+1)%points.length]!))return '多边形不能自交或接触非相邻边。'
  }
 }
 if(Math.abs(area)<=EPS)return '多边形顶点不能共线。'
 // Adjacent collinear backtracking overlaps even though those edges share a vertex.
 for(let i=0;i<points.length;i++) {
  const a=points[(i+points.length-1)%points.length]!,b=points[i]!,c=points[(i+1)%points.length]!
  if(Math.abs(cross(a,b,c))<=EPS&&(a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>EPS)return '相邻边不能折返重叠。'
 }
 return null
}
export interface Matrix {a:number;b:number;c:number;d:number;e:number;f:number}
/** getScreenCTM maps SVG user units to CSS viewport pixels, including letterbox.
 * DPR never enters either side of this inverse. Out-of-image points are rejected.
 */
export function cssToNative(x:number,y:number,m:Matrix|null,width:number,height:number):Vertex|null {
 if(!m||![x,y,...Object.values(m)].every(Number.isFinite))return null
 const det=m.a*m.d-m.b*m.c
 if(!Number.isFinite(det)||Math.abs(det)<1e-12)return null
 const dx=x-m.e,dy=y-m.f,p:Vertex=[(m.d*dx-m.c*dy)/det,(m.a*dy-m.b*dx)/det]
 return p.every(Number.isFinite)&&p[0]>=0&&p[0]<=width&&p[1]>=0&&p[1]<=height?p:null
}
