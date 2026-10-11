# 已接收的本地 MVP 快照与复用

负责人已接收 revision 47 所述三条本地真实开发流程；此接收由总控在当前 INTEGRATION 会话通知，未新建负责人签署记录。本地 MVP 状态为 `PASS_LOCAL_DEVELOPMENT_REAL_MVP`，不是“READY 未运行”。[接收与快照索引](RECEPTION_AND_SNAPSHOT_INDEX.json) 追加到现有 v16，v15/v16 原文件保持原字节。

受测 source `54ff1565f6c11a6deea873feab0a011e879528fb`，v16 交付 commit `510d387ef02d55c22f01f9cbd282137ea1274934`。实际执行发生于 2026-10-11；保存目录名中的 `20261013` 是既有命名，不代表执行日期。模型、环境、命令、预算和退出证据均沿用 v16，整理过程没有重跑模型、浏览器或录屏。

## 先查阅版本与已有证据

从当前 INTEGRATION 工作树读取 [manifest](manifest.json)、[验收报告](ACCEPTANCE_REPORT.md)、[精确运行指标](METRICS.json)和[实际命令收据](COMMAND_RECEIPT.json)。原 manifest SHA 为 `c8bcb4cc795cdafd36c93588b6d826ef8de69764e9b086618eb5b0fa038051c8`。接收索引保存原 16 个已跟踪包文件的路径/SHA，及 revision 47 的状态 SHA；不修改唯一总控状态。

以下仅检查 manifest 字节，无服务、模型、队列或像素读取：

```sh
cd /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration
shasum -a 256 hospital-release/20261011-real-mvp-acceptance-v16/manifest.json
```

权威状态可推进到下一 revision。接收索引的 revision 47 SHA 是当时消费记录，不要求后来权威文件保持旧字节。后续应由总控读取其唯一状态，不把更新后的 SHA 当成历史 MVP 失败。

## 已保存结果的位置与读取范围

结果留在原获准本地忽略目录：

- `frontend/.local/mvp-real-three-20261013-v1`：三个 case-result、96 对 admitted/completed logits 日志、27 张资产及存储对象、SQLite、浏览器收据和三张既有流程截图。
- `research/next-hospital-20261014/.local/phase2/mvp-protected-supervision-v1/hospital-mvp-three-legacy-cpu-20261011-01`：唯一执行监督和退出/恢复证据。
- `research/next-hospital-20261014/.local/phase2/mvp-real-offline-audit-v16/private-audit.json`：`artifact_inventory` 给出结果、资产副本、对象、native 输出、截图及监督文件的绝对路径和 SHA。

上述绝对路径与原文件哈希在接收索引中可追溯。对照原 `case-N-result.json` 的 `assets` 描述，按 case_index、尺度、证据类型和 SHA 找到已经保存的产物；不要按截图外观猜算法版本。响应/候选资产是 224×224 `ALGORITHM_224`，比较网格是 14×14 `COMPARISON_14`。遮挡响应不是病灶概率、专家 GT 或临床定位结论。

获准本机操作员可直接查阅现有本地结果与已保全截图，不需要触发预测、重新上传 CT 或提交 Job。影像、截图、数据库和逐病例数值仍保留原本地权限；索引不复制或授予外传权限。认证配置/密钥不属于可分享快照材料，不从旧配置导出或重用凭据。

如需核对保存数量，下面通过现有 Python 以 SQLite `mode=ro` 只查询数量；不启动 Worker、模型或浏览器，不输出患者字段：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python - <<'PY'
import sqlite3
path = '/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/frontend/.local/mvp-real-three-20261013-v1/backend.sqlite'
with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    for table in ('inference_jobs', 'inference_results', 'job_attempts', 'assets'):
        print(table, db.execute('SELECT count(*) FROM ' + table).fetchone()[0])
PY
```

原受验数量分别为 3 / 3 / 3 / 27；旧收据仍是验收依据。这是给本机操作员的可选读取说明，本次整理未再次执行数据库查询。

## 复用边界与回退

原自有服务全部退出。当前快照包含已保存产物和可追溯索引，不是正在运行的 Web 页面；本轮未建立服务恢复入口。在线恢复需总控明确服务启动范围，先保全已有数据库、对象与结果，使用读取已有结果的方式并关闭新增计算准入；不能把 [COMMAND_RECEIPT.json](COMMAND_RECEIPT.json) 的已消费任务当作恢复脚本。若不能确认恢复不会新增 Job/模型调用，则继续查阅本地已保存产物，交总控处理。

默认本地版本仍为历史 FrozenBaseline 及 16/32/64 Occlusion。算法对照见 [v1 入口](../20261009-integration-v1/README.md)，回退说明沿用 [v16 演示与回退](DEMO_AND_ROLLBACK.md)。研究 E1/E2/F0/F1 的后续交付独立标记；E2 收益、F0/F1 分类头及医院授权都不是已通过本地 MVP 的新阻断，不据此重跑或撤销本地结果。

医院默认模型仍待定，医院展示 `NOT_APPROVED`，最终冻结与临床验证 `NOT RUN`。完整 Series 六项真实空间检查、正式医院 allowlist、医院配置三次演示及合格备用录屏仍是医院交付范围；负责人接收本地 MVP 不完成这些验收。原开发结果尚未升级成医院批准预计算包。快照仅索引原本地资产，不是独立异地备份。
