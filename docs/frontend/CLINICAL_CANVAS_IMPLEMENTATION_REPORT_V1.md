# Clinical Canvas v1 实施与验收报告

负责人：钟佳桦；日期：2026-10-03。分支：`feature/clinical-canvas-v1`。
基线：`2be89143a8abccb3c3896a8f53633e490cf79b28`（远端最新前端，已 fetch 核实）。
最终受测应用提交：`e8eec4241d2a33ff8995461ed2cc920840962b4a`（Phase 8）；其后仅补交付文档，最终仓库 SHA 见交付消息。
工作树：`/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai`。

## Phase 0

完整解压设计附件并阅读规范、原型源、实现参考与 QA。原型是设计依据；生产界面不复制示例数据。使用现有 Vue/Pinia/Router/Ant Design/Cornerstone。无 .codegraph 索引，不自行创建。执行项目 skill，保留其他 worktree/研究资料。

基线：85 tests / 15 specs PASS；vue-tsc + Vite build PASS。现有大 chunk 警告保留。浏览器使用合成 DICOM 与截获 API，不能代替真实服务/GPU E2E。

## 阶段计划

0 审计；1 tokens/shell；2 Dashboard；3 Cases/Case；4 Result/Workspace；5 Jobs/System；6 Login/Preferences/states；7 responsive/dark/accessibility；8 regression/visual acceptance。每阶段测试、build、截图和小提交；只由主 agent 写仓库，子 agent 提供独立审计、候选 patch 与 QA。

## 固定边界

仅 frontend 与本轮工程报告；不修改 Backend/Worker/训练/数据/D10/冻结基线/部署。当前能力见 FRONTEND_CAPABILITY_MATRIX_V1.md，后端提案见 BACKEND_CAPABILITY_REQUEST_V1.md。

## 实现结果与页面

| 页面 | 完成内容 | 数据边界 |
|---|---|---|
| Login | 精简品牌、单主登录操作、明暗主题、键盘与密码管理器标签 | 保留 safe next、Cookie session 与 CSRF |
| Shell | 五个一级入口、208px 侧栏、56px 顶栏、移动抽屉、skip link | 一个 Shell，无用户名伪造权限 |
| Dashboard | 同底座摘要、继续工作、最近病例主表、任务/可用性/最近访问侧栏 | Case 首个6条；不加载 DICOM、Result 或热图；无全局总量或概率 |
| Cases | 语义表格、已加载范围搜索、输入状态筛选、游标追加、密度 | 不冒充服务器搜索；完整 ID 可键盘展开 |
| Case | 病例资料/CT/输入与分析三栏；无输入、过期、错误状态统一 | 原上传与任务创建链路保留；只有单切片 |
| Result | 中央视口、右侧尺度/图层/透明度/模型输出，折叠来源 | 原 SHA、provenance、几何门、资产授权及相机恢复保留 |
| Jobs（新增） | 本会话已知任务、筛选、逐 ID 重新 GET、观察时间 | 最多30条，最多3并发；失败保留旧记录，不发现全局队列 |
| System（新增） | 真实 Session 证据、手动病例 API 检查、未接入指标 | 无内部探测，无假健康/心跳/GPU利用率 |
| Preferences（新增） | system/light/dark、compact/standard/comfortable、减少动态 | localStorage 仅持久化三个非敏感显示字段 |
| 404（新增） | 返回概览或病例中心 | 仍受会话保护；/settings 兼容跳到 /preferences |

### Dashboard 信息架构

主区/侧区约70/30。共同摘要带仅统计当前已加载病例与本会话已知任务。病例主表使用 Case ID、输入状态、独立的“分析未查询”、创建时间及操作；完整匿名上下文可展开。最近访问仅在内存保留，登录状态重验（包括 focus 同步）也可能清空。无完整 Case→Job→Result 关系时，不宣称全病例分析完成。

### Workspace 与设计系统

布局从上下文/文案占主导改为 CT 最大。1440px 截图独立抽查：Case 影像卡约61%，Result 约73%工作区宽度。窄屏工具移到影像下方；不承诺手机精细阅片。无新增 CSS 图像变换、过滤器、MPR、测量、窗宽窗位或假序列能力。

`frontend/src/design/tokens.css` 集中颜色、字体、间距尺度、圆角、边框色、阴影、过渡、密度与明暗主题；`design/preferences.ts` 负责系统偏好/持久化；`components/CaseTable.vue`、`EpStatus.vue`、`EpIcon.vue` 为共用基础组件。使用现有 Ant Design Vue 按钮/标签，通过统一样式映射；没有引入第二个 UI 框架或变更 lockfile。

