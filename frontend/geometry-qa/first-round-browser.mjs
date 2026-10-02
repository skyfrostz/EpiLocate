// Isolated local UI acceptance: every auth/business response is intercepted.
// No request reaches a deployment, Worker, or patient-data service.
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { resolve, join } from 'node:path'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.FRONTEND_QA_URL || 'http://127.0.0.1:5183'
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'QA must only target a local server')
const output = resolve(process.env.FRONTEND_QA_OUTPUT || '.local/first-round-browser')
await mkdir(output, { recursive: true })
const dicom = await readFile(new URL('../.local/geometry_synthetic_ct.dcm', import.meta.url))
const hash = createHash('sha256').update(dicom).digest('hex')
const caseId = 'case_synthetic_' + '0123456789'.repeat(5)
const sliceId = 'slice_synthetic'
const jobId = 'job_synthetic'
const resultId = 'result_synthetic'
const createdAt = '2026-10-01T12:00:00Z'
const browser = await chromium.launch({ ...(process.env.FRONTEND_QA_EXECUTABLE ? { executablePath: process.env.FRONTEND_QA_EXECUTABLE } : { channel: process.env.FRONTEND_QA_BROWSER || 'msedge' }), headless: true,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const evidence = { environment: 'local intercepted synthetic APIs, no inference', scenarios: [], screenshots: [], geometry: [], pageErrors: [] }
const record = name => evidence.scenarios.push({ name, passed: true })
let activePage
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
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
  let logged = false, identity = 'alice', exists = false, ready = false, polls = 0
  let holdNextSessionRead = false, releaseSessionRead
  let heldSessionRead = Promise.resolve()
  let dicomExpired = false, assetBroken = false, transportFailed = true
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
    if (path === '/auth/session') {
      if (holdNextSessionRead) { holdNextSessionRead = false; await heldSessionRead }
      return json(route, logged ? { username: identity, csrf_token: 'synthetic-csrf-only' } : { code: 'UNAUTHENTICATED' }, logged ? 200 : 401)
    }
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
      if (request.method() === 'POST') { exists = true; return json(route, caseRecord(), 201) }
      return json(route, { items: exists && identity === 'alice' ? [caseRecord()] : [], next_cursor: null })
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
  await page.goto(base + '/'); await page.getByText('影像研究工作台', { exact: true }).waitFor()
  await screenshot('02-dashboard-desktop'); await page.goto(base + '/cases')
  await page.getByRole('button', { name: '创建匿名病例' }).click()
  await page.getByLabel('选择已去标识的单张 CT DICOM（最多 20 MiB）').waitFor()
  await page.locator('input[type=file]').setInputFiles(fileURLToPath(new URL('../.local/geometry_synthetic_ct.dcm', import.meta.url)))
  await page.getByRole('button', { name: '上传 DICOM' }).click()
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 }); record('create case, synthetic DICOM upload, actual Cornerstone decoding')
  await page.reload(); await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 }); record('Case deep-link refresh restores authorized DICOM')
  await screenshot('03-case-desktop'); await noOverflow()
  await page.goto(base + '/cases')
  await page.locator('.case-row').waitFor()
  for (const name of ['卡片', '列表', '卡片']) {
    await page.getByRole('button', { name, exact: true }).click()
    await page.waitForFunction(name => document.querySelector(`.segmented-control button[aria-pressed="true"]`)?.textContent === name, name)
  }
  await page.getByLabel('输入状态', { exact: true }).selectOption('READY')
  await page.reload()
  await page.locator('.collection-cards .case-row').waitFor()
  assert.equal(await page.getByLabel('输入状态', { exact: true }).inputValue(), 'READY')
  await screenshot('enterprise-cases-cards-desktop')
  await page.getByLabel('查找病例', { exact: true }).fill('no-match')
  await page.getByText('没有匹配的病例', { exact: true }).waitFor()
  assert(!page.url().includes('no-match'))
  await page.getByRole('button', { name: '清除筛选', exact: true }).click()
  await page.locator('.case-link').first().click()
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
  await page.goBack(); await page.locator('.collection-cards .case-row').waitFor()
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow()
  await screenshot('enterprise-cases-cards-mobile')
  await page.getByRole('button', { name: '列表', exact: true }).click()
  await page.locator('.table-head').waitFor(); await noOverflow()
  await screenshot('enterprise-cases-list-mobile')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto(base + '/')
  await page.locator('.case-row').waitFor()
  await screenshot('enterprise-dashboard-populated')
  record('case modes repeat, URL refresh, status filter, private search, empty recovery, Back and mobile layout')
  await page.goto(base + '/cases/' + caseId)
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(); await screenshot('03-case-mobile')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '运行 16 / 32 / 64 px 遮挡' }).click()
  await page.getByText('排队中', { exact: true }).first().waitFor()
  await page.getByRole('link', { name: '查看已完成结果 →' }).waitFor({ timeout: 10000 })
  await page.getByRole('link', { name: '查看已完成结果 →' }).click()
  await page.getByRole('button', { name: '放大 CT' }).waitFor({ timeout: 30000 })
  await page.getByText('像素契约匹配', { exact: true }).waitFor(); record('Job polling and Result navigation, uppercase SHA-256, verified geometry')
  await page.getByRole('checkbox', { name: '显示叠加' }).check()
  // Deliberately synthetic focus with a controlled auth delay. This is not a native-focus or performance claim.
  const initialGeometry = await page.evaluate(() => {
    const stage = document.querySelector('.cornerstone-stage')
    const overlay = document.querySelector('.cornerstone-overlay')
    const boundary = document.querySelector('.session-workspace')
    window.__qaSessionNodes = { stage, overlay, boundary }
    const rect = stage.getBoundingClientRect()
    return { width: rect.width, height: rect.height, overlayWidth: overlay.width, overlayHeight: overlay.height, scrollY }
  })
  assert(initialGeometry.width > 0 && initialGeometry.height > 0 && initialGeometry.overlayWidth > 0 && initialGeometry.overlayHeight > 0)
  heldSessionRead = new Promise(resolve => { releaseSessionRead = resolve })
  holdNextSessionRead = true
  const verificationStartedAt = performance.now()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.locator('.session-verification-curtain').waitFor()
  const maskedSamples = []
  for (let index = 0; index < 10; index++) {
    await page.waitForTimeout(500)
    const sample = await page.evaluate(() => {
      const { stage, overlay, boundary } = window.__qaSessionNodes
      const rect = stage.getBoundingClientRect()
      const curtain = document.querySelector('.session-verification-curtain')
      const style = getComputedStyle(boundary)
      const curtainStyle = getComputedStyle(curtain)
      return { width: rect.width, height: rect.height, overlayWidth: overlay.width, overlayHeight: overlay.height,
        scrollY, opacity: style.opacity, display: style.display, inert: boundary.inert,
        hidden: boundary.getAttribute('aria-hidden'), curtainPosition: curtainStyle.position,
        curtainBackground: curtainStyle.backgroundColor, loginVisible: Boolean(document.querySelector('.login-page')) }
    })
    for (const key of ['width', 'height', 'overlayWidth', 'overlayHeight', 'scrollY']) assert.equal(sample[key], initialGeometry[key], `Verification changed ${key}`)
    assert.equal(sample.opacity, '0'); assert.notEqual(sample.display, 'none'); assert(sample.inert); assert.equal(sample.hidden, 'true')
    assert.equal(sample.curtainPosition, 'fixed'); assert.equal(sample.curtainBackground, 'rgb(245, 246, 248)'); assert.equal(sample.loginVisible, false)
    maskedSamples.push(sample)
  }
  await page.keyboard.press('Tab')
  assert(await page.evaluate(() => !document.querySelector('.session-workspace').contains(document.activeElement)))
  assert.equal(await page.getByRole('button', { name: '放大 CT' }).count(), 0)
  await page.screenshot({ path: join(output, 'passive-session-verification-curtain.png'), animations: 'disabled' })
  evidence.screenshots.push('passive-session-verification-curtain.png')
  const triggerToReleaseMs = performance.now() - verificationStartedAt
  releaseSessionRead()
  await page.locator('.session-verification-curtain').waitFor({ state: 'detached' })
  assert(await page.evaluate(() => {
    const { stage, overlay, boundary } = window.__qaSessionNodes
    return stage === document.querySelector('.cornerstone-stage') && overlay === document.querySelector('.cornerstone-overlay') &&
      boundary === document.querySelector('.session-workspace') && !boundary.inert && !boundary.hasAttribute('aria-hidden')
  }))
  const restoredGeometry = await page.evaluate(() => {
    const stage = document.querySelector('.cornerstone-stage'), overlay = document.querySelector('.cornerstone-overlay')
    const boundary = document.querySelector('.session-workspace'), rect = stage.getBoundingClientRect()
    return { width: rect.width, height: rect.height, overlayWidth: overlay.width, overlayHeight: overlay.height, scrollY,
      opacity: getComputedStyle(boundary).opacity, display: getComputedStyle(boundary).display }
  })
  for (const key of ['width', 'height', 'overlayWidth', 'overlayHeight', 'scrollY']) assert.equal(restoredGeometry[key], initialGeometry[key], `Restored ${key} changed`)
  assert.notEqual(restoredGeometry.opacity, '0'); assert.notEqual(restoredGeometry.display, 'none')
  evidence.passiveVerification = { trigger: 'synthetic focus', minimumHoldMs: 5000, triggerToReleaseMs, initialGeometry, maskedSamples, restoredGeometry }
  record('synthetic focus verification preserves stage/overlay dimensions and conceals private workspace for at least 5 seconds')
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
  await page.getByRole('button', { name: '打开导航' }).click()
  heldSessionRead = new Promise(resolve => { releaseSessionRead = resolve }); holdNextSessionRead = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.locator('.session-verification-curtain').waitFor()
  await page.keyboard.press('Escape')
  assert(await page.locator('.sidebar').evaluate(sidebar => sidebar.classList.contains('sidebar-open')))
  assert.equal(await page.getByRole('button', { name: '关闭菜单' }).count(), 0)
  assert(await page.locator('.session-workspace').evaluate(boundary => getComputedStyle(boundary).opacity === '0' && boundary.inert && boundary.getAttribute('aria-hidden') === 'true'))
  releaseSessionRead()
  await page.locator('.session-verification-curtain').waitFor({ state: 'detached' })
  await page.getByRole('button', { name: '关闭菜单' }).waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.locator(':focus').getAttribute('aria-label'), '打开导航')
  record('mobile result privacy curtain blocks hidden sidebar keys and restores normal Escape after verification')
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
  await otherTab.getByText(caseId, { exact: true }).waitFor()
  await page.getByRole('button', { name: '创建匿名病例', exact: true }).waitFor()
  await page.getByText(caseId, { exact: true }).waitFor()
  await otherTab.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('账号', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes(caseId))
  await otherTab.close()
  record('cross-tab logout/login synchronizes identity and clears previous account data')

  const measure = Function('return (' + await readFile(new URL('./measure.js', import.meta.url), 'utf8') + ')')()
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
