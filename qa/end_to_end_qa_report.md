# P0 端到端集成 QA 报告

**状态：BLOCKED。** Phase A 固定算法提交的真实 HTTP → Gradio 旧入口链路已通过，不能替代前端、后端共同集成后的完整浏览器验收。

| 范围 | 状态 | 依据 |
| --- | --- | --- |
| Mock QA | PASS | 固定提交单元测试确认 `source=MOCK` 和警示语 |
| Real Algorithm QA | PASS | 21 项测试、golden vector、三尺度独立重算 |
| Backend API QA | FAIL（局部） | 31 项独立 HTTP 探针 PASS；资产权限 QA-BE-001 FAIL |
| Frontend QA | BLOCKED | 前端固定提交未提供 |
| End-to-End QA | BLOCKED | 后端、前端和 integration 固定提交及统一环境未提供 |
| 科研冻结完整性 | PASS | 测试前后 161/161 哈希一致 |

当前前端和后端分支的 HEAD 仍为统一算法基线，工作区均有未提交改动；不存在可测试的固定 integration commit。需要集成负责人提供三份固定 SHA、启动方式、统一测试环境以及 Bearer Token 启用策略；后端负责人解决或明确阻断 QA-BE-001 的资产授权缺口。随后从干净集成检出运行真实 DICOM → 病例 → 分类 → Occlusion Job → 三尺度热图 → Gradio 页面完整链路，并复查错误、刷新、断网与冻结哈希。

**P0 总体验收要求：当前不满足。** 不输出整个 P0 系统最终通过的结论。
