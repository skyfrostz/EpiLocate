# Gradio 算法调试与应急演示系统（P0）

这是 B 组员使用的本地算法联调和应急演示系统。当前版本默认运行 Mock Mode，只支持单张 PNG/JPG；Mock 结果不能用于科研分析或临床判断。

## 1. 环境

- Windows 10/11
- Python 3.11 x64
- Git for Windows
- PowerShell

确认 Python 3.11：

```powershell
py -3.11 --version
```

## 2. 创建环境和安装

在项目根目录执行：

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-gradio.txt
```

脚本直接调用虚拟环境中的 Python，不要求激活环境，也不会修改系统 ExecutionPolicy。如组织策略阻止脚本，可仅对当前进程运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

## 3. 启动

```powershell
.\scripts\run_local.ps1
```

- Gradio：http://127.0.0.1:8000/gradio
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

指定端口：

```powershell
.\scripts\run_local.ps1 -Port 8010
```

端口被占用时脚本不会结束其他进程，请换一个端口。

## 4. Mock 与 Real

默认 Mock：

```powershell
.\scripts\run_local.ps1 -Mode mock
```

Real 模式预留给 A 的正式算法：

```powershell
$env:REAL_PIPELINE_MODULE = "algorithm.inference_pipeline"
$env:REAL_PIPELINE_CALLABLE = "run_case"
.\scripts\run_local.ps1 -Mode real
```

真实模块不存在时服务仍可启动，但健康状态为 `degraded`，推理接口返回 503。系统不会用 Mock 冒充真实结果。

## 5. API

- `GET /api/health`
- `GET /api/v1/contract`
- `POST /api/v1/jobs/inference`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/result`

创建任务使用 multipart，字段 `files` 为单张图片，`input_kind=image`。当前限制为 20 MiB、5000 万像素。

启动服务后运行自动 Smoke Test：

```powershell
.\scripts\test_api.ps1
```

## 6. 自动化测试

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
```

## 7. 数据与日志

- 上传规范化文件：`storage/uploads/`
- 结果 JSON：`storage/results/`
- SQLite：`data/app.db`
- 日志：`logs/`

上传文件会被重新编码、去除 EXIF 并改为随机名称。P0 不自动清理数据；确认不再需要后，可在服务停止时人工删除上述运行时目录中的内容。

本地数据库和文件默认不加密。真实临床数据必须存放在受控、加密且已经获得伦理和医院授权的设备上。本系统只接受已脱敏数据，不提供自动医学脱敏能力。

## 8. 常见问题

- 找不到 Python 3.11：从 python.org 安装官方 x64 版本后重新执行 `py -3.11 --version`。
- 页面打不开：确认启动终端仍在运行，并检查端口是否被占用。
- 返回 `REAL_PIPELINE_UNAVAILABLE`：A 的真实模块尚未接入，使用 `-Mode mock` 重启。
- 返回 413：文件超过上传大小或像素限制。
- 返回 415：文件内容不是有效 PNG/JPEG，修改扩展名无效。

按 `Ctrl+C` 停止服务。

## 9. P0 边界

当前不包括 DICOM、NIfTI、医生画笔、LAN、React、模型训练或公开互联网访问。这些功能按 P1/P2 门槛后续接入。
