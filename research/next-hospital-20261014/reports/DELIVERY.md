# EPI-NEXT｜2026-10-09 本机开发交付

**已完成真实 Preflight、四线隔离开发和本机数值验证；尚未建立真实患者病灶定位改善证据。**

负责人钟佳桦；本轮依用户选择不启动 GPU。主控分支
`codex/epi-next-integration-20261009`，工作树
`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`。
固定受测源码：**`8aa5138a2b51b292eb5b8762f4d908ceb493d29d`**。
该提交在干净状态下完成以下验收；之后只补充文档及运行产物。

## 实际验收

**137 项测试 PASS；单命令 8 个步骤全部退出码 0。**

| 项目 | 实际结果 | 证据边界 |
| --- | --- | --- |
| 数据核对 | 186＝130/28/28；开发 GT 61患者/811 SOP，哈希匹配 | 标签与 collection 完全对应；临床语义未独立核验 |
| E1 | 固定target margin；真实旧权重+合成图输入，8个响应候选 | 数值执行成功，不是患者定位准确率 |
| E2 | 全logits SPI/层级排除/CPF/PSMI独立变体；两个尺度CPF可行，最终NO_RELIABLE_RESPONSE、0候选 | 原因NO_MULTISCALE_SUPPORT；没有强制输出候选，不是作者论文复现 |
| E1/E2 实跑 | 相同旧权重，固定100轮Mask预算、两尺度一阶段；合计219次调用，4.620599秒 | 合成输入，无专家GT，无临床性能比较 |
| CT-FM | 官方权重严格加载；CPU `[1,1,32,32,32]→[1,512,2,2,2]`；GAP512 | 只有小尺寸合成输入；三例完整CT NOT RUN |
| CT-FM成本 | 加载0.361893秒、推理0.079812秒、整进程峰RSS1,285,603,328字节 | 不是GPU显存；不可外推完整病例或96×160×160分块 |
| F1 | 剩余输入重算、baseline/粗图更新；8总调用/7额外/2探查；PARTIAL_BUDGET | 合成交互模型；真实CT-FM与原生坐标接入NOT RUN |
| 评价/几何 | 共同预算、不完整GT限制、患者分母、LPS往返及异常拒绝测试通过 | 未生成真实CT标注叠加 |
| 结果保全 | 本地不可覆盖收据、哈希核验、未知/冲突拒绝、计算前对账 | 不代表远端receiver、持久GPU队列或医院E2E验收 |

所有新代码位于 `research/next-hospital-20261014/`。主仓库、原A/B/C、
GT-v1、封存测试、既有服务和前端保持原状态。没有push、merge或deploy。

## 文件、命令与哈希

- [状态表和完整Preflight](PREFLIGHT.md)
- [机器可读交付收据](DELIVERY_RECEIPT.json)：源码SHA、8步骤退出码、全部产物SHA及运行数值。
- [完整本地命令/环境/日志收据](../.local/verification-committed-v1/receipt.json)
- [实际输入根目录与权重路径](../.local/preflight_paths.json)：本地ignored文件，无逐患者记录。
- [最终原始数值](final/)：baseline E1/E2、真实CT-FM、残余F1、合成head及定位实验。
- [单命令入口](../run_cpu_checks.py)；[使用说明](../README.md)。
- [医院独立标注与AI辅助修订流程草案](../HOSPITAL_EVALUATION.md)。

从本工作树执行的基本复跑命令（使用全新输出目录）：

```sh
/Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python research/next-hospital-20261014/run_cpu_checks.py --output research/next-hospital-20261014/.local/new-verification
```

上面的基本命令不自动下载或使用权重。此次含两种真实权重的完整运行命令、
隔离依赖路径与每个子命令都在本地收据中；可按其参数使用新输出目录复跑。

完整收据SHA256：
`e83ba9e260721bc8246f3f4c183dea60c9169db9733c8860e0318b82495e05a4`。

最终真实CT-FM数值JSON SHA256：
`8579341982901f20933aeb64862fbe9840e85edd7a0ae5818b3d26788269e21b`。

最终E1/E2数值JSON SHA256：
`796b266201d23339cb89846a0bff018d27af15b4cbe70d43fdd8d68261380b88`。

CPU环境：Python3.11.15、Torch2.14.0、NumPy2.4.6，Mac ARM64/24GiB。
CT-FM额外使用隔离MONAI1.5.1/safetensors0.5.3；未改正式CUDA环境。
已保留首次权重下载超时和已修正的测试断言失败。全部本轮计算进程已退出。

## 下一阶段闸门

1. 锁定准确的非封存三例/开发allowlist和新任务标签来源；现有proxy不能改称病灶标签。
2. 实现原生DICOM三维预处理、变换ledger、GT-vNext多对象映射及可检查的真实叠加。
3. 在明确批准的设备/时长内完成三例全病例资源与空间测试；通过后才进入真实F0/F1。
4. 锁定患者、共同支持域、指标和参数，执行E1/E2与F0/F1真实GT比较。
5. 依据实际定位证据决定医院候选；10月13日冻结、14日三次端到端验收仍NOT RUN。

付费GPU、新远程计算、封存测试和受保护资产操作继续需要单独明确授权。
当前三病例、GT-vNext真实叠加、临床标签核验、患者级AUROC/AUPRC、病灶覆盖
改善、医院版本冻结均未完成。本轮没有建立定时或无人值守后续任务。
