// Isolated local UI acceptance: every auth/business response is intercepted.
// No request reaches a deployment, Worker, or patient-data service.
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { resolve, join, dirname } from 'node:path'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const args = Object.fromEntries(process.argv.slice(2).reduce((items, value, index, all) => value.startsWith('--') ? [...items, [value.slice(2), all[index + 1]]] : items, []))
const phase = args.phase || 'final'
const base = args.url || process.env.FRONTEND_QA_URL || 'http://127.0.0.1:5198'
const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(args.root || process.env.FRONTEND_QA_ROOT || (['/tmp', '/private/tmp'].includes(here) ? '/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai/frontend' : join(here, '..')))
const fixturePath = name => join(root, '.local', name)

assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'QA must only target a local server')
const output = resolve(args.out || process.env.FRONTEND_QA_OUTPUT || join(root, '.local', 'clinical-canvas-browser'))
await mkdir(output, { recursive: true })
const dicom = await readFile(fixturePath('geometry_synthetic_ct.dcm'))
const hash = createHash('sha256').update(dicom).digest('hex')
const caseId = 'case_synthetic_' + '0123456789'.repeat(5)
const sliceId = 'slice_synthetic'
const jobId = 'job_synthetic'
const resultId = 'result_synthetic'
const createdAt = '2026-10-01T12:00:00Z'
const browser = await chromium.launch({ channel: process.env.FRONTEND_QA_BROWSER || 'chrome', headless: true,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const evidence = { environment: 'SYNTHETIC_API_FIXTURE — local intercepted APIs, generated pixel values, actual Cornerstone rendering, no inference or deployment access', phase, scenarios: [], screenshots: [], geometry: [], pageErrors: [] }
const record = name => evidence.scenarios.push({ name, passed: true })
let activePage
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const blockedExternalRequests = []
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (['127.0.0.1', 'localhost'].includes(url.hostname) || ['blob:', 'data:'].includes(url.protocol)) return route.continue()
    blockedExternalRequests.push(url.origin + url.pathname)
    return route.abort('blockedbyclient')
  })
  evidence.blockedExternalRequests = blockedExternalRequests
  const page = await context.newPage()
  activePage = page
  page.on('pageerror', error => evidence.pageErrors.push(error.message))
  const pngs = {}
  for (const size of [224, 14]) {
    const bytes = await page.evaluate(size => {
      const canvas = document.createElement('canvas'); canvas.width = size; canvas.height = size
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ff0000'
      const marker = size === 224 ? 8 : 1
      for (const [x, y] of [[0, 0], [size - marker, 0], [0, size - marker], [size - marker, size - marker], [Math.floor(size / 2) - marker / 2, Math.floor(size / 2) - marker / 2]]) ctx.fillRect(x, y, marker, marker)
      return canvas.toDataURL('image/png').split(',')[1]
    }, size)
    pngs[size] = Buffer.from(bytes, 'base64')
  }
  let logged = false, identity = 'alice', exists = false, ready = false, polls = 0, fixtureList = false
  let dicomExpired = false, assetBroken = false, transportFailed = true, casesResponse = 'normal'
  const caseRecord = () => ({ case_id: caseId, patient_id: 'SYNTHETIC-ONLY', status: ready ? 'READY' : 'CREATED',
    created_at: createdAt, input_expires_at: '2026-10-08T12:00:00Z', studies: ready ? [{ study_id: 'study_synthetic', series: [{ series_id: 'series_synthetic',
      slices: [{ slice_id: sliceId, ordinal: 0, width_px: 112, height_px: 80 }] }] }] : [] })
  const jobRecord = (status, id = jobId) => ({ job_id: id, kind: 'OCCLUSION', case_id: caseId, status,
    attempt_no: 1, retry_count: 0, lease_expire_time: null, last_heartbeat: null, failure_reason: null,
    progress: null, estimated_remaining_time_ms: null, result_id: status === 'COMPLETED' ? resultId : null,
    error: null, created_at: createdAt, finished_at: status === 'COMPLETED' ? createdAt : null })
  function layer(scale, kind) {
    const size = kind === 'COMPARISON_GRID' ? 14 : 224
    return { asset_id: `${scale}-${kind}.png`, layer_kind: kind, width: size, height: size,
      coordinate_space: size === 14 ? 'COMPARISON_14' : 'ALGORITHM_224', value_min: 0, value_max: 1,
      origin: 'TOP_LEFT_PIXEL_EDGE', x_axis: 'RIGHT', y_axis: 'DOWN', display_interpolation_only: true }
  }
  const summaries = [16, 32, 64].map(scale => ({ block_size: scale, stride: scale / 2, fill: 0.5,
    baseline_positive_probability: 0.1, median_absolute_probability_change: 0.02, flip_rate: 0,
    candidate_status: scale === 16 ? 'insufficient_positive_response' : 'valid', candidate_area_fraction: scale === 16 ? null : 0.1,
    response_layer: layer(scale, 'CANDIDATE_RESPONSE'), candidate_layer: scale === 16 ? null : layer(scale, 'CANDIDATE_TOP10'), comparison_grid_layer: layer(scale, 'COMPARISON_GRID') }))
  const resultRecord = { result_id: resultId, job_id: jobId, case_id: caseId, slice_id: sliceId, kind: 'OCCLUSION',
    contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED', model_id: 'baseline_resnet18',
    model_version: '548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
    preprocessing_version: 'formal-resnet18-baseline-rule-b-v1', protocol_id: 'stage1-occlusion-instability-v1', created_at: createdAt,
    prediction: { predicted_class: 0, class_label: 'negative', positive_probability: 0.1, predicted_class_confidence: 0.9, inference_time_ms: 25 },
    scale_summaries: summaries, cross_scale: [], provenance: { input_sha256: hash.toUpperCase() },
    assets: summaries.flatMap(item => [item.response_layer, item.candidate_layer, item.comparison_grid_layer].filter(Boolean))
      .map(item => ({ asset_id: item.asset_id, layer_kind: item.layer_kind, width: item.width, height: item.height, coordinate_space: item.coordinate_space, media_type: 'image/png' })) }
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await context.route(base + '/auth/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/auth/session') return json(route, logged ? { username: identity, csrf_token: 'synthetic-csrf-only' } : { code: 'UNAUTHENTICATED' }, logged ? 200 : 401)
    if (path === '/auth/login') {
      const input = route.request().postDataJSON()
      if (input.password !== 'synthetic-fixture-only') return json(route, { code: 'INVALID_CREDENTIALS' }, 401)
      identity = input.username; logged = true
      return json(route, { username: identity, csrf_token: 'synthetic-csrf-only' })
    }
    if (path === '/auth/logout') { logged = false; return route.fulfill({ status: 204 }) }
    return json(route, { code: 'NOT_FOUND' }, 404)
  })
  await context.route('**/api/v2/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (!logged) return json(route, { code: 'UNAUTHENTICATED' }, 401)
    if (path === '/api/v2/cases') {
      if (request.method() === 'GET' && casesResponse === 'forbidden') return json(route, { code: 'FORBIDDEN', message: 'INTERNAL_DEBUG_SHOULD_NOT_APPEAR' }, 403)
      if (request.method() === 'GET' && casesResponse === 'offline') return route.abort('internetdisconnected')
      if (request.method() === 'POST') { exists = true; return json(route, caseRecord(), 201) }
      return json(route, { items: exists && identity === 'alice' ? (fixtureList ? [caseRecord(), ...['CREATED', 'READY', 'EXPIRED', 'READY', 'CREATED'].map((status, index) => ({ ...caseRecord(), case_id: `case_synthetic_fixture_${index + 2}`, patient_id: `SYNTHETIC-ONLY-${index + 2}`, status, created_at: `2026-10-0${index + 1}T08:30:00Z`, input_expires_at: status === 'CREATED' ? null : status === 'EXPIRED' ? '2026-10-01T12:00:00Z' : '2026-10-08T12:00:00Z' }))] : [caseRecord()]) : [], next_cursor: null })
    }
    if (path === `/api/v2/cases/${caseId}`) return json(route, caseRecord())
    if (path.endsWith('/upload')) { ready = true; return json(route, { ...caseRecord(), study_id: 'study_synthetic', series_id: 'series_synthetic', slice_id: sliceId }) }
    if (path.endsWith('/dicom')) {
      if (dicomExpired) return json(route, { code: 'INPUT_EXPIRED' }, 410)
      return route.fulfill({ contentType: 'application/dicom', body: dicom })
    }
    if (path === '/api/v2/jobs/occlusion' || path === '/api/v2/predictions') {
      polls = 0; return json(route, { job_id: jobId, case_id: caseId, status: 'CREATED', status_url: `/api/v2/jobs/${jobId}` }, 202)
    }
    if (path === '/api/v2/jobs/job_failed') return json(route, { ...jobRecord('FAILED', 'job_failed'), failure_reason: 'INFERENCE_FAILED', error: { code: 'INFERENCE_FAILED', message: 'INTERNAL_DEBUG_SHOULD_NOT_APPEAR' } })
    if (path === '/api/v2/jobs/job_transport') {
      if (polls++ > 0 && transportFailed) return json(route, { code: 'BACKEND_UNAVAILABLE' }, 503)
      return json(route, jobRecord('RUNNING', 'job_transport'))
    }
    if (path === `/api/v2/jobs/${jobId}`) return json(route, jobRecord(polls++ ? 'COMPLETED' : 'QUEUED'))
    if (path === `/api/v2/results/${resultId}`) return json(route, resultRecord)
    if (path.includes('/assets/')) {
      await new Promise(done => setTimeout(done, path.includes('16-') ? 150 : 20))
      return route.fulfill({ contentType: 'image/png', body: assetBroken ? Buffer.from('corrupt synthetic PNG') : pngs[path.includes('COMPARISON_GRID') ? 14 : 224] })
    }
    return json(route, { code: 'NOT_FOUND' }, 404)
  })
  async function screenshot(name) {
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) })
    const file = `${name}.png`; await page.screenshot({ path: join(output, file), fullPage: true, animations: 'disabled' }); evidence.screenshots.push(file)
  }
  async function noOverflow() {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Horizontal overflow at ${page.url()}`)
  }
  if (['regression', 'final'].includes(phase)) {
  await page.goto(base + '/cases')
  await page.getByLabel('账号', { exact: true }).waitFor()
  await page.getByLabel('账号', { exact: true }).focus(); await page.keyboard.press('Tab')
  assert.equal(await page.locator(':focus').getAttribute('id'), 'password')
  await screenshot('01-login-desktop')
  await page.getByLabel('账号', { exact: true }).fill('alice'); await page.getByLabel('密码', { exact: true }).fill('wrong-fixture')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: '密码不正确' }).waitFor()
  await page.getByLabel('密码', { exact: true }).fill('synthetic-fixture-only')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByText('暂无病例', { exact: true }).waitFor(); record('login, keyboard focus, invalid credentials, deep-link restore, empty cases')
  await screenshot('02-cases-empty')
  await page.goto(base + '/'); await page.getByRole('heading', { level: 1 }).first().waitFor()
  await screenshot('02-dashboard-desktop'); await page.goto(base + '/cases')
  await page.getByRole('button', { name: '创建匿名病例' }).click()
  await page.getByLabel('选择已去标识的单张 CT DICOM（最多 20 MiB）').waitFor()
  await page.locator('input[type=file]').setInputFiles(fixturePath('geometry_synthetic_ct.dcm'))
  await page.getByRole('button', { name: '上传 DICOM' }).click()
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 }); record('create case, synthetic DICOM upload, actual Cornerstone decoding')
  await page.reload(); await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 }); record('Case deep-link refresh restores authorized DICOM')
  await screenshot('03-case-desktop'); await noOverflow()
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(); await screenshot('03-case-mobile')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '运行 16 / 32 / 64 px 遮挡' }).click()
  await page.getByText('排队中', { exact: true }).first().waitFor()
  await page.getByRole('link', { name: '查看已完成结果 →' }).waitFor({ timeout: 10000 })
  await page.getByRole('link', { name: '查看已完成结果 →' }).click()
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
  await page.getByText('像素校验通过', { exact: true }).waitFor(); record('Job polling and Result navigation, uppercase SHA-256, verified geometry')
  await page.getByRole('checkbox', { name: '显示叠加' }).check()
  assert.equal(await page.locator('.result-metadata').getAttribute('open'), null)
  await page.locator('.result-metadata summary').focus()
  await page.keyboard.press('Enter')
  assert.notEqual(await page.locator('.result-metadata').getAttribute('open'), null)
  await page.keyboard.press('Enter')
  for (const width of [1440, 1100, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 1000 })
    await noOverflow()
    await screenshot(`second-round-result-${width}`)
    const bounds = await page.locator('.cornerstone-stage').boundingBox()
    assert(bounds.height >= 320 && bounds.width > 200)
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1))
  await screenshot('second-round-result-200-percent')
  await page.evaluate(() => { document.documentElement.style.zoom = '' })
  record('workspace breakpoints 1440/1100/768/390/360, enlarged layout and keyboard metadata disclosure')
  await page.getByRole('button', { name: '32 px', exact: true }).click()
  await page.getByRole('button', { name: '64 px', exact: true }).click()
  await page.getByRole('button', { name: '候选区域', exact: true }).click()
  await page.locator('.asset-caption').filter({ hasText: '候选区域' }).waitFor()
  await page.getByRole('checkbox', { name: '显示叠加' }).waitFor({ state: 'visible' })
  await page.waitForFunction(() => !document.querySelector('.fusion-controls input[type=checkbox]').disabled)
  await page.getByRole('button', { name: '放大 CT' }).click(); await screenshot('04-result-desktop'); await noOverflow()
  await page.reload(); await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
  assert(await page.getByRole('button', { name: '64 px', exact: true }).evaluate(button => button.classList.contains('active')))
  assert(await page.getByRole('checkbox', { name: '显示叠加' }).isChecked()); record('rapid scale/layer switching, zoom, Result refresh preferences')
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(); await screenshot('05-result-mobile')
  await page.getByRole('button', { name: '打开导航' }).click(); await page.getByRole('button', { name: '关闭菜单' }).click(); record('mobile result, navigation, long IDs, no horizontal overflow')
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('button', { name: '关闭菜单' }).waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.locator(':focus').getAttribute('aria-label'), '打开导航')
  record('mobile keyboard navigation Escape restores focus')
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.setViewportSize({ width: 1100, height: 900 })
  await page.waitForFunction(() => !document.querySelector('.main-area').inert)
  assert.equal(await page.getByRole('button', { name: '关闭菜单' }).count(), 0)
  record('mobile open navigation releases main content when resized to tablet')
  await page.setViewportSize({ width: 1440, height: 1000 })
  assetBroken = true; await page.getByRole('button', { name: '32 px', exact: true }).click()
  await page.getByText('响应图无法解码。', { exact: true }).waitFor()
  assetBroken = false; await page.getByRole('button', { name: '重试读取图层' }).click()
  await page.locator('.heatmap-frame img').waitFor(); record('corrupt PNG and local asset retry')
  dicomExpired = true; await page.getByRole('button', { name: '重新读取', exact: true }).click()
  await page.getByText('原始影像已过期', { exact: true }).waitFor()
  assert(await page.getByRole('checkbox', { name: '显示叠加' }).isDisabled())
  await page.locator('.heatmap-frame img').waitFor(); await screenshot('06-expired-input'); record('expired DICOM disables overlay and retains independent heatmap')
  dicomExpired = false
  await page.goto(base + '/jobs/job_failed')
  await page.getByText('任务失败：推理未完成', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes('INTERNAL_DEBUG_SHOULD_NOT_APPEAR'))
  assert.equal(await page.getByRole('link', { name: '查看已完成结果 →' }).count(), 0)
  await screenshot('07-failed-job'); record('failed Job safe guidance, preserved ID, no false Result or automatic retry')
  polls = 0; await page.goto(base + '/jobs/job_transport')
  await page.getByText('运行中', { exact: true }).first().waitFor()
  await page.getByText('保留下方最近一次查询到的状态。查询中断不代表任务失败，点击“重新查询”可恢复。', { exact: true }).waitFor({ timeout: 10000 })
  assert.equal(await page.getByText('任务失败', { exact: true }).count(), 0)
  transportFailed = false; await page.getByRole('button', { name: '重新查询', exact: true }).click(); record('transport error preserves RUNNING and supports requery')
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(); await screenshot('08-job-mobile')
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('账号', { exact: true }).waitFor()
  await screenshot('09-login-mobile'); await noOverflow()
  await page.getByLabel('账号', { exact: true }).fill('bob'); await page.getByLabel('密码', { exact: true }).fill('synthetic-fixture-only')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.goto(base + '/cases'); await page.getByText('暂无病例', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes(caseId)); record('logout and different-account login clear prior business data')
  await page.setViewportSize({ width: 1100, height: 900 }); await noOverflow(); record('tablet breakpoint 1100 px')

  // The browser cookie is shared across tabs, while each application's stores are separate.
  const otherTab = await context.newPage()
  otherTab.on('pageerror', error => evidence.pageErrors.push(error.message))
  await otherTab.goto(base + '/cases')
  await otherTab.getByText('暂无病例', { exact: true }).waitFor()
  await otherTab.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('账号', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes(caseId))
  await otherTab.getByLabel('账号', { exact: true }).fill('alice')
  await otherTab.getByLabel('密码', { exact: true }).fill('synthetic-fixture-only')
  await otherTab.getByRole('button', { name: '登录', exact: true }).click()
  await otherTab.getByRole('button', { name: '退出', exact: true }).waitFor()
  await otherTab.goto(base + '/cases')
  await otherTab.getByRole('link', { name: `打开病例 ${caseId}`, exact: true }).waitFor()
  await page.getByRole('button', { name: '创建匿名病例', exact: true }).waitFor()
  await page.getByRole('link', { name: `打开病例 ${caseId}`, exact: true }).waitFor()
  await otherTab.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('账号', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes(caseId))
  await otherTab.close()
  record('cross-tab logout/login synchronizes identity and clears previous account data')

  const measure = Function('return (' + await readFile(join(root, 'geometry-qa', 'measure.js'), 'utf8') + ')')()
  for (const oriented of [false, true]) {
    await page.goto(base + '/geometry-qa/smoke.html' + (oriented ? '?oriented=1' : ''))
    await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
    // Keep the four corner markers inside the viewport; clipped pixels are not measurable.
    await page.getByRole('button', { name: '缩小 CT' }).click()
    await page.getByRole('button', { name: '缩小 CT' }).click()
    for (const stage of ['initial', 'zoom-pan', 'resize']) {
      if (stage === 'zoom-pan') {
        await page.getByRole('button', { name: '放大 CT' }).click()
        const rect = await page.locator('.cornerstone-viewport').boundingBox()
        await page.mouse.move(rect.x + rect.width / 2, rect.y + rect.height / 2)
        await page.mouse.down(); await page.mouse.move(rect.x + rect.width / 2 + 18, rect.y + rect.height / 2 + 12, { steps: 5 }); await page.mouse.up()
      }
      if (stage === 'resize') await page.setViewportSize({ width: 900, height: 800 })
      await page.waitForTimeout(150)
      const metrics = await measure(page)
      evidence.geometry.push({ oriented, stage, ...metrics })
      assert(metrics.markers.every(marker => marker.samples > 0), 'Every overlay marker must remain measurable')
      assert(metrics.maxErrorCssPx <= 1, `Geometry error > 1 CSS px (${oriented}/${stage}): ${metrics.maxErrorCssPx}`)
    }
    await screenshot(oriented ? '11-geometry-oriented' : '10-geometry-nonsquare')
    const release = await page.evaluate(() => {
      const { cornerstone: core, metaData, MetadataEnums, unmount } = window.__geometryFixture
      const imageId = core.getRenderingEngines()[0].getViewport('single-slice').getCurrentImageId()
      const before = { bytes: core.cache.getCacheSize(), metadata: Boolean(metaData.get(MetadataEnums.MetadataModules.NATURALIZED, imageId)) }
      unmount()
      return { imageId, before, after: { bytes: core.cache.getCacheSize(), image: Boolean(core.cache.getImage(imageId)),
        metadata: Boolean(metaData.get(MetadataEnums.MetadataModules.NATURALIZED, imageId)) } }
    })
    assert(release.before.bytes > 0 && release.before.metadata, 'Real renderer should own image and metadata before teardown')
    assert.equal(release.after.bytes, 0)
    assert.equal(release.after.image, false)
    assert.equal(release.after.metadata, false)
    evidence.cacheRelease ??= []
    evidence.cacheRelease.push(release)
  }
  record('actual renderer geometry: non-square, rotated, unequal spacing, pan, zoom, resize, five marker measurements')
  record('actual Cornerstone owned decoded-image and naturalized metadata caches released on teardown')
  }
  if (!['regression', 'extra'].includes(phase)) {
    logged = true; identity = 'alice'; exists = true; ready = true; fixtureList = true
    const routeMatrix = [
      { name: 'dashboard', path: '/', phases: ['shell', 'dashboard', 'responsive', 'final'] },
      { name: 'cases', path: '/cases', phases: ['shell', 'cases', 'responsive', 'final'] },
      { name: 'case-detail', path: `/cases/${caseId}`, phases: ['cases', 'workspace', 'responsive', 'final'], viewer: true },
      { name: 'workspace-result', path: `/results/${resultId}`, phases: ['workspace', 'responsive', 'final'], viewer: true },
      { name: 'job-detail', path: '/jobs/job_failed', phases: ['jobs', 'responsive', 'final'] },
      { name: 'tasks', path: '/jobs', phases: ['jobs', 'final'], optional: phase !== 'final' },
      { name: 'system-status', path: '/system', phases: ['jobs', 'system', 'responsive', 'final'], optional: phase !== 'final' },
      { name: 'preferences', path: '/preferences', phases: ['settings', 'responsive', 'final'], optional: phase !== 'final' },
    ].filter(route => route.phases.includes(phase))
    const sizes = args.sizes ? args.sizes.split(',').map(Number) : phase === 'final' ? [1440, 1512, 1728, 1280, 1024, 768, 390] : [1440, 390]
    const themes = args.themes ? args.themes.split(',') : ['light', 'dark']
    evidence.visualMatrix = []
    await page.goto(base + '/')
    for (const theme of themes) {
      await page.evaluate(theme => localStorage.setItem('epilocate-display-v1', JSON.stringify({ theme, density: 'standard', reducedMotion: false })), theme)
      for (const width of sizes) {
        const height = ({1440:900,1512:982,1728:1117,1280:800,1024:768,768:1024,390:844})[width] || 900
        await page.setViewportSize({ width, height })
        for (const item of routeMatrix) {
          await page.goto(base + item.path)
          await page.waitForTimeout(400)
          const heading = page.getByRole('heading', { level: 1 }).first()
          if (item.optional && !(await heading.count())) { evidence.visualMatrix.push({ route: item.path, skipped: 'route not implemented in this phase' }); continue }
          await heading.waitFor({ timeout: 10000 })
          if (item.viewer) await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
          await noOverflow()
          const actualTheme = await page.evaluate(() => document.documentElement.dataset.theme || document.documentElement.getAttribute('data-color-scheme') || 'unreported')
          if (['responsive', 'final'].includes(phase)) assert.equal(actualTheme, theme, 'Theme must be applied by the application')
          const text = await page.locator('body').innerText()
          if (item.name === 'dashboard') {
            assert(!/COVID probability|分类概率|模型置信度|AI 已确诊|病灶确认|临床风险|0\.1[0-9]|90%/.test(text), 'Dashboard must not reveal AI outputs or clinical claims')
            assert(await page.locator('.case-link').filter({ hasText: 'case_synthetic_' }).count() > 0, 'Dashboard must show actual intercepted case data')
          }
          if (item.name === 'system-status') assert(/未知|未接入|未查询|未提供/.test(text), 'Unsupported telemetry must be clearly unavailable')
          const shot = `clinical-${item.name}-${theme}-${width}`
          await screenshot(shot)
          evidence.visualMatrix.push({ route: item.path, theme, actualTheme, width, height, heading: await heading.innerText(), screenshot: shot + '.png', noOverflow: true, actualSyntheticDicom: Boolean(item.viewer) })
        }
      }
    }
    if (['login', 'settings', 'responsive', 'final'].includes(phase)) {
      logged = false
      for (const theme of themes) for (const width of [1440, 390]) {
        await page.evaluate(theme => localStorage.setItem('epilocate-display-v1', JSON.stringify({ theme, density: 'standard', reducedMotion: false })), theme)
        await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 })
        await page.goto(base + '/login')
        await page.getByLabel('账号', { exact: true }).waitFor()
        await noOverflow()
        await screenshot(`clinical-login-${theme}-${width}`)
      }
    }
    record('Clinical Canvas route and theme screenshot matrix, loopback-only synthetic APIs')
  }
  if (['extra', 'final'].includes(phase)) {
    logged = true; identity = 'alice'; exists = true; ready = true; fixtureList = true
    evidence.extra = { checkType: 'actual browser, intercepted SYNTHETIC_API_FIXTURE responses', accessibilityLimit: 'Computed text contrast sampling and keyboard interactions; not a complete WCAG audit' }
    const requests = []
    const onRequest = request => requests.push(new URL(request.url()).pathname)
    page.on('request', onRequest)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(base + '/preferences')
    await page.getByLabel('外观', { exact: true }).selectOption('light')
    await page.getByLabel('信息密度', { exact: true }).selectOption('standard')
    await page.getByLabel('减少动态效果', { exact: true }).uncheck()
    await page.goto(base + '/')
    await page.locator('.clinical-table tbody tr').first().waitFor()
    const rows = await page.locator('.clinical-table tbody tr').evaluateAll(rows => rows.map(row => ({ top: row.getBoundingClientRect().top, bottom: row.getBoundingClientRect().bottom })))
    assert(rows.length >= 5 && rows[4].bottom <= 900, 'Dashboard must expose five complete rows at 1440×900')
    assert(!requests.some(path => /\/dicom$|\/assets\//.test(path)), 'Dashboard must not preload protected medical media')
    evidence.extra.dashboard = { viewport: [1440, 900], rows, protectedMediaRequests: requests.filter(path => /\/dicom$|\/assets\//.test(path)) }
    await screenshot('extra-dashboard-five-rows-1440x900')
    record('Dashboard five rows above fold, no protected media prefetch')

    await page.getByRole('link', { name: '病例中心', exact: true }).first().click()
    await page.locator('.clinical-table tbody tr').first().waitFor()
    const originalRows = await page.locator('.clinical-table tbody tr').count()
    await page.getByLabel('输入状态').selectOption('CREATED')
    assert.equal(await page.locator('.clinical-table tbody tr').count(), 2)
    await page.getByLabel('筛选已加载病例', { exact: true }).fill('DOES-NOT-EXIST-SYNTHETIC')
    await page.getByText('没有符合筛选条件的病例', { exact: true }).waitFor()
    await screenshot('extra-cases-filter-empty')
    await page.getByRole('button', { name: '清空筛选', exact: true }).click()
    assert.equal(await page.locator('.clinical-table tbody tr').count(), originalRows)
    const densities = {}
    for (const density of ['compact', 'standard', 'comfortable']) {
      await page.getByLabel('显示密度').selectOption(density)
      densities[density] = await page.locator('.clinical-table tbody tr').first().evaluate(row => row.getBoundingClientRect().height)
    }
    evidence.extra.densities = densities
    console.log(JSON.stringify({ densityMeasurements: densities }))
    assert(densities.compact < densities.standard && densities.standard < densities.comfortable, 'Density must change actual row height')
    record('Cases state filter, search-empty and clear restore; three actual row densities')

    await page.getByRole('navigation', { name: '工作区页面' }).getByRole('link', { name: '显示偏好', exact: true }).click()
    await page.getByLabel('外观', { exact: true }).selectOption('dark')
    await page.getByLabel('信息密度', { exact: true }).selectOption('compact')
    await page.getByLabel('减少动态效果', { exact: true }).check()
    await page.reload()
    assert.equal(await page.getByLabel('外观', { exact: true }).inputValue(), 'dark')
    assert.equal(await page.getByLabel('信息密度', { exact: true }).inputValue(), 'compact')
    assert(await page.getByLabel('减少动态效果', { exact: true }).isChecked())
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark')
    await page.setViewportSize({ width: 390, height: 844 })
    const motionReduced = await page.locator('.sidebar').evaluate(el => ({ transition: getComputedStyle(el).transitionDuration, animation: getComputedStyle(el).animationDuration }))
    assert.equal(motionReduced.transition, '0s')
    await page.getByLabel('减少动态效果', { exact: true }).uncheck()
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.sidebar').evaluate(el => getComputedStyle(el).transitionDuration), '0s')
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' })
    await page.getByLabel('外观', { exact: true }).selectOption('system')
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark')
    await page.emulateMedia({ colorScheme: 'light' })
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light')
    await page.reload()
    assert.equal(await page.getByLabel('外观', { exact: true }).inputValue(), 'system')
    await page.getByLabel('信息密度', { exact: true }).selectOption('standard')
    evidence.extra.preferences = { darkPersisted: true, densityPersisted: true, reducedMotionPersisted: true, appMotionReduced: motionReduced, osMotionRespected: true, liveSystemTheme: ['dark', 'light'] }
    record('Display preferences controls persist; OS theme changes live; app and OS reduced motion respected')

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(base + '/jobs/job_failed')
    await page.getByText('任务失败：推理未完成', { exact: true }).waitFor()
    await page.getByRole('navigation', { name: '工作区页面' }).getByRole('link', { name: '任务记录', exact: true }).click()
    await page.locator('.clinical-table tbody tr').first().waitFor()
    assert.equal(await page.locator('.clinical-table tbody tr').count(), 1)
    await page.getByLabel('任务状态').selectOption('RUNNING')
    await page.getByText('没有符合筛选条件的任务', { exact: true }).waitFor()
    await page.getByLabel('任务状态').selectOption('FAILED')
    assert.equal(await page.locator('.clinical-table tbody tr').count(), 1)
    await page.getByRole('button', { name: '重新读取状态', exact: true }).click()
    await screenshot('extra-tasks-spa-known-failed')
    await page.reload()
    await page.getByText('暂无已确认任务', { exact: true }).waitFor()
    record('SPA navigation preserves known Job collection; filter, refresh and hard-reload empty behavior')

    await page.goto(base + '/not-an-implemented-clinical-route')
    await page.getByRole('heading', { name: '页面不存在', exact: true }).waitFor()
    await screenshot('extra-not-found')
    await page.getByRole('link', { name: '返回概览', exact: true }).click()
    await page.getByRole('heading', { name: '工作概览', exact: true }).waitFor()
    exists = false
    await page.goto(base + '/cases')
    await page.getByText('暂无病例', { exact: true }).waitFor()
    await screenshot('extra-cases-empty')
    exists = true
    casesResponse = 'forbidden'
    await page.reload()
    await page.getByRole('alert').waitFor()
    assert(!(await page.locator('body').innerText()).includes('INTERNAL_DEBUG_SHOULD_NOT_APPEAR'))
    await screenshot('extra-cases-forbidden')
    casesResponse = 'offline'
    await page.reload()
    await page.getByRole('alert').waitFor()
    await screenshot('extra-cases-offline')
    casesResponse = 'normal'
    await page.getByRole('button', { name: /^刷\s*新$/ }).click()
    await page.locator('.clinical-table tbody tr').first().waitFor()
    record('404 return navigation; empty, 403 and offline Cases; explicit refresh recovers')

    // Sample computed text colors over their effective ancestor backgrounds.
    async function computedContrast() {
      return page.evaluate(() => {
        const rgb = value => { const m = value.match(/[\d.]+/g)?.map(Number) || [0,0,0]; return [...m.slice(0,3), m.length > 3 ? m[3] : 1] }
        const blend = (front, back) => [0,1,2].map(i => front[i] * front[3] + back[i] * (1-front[3])).concat(1)
        const luminance = color => color.slice(0,3).map(v => { v/=255; return v<=.04045 ? v/12.92 : ((v+.055)/1.055)**2.4 }).reduce((s,v,i) => s+v*[.2126,.7152,.0722][i],0)
        const samples = []
        for (const el of document.querySelectorAll('body *')) {
          if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType===Node.TEXT_NODE && n.textContent.trim()) || el.closest('[disabled]')) continue
          const rect=el.getBoundingClientRect(), style=getComputedStyle(el)
          if (!rect.width || !rect.height || style.visibility==='hidden' || style.opacity!=='1' || rect.bottom<0 || rect.top>innerHeight) continue
          let background=[255,255,255,1]
          const ancestors=[]; for(let p=el;p;p=p.parentElement) ancestors.unshift(p)
          for(const p of ancestors) background=blend(rgb(getComputedStyle(p).backgroundColor),background)
          const foreground=blend(rgb(style.color),background), l1=luminance(foreground),l2=luminance(background)
          const ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)
          const size=parseFloat(style.fontSize),weight=parseInt(style.fontWeight)||400,minimum=size>=24||(size>=18.66&&weight>=700)?3:4.5
          samples.push({ text:el.textContent.trim().slice(0,55),tag:el.tagName,class:el.className,ratio:+ratio.toFixed(3),minimum,color:style.color,background:background.slice(0,3).map(Math.round),fontSize:size })
        }
        return { sampleCount:samples.length, failures:samples.filter(s=>s.ratio+.01<s.minimum), minimumRatio:Math.min(...samples.map(s=>s.ratio)) }
      })
    }
    evidence.extra.contrast = []
    for (const theme of ['light','dark']) {
      await page.goto(base + '/preferences')
      await page.getByLabel('外观', { exact: true }).selectOption(theme)
      for (const path of ['/', '/cases', '/jobs', '/system', '/preferences']) {
        await page.goto(base + path)
        await page.getByRole('heading', { level: 1 }).first().waitFor()
        await page.waitForTimeout(180)
        evidence.extra.contrast.push({ theme, route:path, ...(await computedContrast()) })
      }
    }
    await writeFile(join(output,'computed-contrast.json'),JSON.stringify(evidence.extra.contrast,null,2))
    assert(evidence.extra.contrast.every(sample => sample.failures.length === 0), 'Computed contrast samples require review')
    record('Light/dark computed text contrast sampled on five routes; exceptions recorded for human review')

    await page.goto(base + `/results/${resultId}`)
    await page.getByRole('button', { name:'放大 CT' }).waitFor({timeout:30000})
    await page.waitForFunction(() => !document.querySelector('.fusion-controls input[type=checkbox]').disabled)
    await page.getByRole('checkbox', { name:'显示叠加' }).check()
    const before = await page.evaluate(async () => {
      const coreUrl=performance.getEntriesByType('resource').map(r=>r.name).find(url=>url.includes('@cornerstonejs_core.js'))
      if(!coreUrl) throw new Error('Actual Cornerstone module URL unavailable')
      const core=window.__qaCore=await import(coreUrl)
      window.__qaCanvas=document.querySelector('.cornerstone-viewport canvas')
      window.__qaEngine=core.getRenderingEngines()[0]
      window.__qaRendered=0
      document.querySelector('.cornerstone-viewport').addEventListener(core.Enums.Events.IMAGE_RENDERED,()=>window.__qaRendered++)
      return { engines:core.getRenderingEngines().length,cacheBytes:core.cache.getCacheSize(),canvasCount:document.querySelectorAll('.cornerstone-viewport canvas').length }
    })
    await page.waitForTimeout(300)
    assert.equal(before.engines,1); assert(before.cacheBytes>0); assert.equal(before.canvasCount,1)
    const canvasBefore=await page.locator('.cornerstone-viewport canvas').evaluate(canvas=>canvas.toDataURL())
    await page.getByRole('button',{name:'切换明暗主题',exact:true}).click()
    await page.waitForTimeout(200)
    const canvasAfter=await page.locator('.cornerstone-viewport canvas').evaluate(canvas=>canvas.toDataURL())
    assert.equal(createHash('sha256').update(canvasBefore).digest('hex'),createHash('sha256').update(canvasAfter).digest('hex'),'Theme changes must preserve actual CT canvas pixels')
    assert(await page.evaluate(()=>window.__qaCanvas===document.querySelector('.cornerstone-viewport canvas')))
    for (const scale of [16,32,64,16,32,64,16,32,64,32]) await page.getByRole('button',{name:`${scale} px`,exact:true}).click()
    await page.waitForTimeout(700)
    assert(await page.getByRole('button',{name:'32 px',exact:true}).evaluate(button=>button.classList.contains('active')))
    const after=await page.evaluate(()=>({engines:window.__qaCore.getRenderingEngines().length,cacheBytes:window.__qaCore.cache.getCacheSize(),sameCanvas:window.__qaCanvas===document.querySelector('.cornerstone-viewport canvas'),sameEngine:window.__qaEngine===window.__qaCore.getRenderingEngines()[0]}))
    assert.equal(after.engines,before.engines); assert.equal(after.cacheBytes,before.cacheBytes)
    assert(after.sameCanvas&&after.sameEngine)
    await screenshot('extra-workspace-ten-switches-stable')
    await page.setViewportSize({width:1512,height:982})
    await page.waitForTimeout(600)
    const idleStart=await page.evaluate(()=>({rendered:window.__qaRendered,box:document.querySelector('.cornerstone-stage').getBoundingClientRect().toJSON()}))
    await page.waitForTimeout(30000)
    const idleEnd=await page.evaluate(()=>({rendered:window.__qaRendered,box:document.querySelector('.cornerstone-stage').getBoundingClientRect().toJSON(),engines:window.__qaCore.getRenderingEngines().length,cacheBytes:window.__qaCore.cache.getCacheSize()}))
    assert(idleEnd.rendered-idleStart.rendered<=2,'No ongoing ResizeObserver/render feedback loop during 30s idle')
    assert.deepEqual(idleEnd.box,idleStart.box)
    evidence.extra.renderer={before,after,themePixelsUnchanged:true,rapidScaleChanges:10,idleSeconds:30,idleStart,idleEnd}
    await page.getByRole('link',{name:'概览',exact:true}).click()
    await page.getByRole('heading',{name:'工作概览',exact:true}).waitFor()
    evidence.extra.renderer.afterUnmount=await page.evaluate(()=>({engines:window.__qaCore.getRenderingEngines().length,cacheBytes:window.__qaCore.cache.getCacheSize()}))
    assert.equal(evidence.extra.renderer.afterUnmount.engines,0)
    assert.equal(evidence.extra.renderer.afterUnmount.cacheBytes,0)
    record('Theme preserves CT pixels/canvas; ten rapid scales retain renderer/cache; resize settles for 30s; SPA unmount releases renderer/cache')
    page.off('request',onRequest)
  }

  assert.deepEqual(evidence.pageErrors, [], 'No browser page errors should occur')
  await writeFile(join(output, 'browser-acceptance.json'), JSON.stringify(evidence, null, 2))
  console.log(JSON.stringify({ passed: evidence.scenarios.length, screenshots: evidence.screenshots.length,
    geometryMeasurements: evidence.geometry.length, output }, null, 2))
} catch (error) {
  evidence.failure = error.message
  if (activePage) {
    await activePage.screenshot({ path: join(output, 'failure.png'), fullPage: true, animations: 'disabled' }).catch(() => {})
    evidence.failureUrl = activePage.url()
    evidence.failureText = await activePage.locator('body').innerText().catch(() => '')
  }
  await writeFile(join(output, 'browser-acceptance.json'), JSON.stringify(evidence, null, 2))
  throw error
} finally { await browser.close() }
