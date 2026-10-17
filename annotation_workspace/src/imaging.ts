// One initialization per application lifetime, including logout/login remounts.
let initialization: Promise<any> | undefined
export function imaging() {
 return initialization ??= (async()=>{
  const [core,dicom,tools]=await Promise.all([import('@cornerstonejs/core'),import('@cornerstonejs/dicom-image-loader'),import('@cornerstonejs/tools')])
  await core.init();dicom.init({maxWebWorkers:1});await tools.init()
  tools.addTool(tools.SplineROITool);tools.addTool(tools.PanTool)
  return {core,dicom,tools}
 })()
}
