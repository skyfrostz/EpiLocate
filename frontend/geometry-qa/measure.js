// Use with playwright-cli run-code --filename after opening geometry-qa/smoke.html.
async (page) => await page.evaluate(() => {
  const core = window.__geometryFixture.cornerstone
  const viewport = core.getRenderingEngines()[0].getViewport('single-slice')
  const renderedImage = viewport.getImageData().imageData
  const canvas = document.querySelector('.cornerstone-overlay')
  const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data
  const ratio = window.devicePixelRatio || 1
  const markers = [[4, 4], [220, 4], [4, 220], [220, 220], [112, 112]]
  const measured = markers.map(([rasterX, rasterY]) => {
    const raw = [rasterX * 112 / 224, rasterY * 80 / 224]
    const world = renderedImage.indexToWorld([raw[0] - 0.5, raw[1] - 0.5, 0])
    const [x, y] = viewport.worldToCanvas(world)
    const radius = 18 * ratio
    let sumX = 0, sumY = 0, count = 0
    for (let py = Math.max(0, Math.floor(y * ratio - radius)); py < Math.min(canvas.height, Math.ceil(y * ratio + radius)); py++) {
      for (let px = Math.max(0, Math.floor(x * ratio - radius)); px < Math.min(canvas.width, Math.ceil(x * ratio + radius)); px++) {
        const offset = 4 * (py * canvas.width + px)
        if (pixels[offset] > 150 && pixels[offset + 1] < 30 && pixels[offset + 2] < 30 && pixels[offset + 3] > 50) {
          sumX += (px + 0.5) / ratio
          sumY += (py + 0.5) / ratio
          count++
        }
      }
    }
    const observed = count ? [sumX / count, sumY / count] : null
    return { raw, expected: [x, y], observed, samples: count,
      errorCssPx: observed ? Math.hypot(observed[0] - x, observed[1] - y) : null }
  })
  return { width: canvas.width, height: canvas.height, zoom: viewport.getZoom(),
    pan: viewport.getPan(), markers: measured,
    maxErrorCssPx: Math.max(...measured.map(point => point.errorCssPx ?? Infinity)) }
})
