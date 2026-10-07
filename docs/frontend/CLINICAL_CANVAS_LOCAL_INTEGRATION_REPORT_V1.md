# Clinical Canvas 本地集成合并验收报告 V1

日期：2026-10-04，Asia/Shanghai。执行范围：附件 `prompts/03_CLINICAL_CANVAS_INTEGRATION.md`；执行者：本轮 Codex。状态：**CLINICAL_CANVAS_LOCAL_INTEGRATION_PARTIAL_PASS**。

现有候选的本地 production preview 和下述受限集成验收完成。真实本地 Gateway/Backend 的登录、病例、上传、Job、隔离、过期和不可用链路通过；正向 Result/资产/叠加链路使用明确标记的 MOCK_API。PostgreSQL、MinIO、真实推理和远端验收未完成，不能据此宣布生产或临床可用。

本轮没有进行 UI 风格或全站视觉重构。唯一产品修复是已接受 Job 的导航故障恢复。没有 push、merge、deploy，没有改 Backend、Gateway、Worker、算法、GT、训练或冻结证据。所有本轮服务和浏览器已停止。

## 固定身份与 Release 交接

| 项目 | 本轮核验值 |
|---|---|
| Worktree | `/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai` |
| 分支 | `feature/clinical-canvas-v1` |
| 开始时真实 HEAD | `7ada03b76142e6f45fea9c531f634e36a44cebf8`；tracked/untracked 干净 |
| 固定受测源码 SHA | `273e76aa3e540cdf14a600452e4980167c158e35` |
| Node / npm | `24.19.0` / `11.17.0`；依赖及锁文件未修改 |
| 构建 | `VITE_PUBLIC_BASE=/mvp/ npm run build -- --outDir .local/integration-20261004-v1/release-dist`；production、`/mvp/` base |
| Preview | 现有 `npm run preview`，loopback 5197；临时 HTTPS 同源入口 5198，代理 `/auth` 和 `/api/v2` 至隔离 Gateway |
| 构建包 SHA-256 | `42321d170b168702fb8edbdd4ca697416749c5418d9b14113bc4660515712727` |
| 构建包 | `frontend/.local/integration-20261004-v1/clinical-canvas-production-273e76aa3e54.tar.gz`，仅静态产物 |
| 构建字节身份 | 34 个文件均与 HTTPS preview 的响应逐字节一致；逐文件摘要见 artifact inventory |

Release 应只读固定源码和构建包，并校验 [Release manifest](CLINICAL_CANVAS_RELEASE_MANIFEST_V1.json)、[源码文件摘要](clinical-canvas-integration-evidence-v1/source-files.json) 和 [构建文件摘要](clinical-canvas-integration-evidence-v1/artifact-files.json)。后续文档提交不会替换该受测源码身份。不传输 `.local` 整个目录，其中包含隔离测试数据库、合成 DICOM、临时证书和测试凭证；这些不在 Git 交付范围。

开始时按 canonical Registry 与真实 Git 确认该固定例外工作树；没有 reset 到旧 SHA，没有改原 canonical checkout 的无关文件，原 `.local/`、`dist/` 和 `node_modules/` 保留。任务包 SHA-256 和开始状态见 [opening identity](clinical-canvas-integration-evidence-v1/opening-identity.json)。

## API / Session 来源

本轮实际使用受测候选内的 `backend_v2/` 与 `session_gateway/`；它们相对开始 HEAD 未修改。其最近路径变更来源是 `9f06fbd1a3a6cec88dbcfd0e867d768ba9c40b5e`。契约是 `Backend API v2.0 Freeze`、Result `2.0` 与 Phase5 Session Gateway；源文件、客户端、类型、Viewer、几何及三份契约文档均有 SHA-256 存证。

独立只读复核发现注册 Backend worktree 当前为 `feature/backend-v2 @ fbd3c5802fef23df2d1ef66257c323910d383518`。该分支缺少本候选需要的授权 DICOM 恢复路由和 Session Gateway，认证与资产 URL/过期门也不同。因此没有把旧 Backend SHA 当作等价契约来源，也没有改或合并该工作树。

当前浏览器支持个人病例分页、创建/上传、按已知 ID 读取 Job/Result、授权 DICOM/资产、Cookie Session/CSRF。没有用户侧 Worker 在线性、GPU 利用率、全局统计、可信角色或服务器搜索字段。本轮没有新增这些接口或假数据。

## 实际测试

