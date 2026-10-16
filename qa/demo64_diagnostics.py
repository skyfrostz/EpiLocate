"""Metadata-only diagnostics on failure; unchanged joint readiness/deadline."""
from qa.demo64_readiness import wait_ready as original_wait_ready


def wait_ready(page,expected,timeout_ms=15000,*,log=None):
    try:return original_wait_ready(page,expected,timeout_ms)
    except BaseException:
        if log is not None:
            try:
                details=page.evaluate('''async expected=>{
                  let element=document.querySelector('.cornerstone-viewport');const ancestors=[];
                  for(let i=0;element&&i<12;i++,element=element.parentElement){const s=getComputedStyle(element);
                    ancestors.push({tag:element.tagName,width:element.clientWidth,height:element.clientHeight,display:s.display,visibility:s.visibility,opacity:s.opacity})}
                  let engines=[];let moduleAvailable=false;
                  try{const m=await Promise.race([import(expected.coreUrl),new Promise((_,reject)=>setTimeout(()=>reject(new Error('diagnostic timeout')),1000))]);const c=m.getRenderingEngines?m:m.t;moduleAvailable=true;
                    engines=c.getRenderingEngines().map(e=>({viewports:e.getViewports().map(v=>{
                      const image=v.getCornerstoneImage();return {status:v.viewportStatus,currentImagePresent:!!v.getCurrentImageId(),columns:image?.columns,rows:image?.rows}})}))}catch{}
                  return {ancestors,moduleAvailable,engines,visibleErrorCount:[...document.querySelectorAll('.notice-error')].filter(e=>e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})).length};
                }''',expected)
                log.step('readiness_failure_diagnostics',status='FAIL',details=details)
            except BaseException as diagnostic:
                log.step('diagnostic_unavailable',status='FAIL',error_type=type(diagnostic).__name__)
        raise
