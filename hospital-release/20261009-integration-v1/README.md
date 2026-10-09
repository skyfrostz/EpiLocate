# 医院展示集成交付候选｜2026-10-09

负责人：钟佳桦；首席算法工程师通过总控汇总，项目负责人在当前沟通会话决定 PASS、CONDITIONAL PASS 或 NO-GO。
计划 10 月 13–14 日完成真实流程验收及选版，10 月 14 日最终冻结，10 月 15 日展示。
本目录目前是版本化集成候选，不是已批准、已部署或已临床验证的医院版本。

## 当前交付

- [manifest.json](manifest.json)：模型/算法状态、默认模型空缺、资源及依赖快照。
- [ACCEPTANCE.md](ACCEPTANCE.md)：实际测试及八项医院验收状态。
- [DEMO_AND_ROLLBACK.md](DEMO_AND_ROLLBACK.md)：展示与回退操作步骤。
- [INTERFACE.md](INTERFACE.md)：侧车契约、空间链、适配器义务与上游边界。
- `evidence/`：仅合成测试命令、环境、日志及文件 SHA，不放真实 CT、患者级标注或权重。

正式真实数据只通过总控发布的 DATA-EVAL `data_delivery_v2.json` 消费。
三例 train / 715 SOP 的本地小试授权不构成医院 allowlist 或对外展示授权。
INTEGRATION 不创建第二份 allowlist、授权收据、GT 或标签定义。
本交付没有运行真实 CT，没有新增前端页面，没有远程计算或部署。

## 算法对照入口

从本工作树根目录使用现有 `.venv` Python：

```sh
PYTHONPATH=research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.hospital_release --manifest hospital-release/20261009-integration-v1/manifest.json
```

这是本地只读 CLI，对照版本、证据类型及准入缺口。现有前端功能保持原样。
`hospital_release.dispatch_selected` 是最小调用接缝：无新 flag 时使用原 handler，回退返回原协议结果；尚未安装到 Backend/Worker。
真实新算法 handler 仍需总控转交精确代码/模型版本及空间资产后绑定。不要把“接口可调用”写成“真实算法已完成应用接入”。

## 正式交付边界

最终交付须以实际受测提交、数据与模型手交接 SHA、版本、配置、预算、日志、三次真实演示、预计算及录屏证据更新 manifest。
当前默认医院模型为 `null`，真实端到端 `BLOCKED_BY_DATA_HANDOFF`，最终冻结 `NOT RUN`。
验收门禁只是检查记录的一致性与完整性，不自行授予临床有效性或项目负责人批准。

10 月 14 日由首席算法工程师汇总本地路径、Git SHA、验收摘要及未完成事项；由钟佳桦审阅批准。没有自动发送、上传或医院服务发布。