| 层次 | 本轮实际执行 | 结果与证据限制 |
|---|---|---|
| 开始源码回归 | Vitest 18 specs、121 tests | 本轮重新运行 PASS，非引用历史测试 |
| 修复后回归 | Vitest 18 specs、126 tests | PASS；新增 5 个有故障触发条件的 Job 恢复/隔离测试 |
| 类型与构建 | 现有 build 中 `vue-tsc -b` 与 Vite production build | PASS；保留大 bundle 警告，没有宣称依赖/codec 或性能问题全部解决 |
| LOCAL_INTEGRATION | 实际 HTTPS 浏览器 → 真实 Gateway → 真实 Backend，14 场景 | PASS；SQLite 独立库、显式 TEST_STORAGE 文件适配器，非 PostgreSQL/MinIO |
| MOCK_API | 真实 production bundle 与 Cornerstone，API 响应由 Playwright 合成夹具拦截，10 场景 | PASS；没有新推理或新完成任务，正向 Result 为预先定义的已完成契约夹具 |
| Production 几何 | 两种合成 DICOM，各 initial / zoom-pan / resize，30 个标记测量 | 六组 PASS；最大 `0.45566673285130727 CSS px`，上限 `1 CSS px` |
| Preview 产物身份 | 34 个静态文件 HTTP 200 和字节比较 | 全部一致 |

日志：[baseline tests](clinical-canvas-integration-evidence-v1/baseline-tests.log)、[126 tests](clinical-canvas-integration-evidence-v1/tests.log)、[build](clinical-canvas-integration-evidence-v1/build.log)、[运行库版本](clinical-canvas-integration-evidence-v1/runtime-versions.json)。Git 中日志副本仅规范化行末空白；原始字节未改，路径和 SHA-256 记在 manifest 的 `raw_log_digests`。两份机器证据：[LOCAL_INTEGRATION](clinical-canvas-integration-evidence-v1/local/browser-acceptance.json)、[MOCK_API](clinical-canvas-integration-evidence-v1/mock/browser-acceptance.json)。最终两次浏览器执行均为 0 page error、0 外部请求；实际页面操作使用正常表单、文件输入、按钮、链接、拖动和刷新。

### 真实本地链路

- HTTPS 登录、错误密码、受保护 `/mvp/cases` 的 `next` 深链返回；真实 Cookie 为 Secure、HttpOnly、SameSite Strict。
- 不带 CSRF 的病例创建 POST 被真实 Gateway 以 403 拒绝。
- 真实创建匿名病例；带非空 PatientName/PatientID 的旧合成 fixture 被后端去标识校验以 422 拒绝；清空这些合成标签后的 DICOM 成功上传。
- 真实授权 DICOM 恢复，实际 production Cornerstone 解码/渲染；病例深链刷新恢复。
- 创建真实隔离库 Occlusion Job；阻断 Job 页面 JS chunk 后通过已接受任务的普通恢复链接打开原 Job，网络记录证明只有一次 Job POST。
- Job 深链及刷新仍为 CREATED，无完成结果链接、无自动重跑。最终数据库为 **1 Job、CREATED、attempt_no=0；0 Worker；0 Result**。仅注册合成模型元数据，没有加载 checkpoint，也没有启动 sweeper/Worker。
- Dashboard 展示真实当前账号病例状态，不展示具体 AI 概率；System 的病例 API 显示本次请求“曾响应”，GPU/Worker 等为“未接入”。“未接入”不等于服务端已经证明离线：当前用户契约无法观察在线 Worker。
- 跨标签退出、切换 qa_bob 后病例列表为空；前账号 Case、DICOM、Job 读取 404；不存在的 Result/资产 404。这验证了所有权负向路径，未验证真实正向 Result 取回。
- 仅修改隔离库的 Slice 过期时间及 Case 状态：后端真实 DICOM 410，CT 不再显示，新分析按钮禁用。
- `/mvp/` production fallback 和应用 404；实际停止本轮 Backend 进程后，Gateway 对病例、Job 和登录产生真实 503，页面提供安全不可用提示。

### Mock / Viewer 链路

已完成 Job → Result 使用预先定义的 synthetic fixture；wire 字段因现有严格契约保留 `source=LIVE_CASE`，**这只是接口夹具值，不是本轮真实推理事实**。所有对应截图均带 `MOCK_API` 标记；Mock 模式新建 Job 数为 0。

实际 production bundle 验证了大写 DICOM SHA、真实解码、非方形影像、旋转方向/不等像素间距、平移/缩放/resize 几何、Result 刷新恢复尺度/图层/叠加/相机。相机恢复比较了 Cornerstone 的实际 zoom/pan，非只看存储值；该恢复结论仅针对 Result 页面。

分别制造 SHA、Slice、未核验模型版本和资产尺寸不一致：前三项保留独立合法图层并禁用 overlay；不一致资产元数据拒绝该图层，另一合法尺度可读取。损坏 PNG 拒绝解码，显式重试恢复；DICOM 410 保留独立热图并禁用 overlay。Dashboard 不请求 Result/DICOM/热图，不出现具体概率。

几何测量读取 production 动态模块内的实际 RenderingEngine 与 `indexToWorld/worldToCanvas`，比较真实 overlay 红色标记中心；未用 dev smoke 页面或改产品 Viewer 来获得通过。

