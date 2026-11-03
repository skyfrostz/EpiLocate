# 单切片多边形标注演示（生成数据）

这个独立工作台在本机创建一张棋盘格 DICOM、临时 SQLite 数据库和两个测试账号。使用者可绘制、修订、删除及恢复多边形，服务会检查病例所有权、切片几何、修订版本和操作记录。全部标注状态为 `UNREVIEWED`，不具备训练真值资格。此演示不调用模型，不使用真实病例。

此目录与项目根的 `backend_v2/annotation_v1/`、`backend_v2/tests/test_annotation_v1.py`、`qa/annotation_workspace.py` 配套，使用项目自带的 Backend v2、Session Gateway、研究契约与本地 HTTPS 边缘服务。前端和后端使用独立于其他演示任务的新运行目录。

从项目根目录准备依赖并验证。前端依赖以本目录的 npm 锁文件为准，Python 依赖由 Gateway 的 requirements 引入：

```sh
python -m pip install -r session_gateway/requirements.txt
(cd annotation_workspace && npm ci --ignore-scripts && npm test && npm run build)
python -m pytest -q backend_v2/tests/test_annotation_v1.py
```

安装好 OpenSSL 后，从项目根目录启动：

```sh
python -m qa.annotation_workspace --run .local/annotation-demo-01
```

每次选择一个尚不存在的运行目录。启动器只监听回环接口，生成本次专用证书与随机端口，输出浏览器入口和本机凭据文件路径。使用该文件里的合成标注账号登录，关闭时在启动终端按 Ctrl+C。包含临时凭据、证书、图像和数据库的运行目录应留在已忽略的 `.local/`。历史演示桥接、真实数据读取和生产迁移不属于此组件。

本次导出使用合成输入验证了 24 个后端测试、10 个前端测试与前端构建，并在本机 HTTPS 服务检查了工作台页面、未登录拒绝、合成账号登录及标注列表读取。此范围没有包括浏览器内的手工绘制验收。
