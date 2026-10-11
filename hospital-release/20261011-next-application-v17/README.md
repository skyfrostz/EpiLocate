# 新算法应用接缝交付 v17

2026-10-11；INTEGRATION原工作树/分支。此包交首席算法工程师汇总，由钟佳桦确认医院版本。医院默认模型仍为空，最终冻结 NOT RUN，真实新算法应用验收 NOT RUN；本轮没有访问患者像素、权重、GT，没有医学模型调用、队列 dispatch 或真实浏览器运行。

- `manifest.json`：版本、代码 SHA、模型角色、现有证据与未完成项。
- `application-request.schema.json` / `handler-result.schema.json`：独立 next-1 应用契约。
- `ACCEPTANCE.md`：78项后端/Worker、164项前端、34项空间/医院契约测试的实际范围。
- `DEMO_AND_ROLLBACK.md`：实验入口、保存刷新、停止新任务及旧版回退。
- `REAL_UPGRADE_REQUEST.json`：优先 E2-Q PRECOMPUTED 零模型回放的集中申请片段，当前 NOT_READY，无批准/dispatch能力。
- `LOADING_ENTRIES.md` / `SELECTED_FIDELITY_BINDING_INDEX.json`：实际加载函数、5F固定绑定/外置派发argv及缺口；E2-Q三例共享全局预算封装ENGINEERING_NOT_READY。
- `evidence/`：生成控制与只读源码/历史包消费收据，不含 CT、GT、权重或凭据。

代码入口：`POST /api/v2/jobs/algorithm`、`worker.next_application.run_one_application`、`E2HandlerAdapter`、`E2PrecomputedAdapter`。旧 PREDICTION/OCCLUSION、16/32/64及 FrozenRunner计算路径保留；新结果使用独立kind ALGORITHM / contract next-1。默认新任务入口关闭，不自动选最新模型。

复现生成测试（既有依赖，无安装）：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps \
  /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python \
  qa/next_algorithm_application_smoke.py \
  --output .local/next-application-v4/new-generated-run \
  --loc-root /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-localization/research/next-hospital-20261014/epi_next \
  --alembic-site /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/backend/.venv/lib/python3.14/site-packages
```

输出目录必须全新。Alembic只从现存环境追加pure-Python搜索路径，应用依赖仍使用原3.11环境；没有安装或修改共享依赖。该入口不启动实际浏览器/医院服务；它通过TestClient、本地生成资产和实际LOC core验证接缝。模型为生成小函数，只有6/4/4合成调用；同源回放0/0/0。

历史M0仍为已完成的开发MVP，不倒退为未运行；16个原v15/v16文件SHA保持一致，旧source为54ff1565f6c11a6deea873feab0a011e879528fb。历史三真实流程不替代新算法M1/M2或医院配置的三次展示。只通过总控接收正式数据/模型及发布审批，本包未写权威状态，也未对其他会话发消息。
