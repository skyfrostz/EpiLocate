# 2026-09-26 接口与探索性分析核验记录

本次新增文件仅在 `docs/interfaces/`、`analysis/stage1_validation_exploratory_v1/` 和 `scripts/analyze_stage1_validation_exploratory.py`。本地 `main` 原有未提交修改未重置、合并或覆盖；远端 B 分支和远端主线只读审查。

| 检查 | 结果 |
| --- | --- |
| 运行 `.venv/bin/python scripts/analyze_stage1_validation_exploratory.py` | 成功，生成报告、8 个 CSV、2 张 PNG、provenance；只读 validation 汇总和 val manifest |
| 对照正式 `result_freeze.json` 的 161 项 SHA-256 | 161/161 一致，0 mismatch |
| 冻结 Stage 1 Protocol、Config、Baseline checkpoint SHA-256 | 均与 `protocol_v1_freeze.json` 一致 |
| `.venv/bin/python -m pytest -q tests/test_occlusion_runner.py` | 8 passed |
| 从 B 分支 `f153b9b` 导出的隔离临时目录运行契约、job、Mock 推理单元测试 | 5 passed；未改动同事分支 |
| OpenAPI 3.1 规范与四个 synthetic JSON 示例 | `openapi-spec-validator` 通过，`jsonschema` 验证通过 |
| 脚本 `py_compile` 与 `git diff --check` | 通过 |
| 交付文本标识检查 | 探索性输出和 synthetic fixture 未包含数据集患者编号、DICOM UID 或本机绝对路径 |

未执行 B 分支 HTTP/Gradio 服务器集成测试：该分支尚未集成当前主线，当前环境也没有安装 Gradio，真实算法 adapter 不存在。本次 OpenAPI 是目标契约，不代表这些路由已实现；P0 Mock 路由的状态以 B 分支源码和上述 5 项单元测试为准。没有读取 formal test pixels，没有进行 formal test 推理、重新训练、Robust、LIME 或 Grad-CAM。
