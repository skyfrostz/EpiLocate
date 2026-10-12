# R76 医院版本集成验收报告

## 结论

R76 的 E2 v5 目标元数据接缝和 F0 v4 已保存结果消费接缝已实现，并通过本地生成数据的后端、前端与构建检查。此结果只证明被测接缝能保存、刷新并拒绝绑定不一致的生成结果；真实 CT 端到端、医院展示验收和临床验证均为 **NOT RUN**。医院冻结仍为 **NOT RUN**，展示材料用途等待负责人决定。

基础演示默认候选仍为已保全的 FrozenBaseline/v16。E2、F0 不会自动启用或替换它。E1 未在本版本注册，F1 未完成。

## 源与契约

- 工作树：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`
- 分支：`codex/epi-next-integration-20261009`
- 开始 HEAD：`8e8b202a00ea4bc4c407e206d08b630a6dbfd566`
- 本次接缝源码提交：`fca57445fe6f82c9e9bc501b053b889928832d1f`
- LOC 目标契约 v5 SHA-256：`d852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c`
- ENC F0 接口 v4 SHA-256：`2b2e2d0ebb6e56094451baab09e969782258155bbc6cae31ee769dcac92e0467`
- 原 v16 FrozenBaseline 包、历史 A/B/C、GT-v1、旧 Occlusion16/32/64、既有 M0 路径均未修改。

## 验证证据

- `backend_v2/tests/test_research_seams_r76.py`：15 项生成测试通过，3.15 秒。覆盖 E2/F0 预计算结果经应用 Worker 测试传输后保存与重复 GET、认证、拒绝篡改后不改变原结果、E2 target 与预测类别分离、失败状态留存、F0 输入/头/缓存/坐标/有符号值/SHA 绑定。
- `frontend/src/tests/research-evidence.spec.ts`：3 项通过。覆盖 target 与预测类别区分、来源范围标识、F0 有符号数值与 bias 恒等式校验，以及结果刷新后所选粗网格层恢复。
- `vue-tsc -b`：exit 0。
- Vite production build：exit 0，输出到 `/tmp/epi-next-integration-r76-build-20261013`，未覆盖 `frontend/dist` 或旧展示包。构建保留既有 DICOM codec 的 Node core externalization 与大 chunk 提示。
- 没有读取真实 CT 像素、患者级标签、真实权重、ENC 私有结果或医院影像；没有启动 Backend/Gateway/Worker 服务、MPS/GPU 或真实算法前向，没有截图、视频、上传或部署。

## 验收范围与未完成项

| 项目 | 状态 | 证据边界 |
| --- | --- | --- |
| E2 v5 目标 schema、类别/模型绑定 | 合成 PASS | 真实 LOC 模型和真实应用 Job NOT RUN |
| F0 v4 保存结果、缓存/头 SHA、logit 重建 | 合成 PASS | 实际 F0 head/logits/cache handoff 仍 `BLOCKED_BY_DATA_HANDOFF` |
| F0 名义 native/LPS 格点正逆映射 | 合成 PASS | 非真实影像；左右、顺序、crop、resize、resample 的医院空间验收 NOT RUN |
| 结果保存/刷新/合同篡改拒绝 | 生成 API 和组件测试 PASS | 非真实服务或医院浏览器流程 |
| 六种任务状态的人机界面与失败恢复 | NOT RUN | 本次不是完整状态 UI 验收 |
| 3 次连续真实医院流程、真实预计算备份、备用录屏 | NOT RUN | 需后续获准的展示数据与实际流程验收 |
| 医院用途批准、负责人 PASS/CONDITIONAL PASS/NO-GO | NOT RUN | 本包不代表负责人批准 |

此前 R71 的只读恢复技术验收仍由原独立报告记录；它不构成本次新算法真实空间或医院视觉验收。请按 [v16 演示清单](../20261011-real-mvp-acceptance-v16/DEMO_CHECKLIST_OCT14_20261012.md) 复用既有操作说明，不重放已消耗的验收命令。
