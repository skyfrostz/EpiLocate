# EPI-NEXT F1 remaining-input 参考实现

2026-10-09 / LOCALIZATION / 本机 CPU；初始 HEAD `d2877ba1ffd3e5355c1ed8af087b46bf78d22114`。仅新增 `epi_next/residual_localization.py`、`tests/test_residual_localization.py` 和本报告／合成证据，既有 static-coarse 变体字节保持不变。无患者、GT、GPU、远程调用。

## 算法与明确的设计选择

接口：`residual_input_occlusion_3d(predict_with_map, volume, valid_mask, target, spacing_mm, config=None, fill=0., clock=time.monotonic)`；`predict_with_map(volume)` 完整执行一次模型，返回 `(1D logits, 同shape粗贡献图)`。空间轴为 ZYX，scale 单位 mm，fill 已在模型输入单位。

初次原始 baseline+map 为 1 call。两次 PCG64 固定 seed 未搜索探查使用最小尺度、实际 mask 互不相交，计 extra；**仅作诊断，不加入 candidates**。v2 中探查体素仍允许参与正式候选中心和 mask；再次入选必须另做一次完整模型调用，不复用 probe 响应或视作 cache。没有 GT 参与候选生成。

每阶段从当前剩余输入粗图选择一个最高分的未搜索中心，遍历预声明尺度，均与本阶段 baseline 比较固定 target margin。接受区域取 union；下一阶段在原始输入中用指定 fill 填充累计 union，**真实完整重算 logits 和粗图**，刷新调用计入 extra。日志同时保留原始 baseline、每阶段 baseline、input/map SHA、每次模型调用、相对阶段响应与仅作诊断的相对原始累计响应。不同尺度不强求硬交集、不强制 Top-k。若无候选，允许 empty。阶段 baseline 的固定 target margin≤0 时停止；无已接受候选返回 `NO_RELIABLE_RESPONSE/TARGET_SUPPORT_LOST`，已有候选则保留并返回 `OK/TARGET_SUPPORT_LOST`。这不代表正常CT。

默认最多3阶段、32次 extra、120秒合作式预算；刷新和失败调用均计数。达到阶段/次数/时间上限返回 `PARTIAL_BUDGET` 并保留此前候选；超时仅在 forward 之间检查，在途同步调用不能强制停止。两个探查不可完成返回 `INPUT_UNSUPPORTED` / `INSUFFICIENT_PROBE_SUPPORT`；有效域/可搜索域耗尽有显式 stop reason；数值/模型异常为 `FAILED` 并保留原始成功记录及失败 call。结果不是可盲重试的推理缓存。

## 实跑与证据

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest -q research/next-hospital-20261014/tests/test_residual_localization.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.residual_localization --output research/next-hospital-20261014/reports/F1_RESIDUAL_SYNTHETIC_V2.json
```

交互 toy：`score=4*a+2*b+3*(1-a)*c`。初始 a 遮挡后，c 的贡献和粗图峰值改变；三阶段 baseline 实测 `[0,6] → [0,5] → [0,2]`，搜索中心顺序 a→c→b，阶段 margin 响应 `[1,3,2]`；原始累计响应与阶段响应分开记录。总8 calls、7 extra，包括2 probe、3候选扰动、2 baseline/map 刷新；第三阶段到限为 `PARTIAL_BUDGET/STAGE_LIMIT`，不是假报完整搜索。7项 smoke 检查实际 PASS、退出码0，原始记录见 `F1_RESIDUAL_SYNTHETIC.json`。14项单测 PASS、退出码0，见 `F1_RESIDUAL_TESTS.txt`。

环境：既有 Python 3.11.15 / NumPy 2.4.6，macOS arm64；无 torch/GPU计算。当前 v2 源码提交和产物 SHA 见 `F1_RESIDUAL_DELIVERY_V2.json`；原 v1 JSON/测试日志/交付清单保留，不覆盖。入口不启动子进程计算，执行结束无持续任务。

## 限制

只证明剩余输入、阶段 baseline 与粗图更新的数据流和预算/异常行为。CT-FM真实模型回调、患者几何回映、真实 GT定位、医院展示验收均 NOT RUN。该模块实现完整阶段重算逻辑，不意味着已交付真实 CT-FM F1或定位准确性提高；没有缓存等价性宣称。

## v2 复核修正

算法版本 `EPI-NEXT-F1-residual-input-refreshed-coarse-v2`。原 v1 把诊断 probe 区域永久排除正式搜索，可能遗漏已探查到的真实正响应；v2 保持 probe 间不重叠，但正式搜索重新允许该空间，每次另做完整调用。新增唯一信号恰好落在第一个 seed probe 中心的回归，确认正式候选仍发现它，并在下阶段 target margin 归零后停止。另测初始 target margin≤0 时只进行1次 baseline call；无候选和 `TARGET_SUPPORT_LOST` 不作正常CT解释。

17项单测 PASS（`F1_RESIDUAL_TESTS_V2.txt`），7项 smoke 检查 PASS（`F1_RESIDUAL_SYNTHETIC_V2.json`），退出码0。main 在运行前拒绝已存在输出，并使用 exclusive `open('x')` 写入以关闭竞态覆盖窗口；已有文件字节不变的回归通过。原 v1 数值文件保持不变。