### 正确性增补

共用 createCase action 保留未确定请求的幂等键。收到成功创建响应但路由被阻止/懒加载失败时，保留 accepted Case ID，重试仅导航，避免重复病例。已知任务刷新独立于当前任务轮询，保留每 ID 观察时间；会话重置立即 abort 并丢弃迟到结果。未知状态使用 own-property 检查，避免 constructor 等继承属性被当成状态。

### 明暗、响应式与可访问性

102张 Phase 7 截图覆盖1440/1512/1728/1280/1024/768/390px与两种主题；所有检查通过全页无水平溢出，病例表允许局部滚动。移动菜单保留焦点循环、Escape和宽屏 inert 解除；保留200% CSS放大回归（不是原生浏览器缩放认证）。语义表头、标签、可见focus、动态页面title、skip navigation与OS reduced-motion均保留/补充。最终补验已记录密度实测、对比度抽样与指定视口高度，结果见下文。

## 与旧界面的主要区别

- 登录默认同一路由 `/`，由介绍型“工作台”升级为病例优先的工作概览；安全深链接仍优先恢复。
- 病例从普通分行列表改为可展开完整ID的语义表格，有范围明确的搜索/过滤/密度控制。
- Case 三栏 CT工作区，Result 工具从画布上方移到右侧；暗色只改变界面。
- 新增可诚实降级的任务集合、服务状态、显示偏好与404；不引入虚构RBAC。

## 能力与开放事项

当前接口已实现能力及 A/B/C/D 分类见 [能力矩阵](FRONTEND_CAPABILITY_MATRIX_V1.md)。Backend提案见 [能力请求](BACKEND_CAPABILITY_REQUEST_V1.md)。全局统计、任务集合、授权角色、遥测、审计feed仍缺失。完整分析历史无证据时保持未知。

## 部署验收建议

建议作为本地前端候选进入**独立部署验收准备**。不能据此直接上线或宣称生产可用：仍需负责人授权的真实账号/Backend链路、既有 /mvp/ 环境、回滚与缓存兼容检查，以及后续可用环境中的推理验收。真实 GPU E2E 本轮 NOT_RUN，未连接GPU，当前GPU状态未知。历史 D10/CPU-GPU数值门和临床有效性不因UI工作改变。

本轮没有 push、merge、deploy，没有修改 Backend API contract、Worker protocol、Stage B、Dataset、D10、FrozenBaseline、独立 Landing/Review/Aid。

## 逐阶段提交与验证

| 阶段 | 提交 | tests | build | 浏览器/截图 |
|---|---|---|---|---|
| 0 | `5e1856088f8faa70791eef6acdc9db55f7aa0c80` | 85 PASS | PASS | 18场景基线/1张归档截图 |
| 1 | `43af27a4bb9fcf461fae63c23b1f405a23703bda` | 85 PASS | PASS | Shell / 2张 |
| 2 | `95629630c8c3ea91a9b67c5a775e761952bcfeb3` | 99 PASS | PASS | Dashboard / 4张通过截图 |
| 3 | `e03e877754af4ea8d8e292c8d01c2e085343c747` | 107 PASS | PASS | Cases/Case / 4张 |
| 4 | `588a6f3d7c9ab631eda8cbf4bbea158f789729cc` | 107 PASS | PASS | Workspace/Result / 8张 |
| 5 | `ace3cdb4e8ddebd445bfb644c7cbed23b4bb8a3d` | 107 PASS | PASS | Jobs/System / 10张 |
| 6 | `70cae0611ffc9d9aae576183d9c0f4d8825143f8` | 107 PASS | PASS | Login/Preferences / 8张 |
| 7 | `a05f8e6abf8fc422ef23ccfe444f9cf330433bf9` | 121 PASS | PASS | 响应式明暗 / 102张 |
| 8 | `e8eec4241d2a33ff8995461ed2cc920840962b4a` | 121 PASS | PASS（/mvp/） | 26场景 / 143张最终截图 |

Phase 8 为最终回归、密度实效修复、窄屏上下文压缩、补充验收工具与交付文档。最终提交 SHA 在负责人交付消息及 Git 中提供；各次小提交保留，不 squash/rewrite。

## 最终执行结果

环境：macOS、本机 Chrome headless / SwiftShader、Node v26.5.0、npm 11.17.0、lockfile 固定依赖。仅回环地址5198；所有业务 API 是 `SYNTHETIC_API_FIXTURE` 拦截，DICOM为本地生成棋盘像素，Viewer实际解码渲染。不是患者影像、真实账号或后端推理证据。

