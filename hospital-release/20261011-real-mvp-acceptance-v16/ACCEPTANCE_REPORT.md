# 真实本机开发 MVP 验收｜2026-10-11

结论：`PASS_LOCAL_DEVELOPMENT_REAL_MVP`。总控唯一调度的历史 FrozenBaseline CPU 单切片流程完成；INTEGRATION 对已有文件作离线核验，未启动额外模型、浏览器、刷新重算或重试。医院展示尚未获批，最终冻结与临床验证均 `NOT RUN`，医院默认模型为 null。

分支 `codex/epi-next-integration-20261009`，工作树为当前 INTEGRATION。受测 source Git SHA `54ff1565f6c11a6deea873feab0a011e879528fb`，验收整理前 HEAD `1057b03b9072029d1d3deba53801fd099fa128d1`。本包提交可通过 manifest 中的 git 路径查询定位，避免自引用 SHA。前端、FrozenBaseline、模型数学、预处理、A/B/C、GT-v1、核心协议及已绑定 READY 字节保持。

## 实际执行与保存

唯一 job `hospital-mvp-three-legacy-cpu-20261011-01`，正式 dispatch SHA `934a55fa2d0f51f3198281befa8dab2d40a262a26e757ceaaa7622cd5f9597de`，READY SHA `2d484b1915cd952b5a06d635272a01d5bfc8ccc0226eb18ba442011db1b8ab58`。完整实际命令、Python、cwd、环境、启动/结束时间与父 exit 0 见 [COMMAND_RECEIPT.json](COMMAND_RECEIPT.json)。首个启动前 metadata 检查缺 PYTHONPATH 的修正记录已绑定；该检查没有模型或 dispatch，不是科学重试。

实际模型 `baseline_resnet18`，checkpoint SHA `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`；预处理 `formal-resnet18-baseline-rule-b-v1`，协议 `stage1-occlusion-instability-v1`，证据类型 `INPUT_OCCLUSION`。本次没有执行研究 E1/E2/F0/F1。原分类概率、遮挡响应、候选区域、比较网格具有各自含义，不标作统一“病灶概率”。

| 项目 | 已核验结果 |
| --- | --- |
| 前向 / 反向 / 更新 | 96 批 / 0 / 0；每例 32 批、935 图像评估 |
| 图像评估 | 2805 = 3 基准 + 2802 遮挡扰动；没有额外预测、预热或重试 |
| SQLite | 3 COMPLETED Occlusion Job、3 Result、3 SUCCEEDED JobAttempt、27 Asset、1 Worker |
| 提交身份 | 三个浏览器 Job/Result、接受 attempt、保存 JSON、源输入 SHA 一致；每 Job 一次接受提交，retry_count 0 |
| 原始数值 | 96 对 admitted/completed 日志连续且身份相同；每批 n×2 有限 logits；基准 argmax 与保存预测一致 |
| 位置与资产 | 每例 934 行，16/32/64 分别 729/169/36，行顺序对应批 logits；复制资产、数据库描述及对象 SHA 全部一致 |
| 资产坐标 | 18 张 224×224 `ALGORITHM_224` 响应/候选 PNG；9 张 14×14 `COMPARISON_14` PNG；native 输出保全 |
| 浏览器 | 三流程 PASS；无 page errors、无外部请求；LIVE_CASE、generated_model=false；医院展示授权 false |
| 保存与刷新 | 16/32/64 按钮选择断言通过；选中 64 时叠加可用与“像素校验通过”断言通过；刷新后保持 64 选择 |
| 退出 | owned-completion 所有自有线程停止、三服务已退出；父/子 exit 0；supervisor SUCCESS、slot_completed=true |

528 项离线断言通过；这是文件/身份/计数核对数量，不是新增测试套件或临床病例数。99 源/构建文件、19 既有包版本、8 实际加载 supervisor 模块及固定 dependency SHA 均相符。原始路径与逐文件 SHA 全部在 manifest 指向的忽略目录 `private-audit.json` 中；原患者影像、结果 logits、数据库、认证文件和截图未复制到 Git 包。离线核验像素解码/查看、医学 F/B/update、队列和数据库写入均 0。

