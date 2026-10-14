# 64-only Revision88 工程排障与新技术请求

状态：**工程修复及生成回归 PASS；修复后真实三SOP技术执行 NOT_RUN，待新精确批准。** 原工作树/分支保留，代码提交 `0e44ac5adfc4dcc58e1eeb829b39d35e25d17de7`。本报告只覆盖 INTEGRATION；R18由ENC独立处理，Ridge保留前次结果、不调参。

## 证据与根因边界

两次旧真实 receipt 均保留 FAILED_OR_PARTIAL：原01仅服务/登录；02另保存首例Result、仅64与DICOM SHA断言，随后 CURRENT_IMAGE_READINESS_TIMEOUT，renderSequence/overlaySequence=0、flows=[]。旧收据未保存完整布局、静态请求或解码内部观测，**旧真实根因仍UNKNOWN**，不回填PASS。

实际生成生产构建复现了一个确定的候选缺陷：`qa/demo64_build.py`把Vue `<template v-else>`替成无指令 `<template>`；它成为隐藏的HTMLTemplateElement。生成Result路由、API、Backend/Gateway/HTTPS及实际Cornerstone engine已加载当前影像，但canvas零布局，ready文字hidden、联合readiness失败。修复仅让候选模板仍为Vue fragment：`<template v-if="result">`；未改原前端、模型、解码算法或空间数学。该机制与旧症状相符，不等于恢复了旧现场全部观测。

生产回归另出现CSS/模块 ERR_CONNECTION_RESET/ERR_TOO_MANY_RETRIES。Python原SSLSocket.accept同步做握手，未发送TLS握手的预连接使旧edge并行请求ConnectTimeout（生成对照1.002秒）。候选edge仅增加接收队列至64、让既有handler线程在IO时完成握手；生成同场景及完整浏览器回归通过。旧`qa/local_mvp_readonly.py`不改，不新增代理/调度框架。

没有证据要求修改`core.init()`或Vue viewer初始化代码：既有core.init是同步函数；生成生产engine状态和实际事件/解码可观察。初始非空File/取消/替换等现已实际回归。未靠await猜测、延长超时或CSS强行覆盖隐藏状态来通关。

## 驱动V3

旧V2 driver、request7398099…和candidate191b47…文件保留。新V3从请求绑定的实际core chunk取模块，readiness/相机采样统一采用 `module.getRenderingEngines ? module : module.t`，不假设minified `.t`跨构建稳定。生成多入口构建验证命名导出路径，新实际候选core仍绑定原聚合chunk及SHA，支持`.t`分支。原独立DICOM IPP/IOP/spacing＋相机投影、七个固定点及0.5 CSS px容差不变。

失败时保存祖先布局、engine/current decoded尺寸、模块可用性及静态资源请求状态，诊断import限1秒；不读取像素、账号、密钥或数据库正文。primary_failure在browser cleanup之前持久化，main不再次覆盖；失败或清理失败返回2，成功返回0。旧exit0与失败receipt并存的历史不改。原decoded/render/visible nonzero canvas/current64 asset联合readiness未放宽，提示或等待时间不能建立PASS。

## 最终生成验收

| 验证 | 实际工程结果 |
| --- | --- |
| 新driver/API/预连接 | 12 passed / 2.34s；含成功、主失败、cleanup失败返回码与主失败step保存、直接16/32/其他对象/写/Worker拒绝、原DB不变 |
| 候选前端/几何 | 3＋11＝14 passed / 743ms；64-only、旧偏好拒绝、未知Result不读CT、无研究/Series/3D路由 |
| 生产构建浏览器 | PASS_GENERATED_PRODUCTION_ONLY；真实编译Vue＋Backend/Gateway/HTTPS、3生成Result/9层、刷新、范围拒绝、原独立相机空间验证，270个持久化步骤 |
| 压缩解码 | 生成JPEG Lossless SV1（1.2.840.10008.1.2.4.70）实际browser解码；SOF3/Huffman码流从零生成，无第三方或医疗样本复制 |
| 生产生命周期 | 初始File非空、replace/remove、cancel/remount、清空/旧资产、坏DICOM、core初始化失败、refresh/unmount、浏览器与三个自有服务退出通过 |
| 生成空间残差 | 最大0.0000152587890625 CSS px ≤0.5；不充当真实空间PASS |
| runtime/资源 | 生产core注册实例与viewport观测一致，worker请求HTTP200，无最终正常场景静态请求失败；坏DICOM负例错误单列。SwiftShader本机浏览器，不涉及GPU AI Node/模型 |
| 最终候选构建 | vue-tsc＋Vite PASS，21 dist文件；既有codec externalization及大chunk警告保留 |