| 检查 | 实际结果与证据 |
|---|---|
| `cd frontend && npm test` | **121/121 PASS，18 specs**；`final/tests.txt` |
| `cd frontend && npx vue-tsc -b` | **PASS**，退出0；`final/typecheck.txt`（成功无输出） |
| `cd frontend && VITE_PUBLIC_BASE=/mvp/ npm run build` | **PASS**；`final/build-mvp.txt` |
| 全链浏览器与新增交互 | **26 场景 PASS**；`final/browser-acceptance.json` |
| 截图 | **143 张最终截图**，其中完整明暗页面矩阵/登录/异常/几何与交互证据 |
| 视口 | 1440×900、1512×982、1728×1117、1280×800、1024×768、768×1024、390×844；旧回归另含360px和200%CSS放大 |
| 几何 | 6组非方形/旋转/不等像素间距/缩放/平移/resize，所有标记≤1 CSS px |
| 首页 | 1440×900有6条完整行；未请求DICOM/Result/heatmap；已知与全局范围分开 |
| 密度 | compact **47.14px** / standard **52px** / comfortable **60px**（长内容仍可撑高） |
| 明暗与减少动态 | 偏好刷新持久化；系统主题实时变化；OS减少动态与用户减少动态均生效 |
| 对比度 | 5页×2主题可见文字抽样无失败；最小值 light **5.481** / dark **6.156**。不是完整WCAG认证 |
| Viewer稳定性 | 主题切换CT canvas字节不变；连续10次尺度切换同一canvas/engine；缓存17,920B不增；resize后30秒空闲无持续重绘；离页engine/cache均释放至0 |
| 错误/会话 | 失败Job、坏PNG、过期DICOM、403、离线、空列表、404、账号切换/跨标签失效、迟到请求与POST幂等通过 |
| 页面错误/外部请求 | **0 / 0** |

初次新增Dashboard测试缺少Pinia测试安装，已补齐测试依赖。旧浏览器工具两处断言依赖英文几何标签与完整可见ID，现按对应中文状态/可访问完整ID更新；安全与几何条件未移除。新建成功后的导航恢复与密度不生效是真实发现并修复的问题。一次独立typecheck命令从根目录启动而缺tsconfig，改在frontend目录执行后通过。

构建保留基线已有 Cornerstone/codec 的大 chunk 及 fs/path/url externalization 警告；未为UI任务升级依赖。Dashboard自身chunk约3.36KiB gzip，入口公共chunk约62KiB gzip；没有增加首页医学影像预取。网络和渲染性能结论仅限本次固定合成场景，不是临床硬件容量认证。

## 截图入口

全部为实际Vue界面截图，业务数据与CT均为合成测试fixture。

- [Dashboard desktop](clinical-canvas-evidence/final/clinical-dashboard-light-1440.png)
- [Dashboard dark](clinical-canvas-evidence/final/clinical-dashboard-dark-1440.png)
- [Dashboard mobile](clinical-canvas-evidence/final/clinical-dashboard-light-390.png)
- [Cases desktop](clinical-canvas-evidence/final/clinical-cases-light-1440.png)
- [Case detail / CT workspace](clinical-canvas-evidence/final/clinical-case-detail-light-1440.png)
- [Result workspace](clinical-canvas-evidence/final/clinical-workspace-result-light-1440.png)
- [System status](clinical-canvas-evidence/final/clinical-system-status-light-1440.png)
- [Login](clinical-canvas-evidence/final/clinical-login-light-1440.png)
- [任务详情](clinical-canvas-evidence/final/clinical-job-detail-light-1440.png)

完整修改文件见 [变更清单](CLINICAL_CANVAS_CHANGED_FILES_V1.txt)。输入附件SHA-256及受保护源码不变证据见 `clinical-canvas-evidence/source-provenance.json`。

## 已知限制

1. 本轮没有真实账号/服务器/GPU E2E。测试证明前端控制与渲染链路，不证明当前线上服务可用。
2. 当前API无法支持全局统计、权限管理、GPU/Worker/存储队列健康、完整活动历史；界面已诚实降级。
3. Viewer现有ResizeObserver实现保持不变；本次观测无循环，未将有限场景结果扩展为所有设备无性能问题。
4. 原生屏幕阅读器、Safari/iPad硬件、原生浏览器200%缩放及临床医生3秒扫描可用性研究未执行。移动端保证病例/状态/任务可用，不保证完整阅片体验。
5. 依赖构建警告仍在；科研数值门、临床有效性和生产准备边界不变。
