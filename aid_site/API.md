# API v1 契约

基础路径：`/api/v1`。已登录后可获取机器可读的 [`/api/v1/openapi.json`](/api/v1/openapi.json)。下列类型是后续对接设计，**当前没有影像或算法后端**。

## 认证与状态

全部业务接口和能力查询要求站点登录会话。未登录返回 HTTP `401`、`code=UNAUTHENTICATED`。修改类请求还需将 `GET /api/v1/capabilities` 返回的 `csrf_token` 放入 `X-CSRF-Token` 请求头；缺失或错误时返回 HTTP `403`、`code=CSRF_REJECTED`。只接受同源 `Origin`。Cookie 使用 `Secure`、`HttpOnly`、`SameSite=Strict`。

| 方法 | 路径 | 当前响应 |
|---|---|---|
| GET | `/capabilities` | HTTP 200；列出能力状态与当前会话 CSRF 令牌 |
| POST | `/images` | HTTP 503，`NOT_CONNECTED` |
| POST | `/analysis-tasks` | HTTP 503，`NOT_CONNECTED` |
| GET | `/analysis-tasks/{task_id}` | HTTP 503，`NOT_CONNECTED` |
| GET | `/results/{result_id}` | HTTP 503，`NOT_CONNECTED` |
| POST | `/doctor-feedback` | HTTP 503，`NOT_CONNECTED` |

占位响应示例：

```json
{
  "code": "NOT_CONNECTED",
  "status": "NOT_CONNECTED",
  "message": "该能力尚未接入；当前不接收或保存影像及业务数据。",
  "capability": "image_submission"
}
```

当前所有业务占位路由不读取请求体、不创建任务、不保存反馈。Nginx 请求体上限为 64 KiB，真实影像上传不受理。

## 后续对接类型

类型定义以 `aid_site/schemas.py` 中的 Pydantic 模型为准。

| 类型 | 字段 | 含义 |
|---|---|---|
| `ImageMetadata` | `image_id`, `modality`, `format`, `width`, `height`, `slices`, `deidentified` | 去标识影像元数据；没有患者标识字段 |
| `AnalysisStage` | `PREPROCESSING`, `CLASSIFICATION_OCCLUSION`, `COARSE_LOCALIZATION`, `LIME_REFINEMENT`, `CLINICAL_REVIEW` | 预处理、分类遮挡、粗定位、LIME、临床复核阶段 |
| `AnalysisStatus` | `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `NOT_CONNECTED` | 任务状态 |
| `AnalysisTask` | `task_id`, `image_id`, `stage`, `status`, `created_at`, `updated_at` | 异步分析任务 |
| `LocalizationRegion` | `region_id`, `stage`, `geometry`, `points`, `slice_index`, `stability_score` | 坐标归一化至 `[0,1]` 的候选定位区域 |
| `Explanation` | `method`, `summary`, `region_ids`, `contribution`, `comparison_only` | 定位解释；`GRAD_CAM_PLUS_PLUS` 仅为对照或降级方案 |
| `DoctorCorrection` | `region_id`, `action`, `corrected_region`, `note` | 医生确认、添加、删除或调整区域的记录 |
| `DoctorFeedback` | `result_id`, `corrections`, `clinical_alignment_score` | 医生反馈包 |

后续接入时，影像格式解析、脱敏校验、授权与伦理审批、数据隔离、真实任务生命周期、模型版本和审核记录都需要单独设计与验收。当前契约不会将它们伪装成已实现能力。
