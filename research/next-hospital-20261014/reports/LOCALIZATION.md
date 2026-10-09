# EPI-NEXT LOCALIZATION 本机交付

日期：2026-10-09，Asia/Shanghai。负责人：钟佳桦；实现执行者：本轮 LOCALIZATION Codex 子代理。Worktree：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-localization`；分支：`codex/epi-next-localization-20261009`；开发前 HEAD：`169bb42b94365ae0eeccae10e425fa1e167f3ce1`。初始 tracked / untracked / ignored 均无改动，未发现 `.codegraph/`。只在新研究模块及本工作树日志写入。

## 已执行范围

- E1：固定 target 的 `target logit - max(non-target logits)` 差值；输出原始前后 logits、概率差、margin 差、argmax、候选位置和有效像素数。不改历史 A/B/C；不强制 Top-k；并列位置按数组索引确定顺序，负/零响应不接受。当前 E1 按每个尺度的不重叠网格遍历，不能静默称为旧滑窗协议复现。
- E2：独立连续 Mask 参考变体，实现全 logits L2 一致性（论文 eq4）、L1 Mask 损失（eq5/8）、nearest 刚性逐级排除（eq6/7）、可行轮次内最大峰值差 CPF（eq9-11）、按其他尺度计一票的 PSMI（eq12-15）。冻结分类器参数但开启输入梯度；退出恢复原参数 requires_grad 和各模块模式。CPF 不可行返回 `NO_FEASIBLE_MASK`。
- F1 static-coarse/original-input search-exclusion variant：可注入三维预测器的 **输入级**遮挡；每次完整原始输入重算，无 feature cache。只从未搜索中心生成粗图提议，已接受区域不参与后续搜索；不把所有尺度硬取交集。最大 3 阶段、32 次额外 forward、120 秒合作式时间预算；到限保存部分结果并 `PARTIAL_BUDGET`。同步 forward 在途无法强制打断，因此 120 秒不是硬墙钟保证。
- 两次固定 PCG64 seed 的探查优先运行：从有效、未搜索体素均匀抽中心，使用最小物理尺度，裁去已搜索体素，计入额外 forward。实际有效域无法满足两次时为 `INPUT_UNSUPPORTED` / `reason=INSUFFICIENT_PROBE_SUPPORT`，不伪称可靠无响应。失败 forward 计 attempted calls，但不计 completed probes。
- 算法入口不接受 GT。体素索引均为模型空间 `z,y,x`，2D 为 `y,x`；原生 DICOM 回映由独立几何契约负责，当前未声称患者原生 overlay PASS。

## 论文核对与差异

读取用户本地 HSPI PDF，并渲染第 4 页核对 eq11/13/14/15。论文 DOI：10.1109/BIBM62325.2024.10822166。当前工作树文件名检索未找到获准 HSPI 作者源码；此结果不能证明其他私有目录没有源码。

本实现不是作者代码复现。Projected Adam、Mask clamp `[0,1]`、active peak 限制、并列峰拒绝、有效域保护、较小网格和有限轮次为本轮显式变体。论文设置为 10 个网格（7..16）、15 阶段、10000 轮、η=.01、λ=1、α=.005、β=.08、benchmark 第一个尺度、ε=8；合成 smoke 使用 2 个网格、2 阶段、60 轮和特设合成 CPF 约束，仅为可执行性验证，不构成论文结果复现或临床参数选择。E2 始终比较全部 logits，没有改成固定 target margin 并冒充原版。

## 实跑命令

在上述 worktree 执行：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest -q research/next-hospital-20261014/tests/test_localization.py research/next-hospital-20261014/tests/test_hspi.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.localization_smoke --output research/next-hospital-20261014/reports/LOCALIZATION_SYNTHETIC.json
```

环境：Python 3.11.15 / torch 2.14.0 / numpy 2.4.6；macOS arm64 CPU，torch 单线程。没有 GPU、远程请求、患者像素、真实 checkpoint 或封存数据访问。JSON 的 checkpoint SHA 仅对应 toy 参数，不得称真实模型 checkpoint。

32 项单测最终通过；日志见 `LOCALIZATION_TESTS.txt`，退出码 0。合成 smoke 的 10 项检查通过，退出码 0：极高 logits `[0,100]→[0,99]` 的概率差 0、margin 差 1；target 在 argmax 切换后不变；E1 21 calls / 4 candidates；E2 244 calls / 2 candidates；F1 5 calls / 4 extra / 2 completed probes / `PARTIAL_BUDGET`；恒定输出无响应无候选；固定 seed 原始记录重复一致；相同输入的局部平滑 baseline 产生零响应。原始逐轮/逐候选数值、配置 SHA、输入 SHA、源码 SHA 和环境保存在 JSON。最终产物哈希与提交见 `LOCALIZATION_DELIVERY.json`。

先前一次测试为 20 PASS / 1 FAIL：合成第二信号跨网格形成并列峰，被 CPF 正确拒绝，而测试误要求两候选。改为唯一峰合成信号，并保留单独 tie 拒绝测试。一次使用系统 `python3` 修改文件被 Xcode license 阻止（未执行修改），之后使用既有 venv；没有修改系统许可或安装依赖。

## 未完成 / NOT RUN

计划中的 residual-input F1（逐阶段剩余输入 baseline 重算及粗图更新）NOT IMPLEMENTED；真实二维 checkpoint 对照、CT-FM F0 接入、三例真实 CT、原生 CT overlay、专家 GT-vNext 定位指标、患者级 AUROC/AUPRC、真实成本/显存、临床评价、论文超参数复现均 NOT RUN。合成数值 PASS 不代表真实定位提升。E2 当前无整体 wall-clock budget；受控本机调用需限制 epochs / grids / stages。F1 几何是轴对齐模型空间框，需接入已核验 native 变换才可向医院展示。无后台子进程由本入口启动，运行结束无本工作线持续计算任务。

## 2026-10-09 主控复核修正

`fixed_target_response` 拒绝 Python/NumPy bool、浮点、越界 target。对外算法状态统一为 `OK`、`FAILED`（保留 NUMERICAL_FAILURE/MODEL_FAILURE reason）、`INPUT_UNSUPPORTED`（保留支持域 reason）及既有 abstention/budget 状态；PSMI 无支持为 `NO_RELIABLE_RESPONSE` / `NO_MULTISCALE_SUPPORT`。32 单测 PASS。

当前三维算法 ID 为 `EPI-NEXT-F1-static-coarse-original-input-search-exclusion-v1`。coarse map 是调用者一次提供的静态图，所有遮挡评分始终参考原始 volume baseline，仅候选搜索域排除已接受区域。它**不是完整执行包 F1**：剩余输入重新预测和更新粗图 NOT IMPLEMENTED。不得将此原型称为 F0/F1 完整受控对照。

只读短审主控 contracts/artifacts/cli：临时合成 receipt 将 artifact_hashes 设为非空 list，reconcile_run 抛 AttributeError，已向主控报告；未写其他工作树。另指出创建新 run 目录后父目录 fsync 缺口。是否修复由主控提交证明。