主要命令：主仓库venv Python＋原`frontend/.local/mvp-20261011-browser-deps`，无安装。`python -m pytest -q qa/test_demo64_v3.py backend_v2/tests/test_demo64.py`；隔离生成候选中`npm exec vitest -- run src/tests/demo64.spec.ts src/tests/geometry.spec.ts`；`qa/demo64_production_browser.py --regress`读取纯生成plan；最终隔离候选`VITE_PUBLIC_BASE=/mvp/ npm run build`。各日志及270-step JSON的path/SHA在manifest。生成多入口夹具含测试生命周期页面；实际冻结候选为普通单入口构建，未包含测试页面或生成DICOM。

保留初期生成夹具依赖PYTHONPATH/绝对配置路径、导出不一致、无指令模板、TLS及刷新失败目录。不把它们计为真实重试，不隐藏失败历史。当前通过后不扩展矩阵或重复已通过未变检查。

## 新冻结对象与集中申请

- 候选：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/demo64-candidate-r88-20261014/frozen-candidate-v3.json`
- 候选SHA：`a7d3cc77d17d4bf44fd45b80ea44b35472faa3a1e2c31f8b93a18eeb6b818da0`
- 请求：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/demo64-technical-request-r88-v3.json`
- 请求SHA：`2d3d5da57a818b2b202b5fe93db632fe8fbfd1e79cb7f2487f478565575b5934`
- 新输出：`.local/demo64-technical-r88-20261014-03`，尚不存在。

绑定197个源码/旧恢复引用、21 dist、23 runtime、新driver/diagnostics/原readiness、浏览器runtime及配置；三SOP/三Result/九64资产只引用原projection b0dcd6…和唯一DATA v2 ledger bc9198…，未创建allowlist或复制真实资产。metadata-only check实际exit0，services_started=0/medical_arrays_read=0。源DB/真实对象正文未读，原恢复66项源/构建MATCH。旧候选/旧dist字节保留，但修复后的live源码已不同，不能拿旧candidate/许可运行新版本；历史源码仍可按原Git恢复。v16受测readonly源码/旧dist保留作为已获范围内的回退，不把未获准录屏当作可用回退。

仅申请原三SOP一次本机只读技术核验：overall180s/browse140s，原七点/0.5CSSpx，0模型/Worker/Job/上传/截图/录屏/外传，无重试；人工实际操作员才可记录否则NOT_RUN，不计最终演练/医院展示。两次旧许可均已消费。本轮没有创建owner、admission、slot或dispatch，未启动真实候选服务，未修改总控状态/两表或push。

准确确认句（文本本身不是批准）：

> 我批准新64-only技术请求SHA `2d3d5da57a818b2b202b5fe93db632fe8fbfd1e79cb7f2487f478565575b5934`，绑定修复候选SHA `a7d3cc77d17d4bf44fd45b80ea44b35472faa3a1e2c31f8b93a18eeb6b818da0`，仅允许一次原三SOP本机只读技术核验，按180秒整体/140秒浏览及原空间固定点、0.5CSSpx执行；失败停止、不自动重试，不包含医院受众、最终演练、截图、录屏、外传或模型/Worker/新Job。

## 未完成与结论

修复候选真实decode/render/三Result/九层/刷新/拒绝API/独立空间仍NOT_RUN；人工NOT_RUN、最终演练0、医院用途与录屏未批准、医院冻结NOT_RUN。普通网络允许，无GPU AI Node；不新增医院名称或场地审批。工程生成PASS说明修复可供新一次实际核验，不建立临床定位或医院放行。
