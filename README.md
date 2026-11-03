# EpiLocate · 胸部 CT 空间响应研究原型

本项目研究分类模型在不同位置和尺度的遮挡下如何响应，以及有限查询预算如何影响粗定位。公开快照日期为 2026-11-03。导师路线依次检验稳定粗定位、粗区引导的局部细化和医生核验。一次受控模型执行已经通过技术验收，两臂配对先导完成 0/2，独立医学评价和生产验收仍待完成。

- [项目全面审查与六周对照](docs/review/PROJECT_REVIEW_20261103_ZH.md)
- [40 项聚合观测及各自分母](docs/review/research_aggregates.csv) · [数据字典](docs/review/EVIDENCE_DATA_DICTIONARY_ZH.md)
- [Clinical Canvas 合成交互原型](docs/prototypes/clinical-canvas-synthetic.html)。克隆后用浏览器打开该 HTML，可浏览模拟病例、调整图层、重试任务。示例使用内联矢量画面。
- [研究评价设计](research/next-hospital-20261014/HOSPITAL_EVALUATION.md) · [API v2 合同](docs/backend/backend_api_contract_phase5.md) · [Worker 协议](docs/backend/worker_protocol_v1_freeze.md)

| 目录 | 内容 |
|---|---|
| `src/`、`algorithm/`、`configs/`、`scripts/` | 冻结基线的训练、预处理、推理接口、多尺度遮挡与离线核验工具 |
| `research/next-hospital-20261014/`、`epilocate_next/` | 研究算法、空间几何、输入资格检查、协议模板和生成输入测试 |
| `frontend/`、`session_gateway/`、`backend_v2/`、`worker/` | Vue 工作台、会话网关、病例与任务 API、异步推理 Worker |
| `apps/landing/`、`aid_site/`、`epilocate_review_server/`、`gradio_service/` | 欢迎页、展示站、历史人工复核应用及调试原型 |
| `tests/`、`qa/`、各组件测试目录 | 生成输入、接口和数值合同的测试工具。部分历史集成测试需要另行准备运行环境及输入。 |

- [P2 路由、生成示例与测试](research/portable-p2/README.md)
- [R168 研究标注源码摘录及已知测试结果](research/source-excerpts/r168-roi/README.md)

## 本地使用

Vue 工作台使用 `frontend/package-lock.json`。在该目录运行 `npm ci`、`npm run build` 可生成静态资源。浏览器交互使用前面的单文件原型即可；整套工作台的登录、存储和推理还需要相应服务与运行配置。

Python 各组件的依赖清单位于相应目录。例如在虚拟环境中安装 `session_gateway/requirements.txt` 与 `pytest` 后，可从仓库根运行 `python -m pytest -q session_gateway/tests/test_gateway.py`。使用单片合成 DICOM 的测试需要先安装根研究环境的 numpy、pydicom，再执行：

```sh
python scripts/generate_p0_synthetic_vector.py docs/interfaces/fixtures/p0_synthetic_ct.dcm
```

## 发布范围

这是按文件筛选的源代码快照。输入影像、逐例记录、权重、私有运行合同、凭据、上线配置和交付包留在原保管环境。文中提供的研究数字为有限范围的历史聚合。欢迎页使用本地生成的配色代替原有的远程媒体。原型和生成测试均不能替代真实病例评价。

公开研究配置只承载模板及代码。依赖原数据主体映射的两项历史标签读取入口在此版本显式拒绝执行，数据映射与执行授权必须由其保管方分别管理。公开分支采用独立 Git 根提交，以便单独审查该分支的全部历史。