## 最小产品修复与失败记录

原 `CaseDetailView` 在 AcceptedJob 后先删除幂等键再跳转；导航失败后重试可创建第二个 Job。现在按 Case/Slice/model/kind 保留已接受 Job ID，失败重试只导航原任务；会话/病例重置清空恢复目标，其他动作提交失败不会显示旧任务链接。

真实 Chrome 故障注入还证明失败的动态 import 可在当前 document 缓存，重复 SPA 跳转仍失败。因此增加同一已接受 Job 的普通链接“打开已创建任务 →”，通过新 document 恢复该深链；不是自动重跑推理。

初次新回归中，账号切换 fixture 未模拟真实 accept 后的失效/重新读取；修正测试前置状态后通过。早期服务脚本因目录权限和局部 FastAPI 类型注解初始化失败；浏览器 harness 又因网络空闲等待、短 ID 显示、登录异步等待、图层选择与请求归属断言失败。本轮修复这些 harness 问题并从新隔离库完整重跑，未弱化身份/几何/错误断言。早期日志、JSON 和截图原样保存在 manifest 指向的 ignored 本轮目录；不计为最终 PASS，不覆盖既有历史报告。

## 本轮必要截图

23 张截图的完整路径与 SHA-256 均在 Release manifest。以下是主要状态：

| 状态 | 环境 | 截图 |
|---|---|---|
| 登录 | LOCAL_INTEGRATION | [01-login](clinical-canvas-integration-evidence-v1/local/01-login.png) |
| Dashboard，无概率 | LOCAL_INTEGRATION | [04-dashboard](clinical-canvas-integration-evidence-v1/local/04-dashboard.png) |
| Case，真实授权 DICOM + Cornerstone | LOCAL_INTEGRATION | [02-case](clinical-canvas-integration-evidence-v1/local/02-case-cornerstone.png) |
| 已接受 Job 导航恢复 | LOCAL_INTEGRATION | [03a-recovery](clinical-canvas-integration-evidence-v1/local/03a-accepted-job-navigation-recovery.png) |
| Job CREATED，无 Worker/Result | LOCAL_INTEGRATION | [03-job](clinical-canvas-integration-evidence-v1/local/03-job-no-worker.png) |
| GPU/Worker 未接入 | LOCAL_INTEGRATION | [05-system](clinical-canvas-integration-evidence-v1/local/05-worker-unobserved.png) |
| 真实输入到期 | LOCAL_INTEGRATION | [07-expired](clinical-canvas-integration-evidence-v1/local/07-expired-input.png) |
| 真实 Backend 不可用 | LOCAL_INTEGRATION | [09-unavailable](clinical-canvas-integration-evidence-v1/local/09-backend-unavailable.png) |
| Result viewer | MOCK_API | [01-result](clinical-canvas-integration-evidence-v1/mock/01-result-fixture.png) |
| Result 手机视图 | MOCK_API | [04-mobile](clinical-canvas-integration-evidence-v1/mock/04-result-mobile.png) |
| 到期输入 + 独立热图 | MOCK_API | [07-independent-layer](clinical-canvas-integration-evidence-v1/mock/07-expired-input-independent-layer.png) |

已查看登录、Dashboard、Case、Result 桌面/390px、System、过期和不可用截图；未发现异常水平溢出或新增页面脚本错误。页面正常纵向滚动保留。本轮没有再做全站主题/视觉矩阵或完整 WCAG/性能审计。

## 未来版本与尚未验收项

Result 的版本来源仍限实际字段：`model_id`、`model_version`、`preprocessing_version`、`protocol_id`、`contract_version`。既有 model/preprocessing/protocol 几何白名单保持不变。未核验新版本可以查看独立图层，但没有合格映射就不画 overlay。

`operator_version`、`search_protocol_version` 在当前严格 Result schema 中不存在，本轮只记录 **DRAFT 契约需求**：由服务端返回真实、不可变的版本身份并更新 schema 与几何映射证据后再接入。没有硬编码未来生产版本或修改算法/后端契约。

未完成的真实条件是 PostgreSQL/Alembic/并发行为、S3/MinIO 资产生命周期、真实正向 Result 与资产取回、授权远端账号和 GPU Worker 的注册/心跳/领取/推理/Result/刷新链路。当前 Docker daemon 未运行，本轮采用受限 SQLite + TEST_STORAGE；无可用研究 GPU，没有访问远端、训练数据、模型权重或 sealed GT。大 bundle 警告保留；本轮未证明所有压缩 DICOM codec 或完整性能指标。

**唯一下一步：** Release 按固定 manifest 只读复核该 candidate，在 PostgreSQL/MinIO 与可观测 GPU Worker 条件具备且另获授权后补齐真实远端验收，再决定发布。本轮到此停止，不表示生产或临床验收通过。