## 时间与资源

[METRICS.json](METRICS.json) 保存精确数值和每例记录。浏览器三流程用时 36.0121 / 34.4746 / 34.2931 秒；受保护 case runtime 40.5578 / 33.3628 / 33.1239 秒。两者起止范围不同；第一例 runtime 含启动和模型加载。父实际收据用时 111.958330 秒，监督范围 111.749648 秒，退出至恢复 0.007055 秒。均在原总 540 / 每例 180 秒预算内。

1385 个父采样、4482 个子采样；自有进程组 RSS 采样峰 1705672704 字节（约 1.59 GiB），低于原 5 GiB 预停线。RSS 是组内逐进程 RSS 相加，共享页面可重复计数，且采样峰不是绝对峰。父间隔最大 0.179046 秒；启动期一个 TELEMETRY 缺样保留，不能宣称零缺测。没有 stop_seen 或预停触发。相对首样本 swap 增长 0；最大减最小的采样范围 25165824 字节，不能归因于本任务。run+supervision 文件总量核验时 7922747 字节，低于原 256 MiB。

supervisor SHA `84508fb7d89e26b8a529e108a642dcfb424da7b2f7f9f110a4f2ede9769dbd20`；其 10 个监督资产哈希一致，finished 精确绑定该收据。固定 dependency SHA `093e0a7fd137ae9772dd30595fe39de845a7babe9de1617d633782a02707a192`；原两个 UNKNOWN 的 started 字节不变、finished 仍缺失，未伪造解除。总控已保存所有自有 PID 无存活行的检查，收据 SHA `6f5a61ae866e38ec5052ed3a2f9803d62bf1325abc517caae616b0a5f910fdd1`；本线不再 probe/发信号或操作他人会话。

## 空间与医院验收边界

DATA v2 原三 SOP 派生交付由总控传入，ledger SHA `bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1`。DATA 的像素/原生几何/编码/window 不变、header 去标识与负责人逐图复核证据按 SHA 消费；本线没有重新标注 BIA、创建第二 allowlist 或人工查看患者截图。

本次只证明单 SOP 原生 DICOM 能在既有 viewer 流程加载，以及当前单切片 64 px 叠加的像素校验、结果读取与刷新。16/32/64 按钮状态有断言，不能扩展为三尺度逐像素独立人工验收。截图仅在受保护本地目录保全，离线只核对哈希与 PNG 头，未向模型展示像素。

左右方向、完整 Series 切片顺序、DICOM 世界坐标、裁剪、resize 与重采样的真实全流程独立验收尚未完成。单切片 `ALGORITHM_224` 对齐不等于 3D registration 或病灶定位准确性；既有合成空间测试不替代这些真实检查。空间未获验证的结果不进入医院展示候选。

本次三条连续真实**开发**流程通过，不能填写为医院受众/allowlist/冻结配置的三次展示通过。实际开发失败流程本轮未触发；失败状态证据沿用明确标注的生成回归，不伪称真实失败验收。CPU 工程闭环不建立 MPS/CUDA 数值一致性、生产部署或临床有效性。

## 模型清单与未完成事项

当前本地应用默认保留历史 FrozenBaseline 与 16/32/64 Occlusion。医院默认尚未选定。E1、E2、F0、F1 均作为独立研究版本保留，尚无本包对应的医院运行注册/验收；本包不代替 ENCODER/LOCALIZATION 的科研结论，也不把未完成算法写作已通过临床验证。

10 月 13–14 日还需总控正式交付医院数据 allowlist、已验收模型/预计算结果和六项真实空间检查；按实际冻结配置完成三次真实展示，准备有 SHA 且实际播放过的备用录屏，再由钟佳桦决定 PASS / CONDITIONAL PASS / NO-GO。开发产物已保存，但尚未升级为医院批准的预计算包。当前无合格备用录屏。本包仅本地汇总；没有 push、上传、远程 3090 或医院服务部署。
