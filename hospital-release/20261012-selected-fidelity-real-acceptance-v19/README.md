# 独立真实 E2 selected fidelity 5F 验收 v19

2026-10-12 Asia/Shanghai；原工作树/分支。总控唯一最终dispatch bf4c0d9fddcaf5287973f858a6bc64a9a2fce20c6b233c6298afb4832d0a7b14，经新owner/准入链和原v12监督器一次执行。父源bc5e32feca002303318703f1ddc6ba73f1d8b913，原v17应用/算法源和固定binding不变。实际SUCCESS/exit0/F5/B0/update0/extra autograd0/retry0；slot completed、finished receipt SHA已对账，自有进程退出和资源恢复已确认。

完整原始logits、五对象（原图/full Mask keep/peak patch keep/full Mask remove/peak patch remove）响应、固定model class1、epoch3604/cell43、真实计数和源SHA保存在获准忽略目录的selected-fidelity.json，不复制受保护内容到Git。manifest.references给出该结果、实际command/spec、原stdout/stderr、runtime线程、runner/supervisor及新slot started/finished路径/SHA。科学结果耗时约0.294秒；父启动至退出约3.427秒、恢复约3.434秒，包含真实导入/加载/输入核验，不能用科学内层计时替代全流程。

实际Torch2.14.0 intra/inter op线程1/1，OMP/MKL/OPENBLAS均1；线程测量0模型调用，不重置原监督时钟。所有监督asset_hashes、18原source和绑定SHA逐项匹配，五份logits保全且无额外诊断forward。科学文件远低于64MiB，原supervisor仍采用独立身份/5GiB预停/6GiB采样目标及退出恢复路径，无新锁或重试。资源峰值/采样interval见manifest；九个初始TELEMETRY缺测如实保留（发生在子启动15秒允许期内），不能声称启动阶段连续遥测或绝对瞬间内存上限。

这只是固定开发case3/已选择Mask的模型忠实性实验，不是独立泛化验证、完整E2-Q收益验证、新应用流程或医院/临床验收。模型类响应概率不称病灶概率。未做新优化、E2-Q、其他编码阶段、GT选择、浏览器/应用重跑或医院展示；医院默认null、最终冻结NOT RUN。结果只交首席算法工程师汇总；未上传患者影像或推送/部署。原M0 COMPLETE、v17/v18历史包保留。不得重复执行已消耗task-key/命令，任何后续计算需要新的明确scope和总控派发。

## 目标元数据差异（不改历史）

固定ApplicationRequest.task.target_class=0，但实际五份responses.fixed_target均1。只读核对科学请求scope.fixed_target（配置SHA ab7b2df…）及handler selected_fidelity定义（SHA062eff4e…）：科学profile取原图logits argmax，再固定用于五份响应，本次原图argmax为1；调用函数不接收应用task.target_class。科学profile与实际指标目标一致，应用target字段却未同步，属于本次独立调用绑定的应用元数据差异。执行/监督SUCCESS保持，但**完整应用契约不标PASS，目标元数据一致性NOT PASS**。原binding/结果/五份logits不修改，也不重跑；日后应用适配需另行明确目标策略和版本化绑定。这不是新增E2-Q或医院验收。算法结果的详细离线解释归LOCALIZATION，本线仅对账此契约差异。

full_mask_remove严格指完整连续Mask M的互补遮挡：valid_support内x*(1-M)，valid之外保持原输入；peak_patch_remove另用peak patch补掩膜。前者不得命名full-mask-remove-peak。科学fill仍为原RGB冻结归一化前的scalar0，不改变实际扰动对象。
