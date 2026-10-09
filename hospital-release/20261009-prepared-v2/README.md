# 三真实切片 prepared input 增量交付

这是开发小试输入交付，不是医院展示冻结，也不是模型准确率验收。旧 `20261009-integration-v1` 包及收据保持原字节，当前状态由本增量记录说明。

DATA v3、原三例3train/715SOP与总控锁定切片 `111/121/123` 已消费。原始DICOM完整HU窗/resize/normalization路径已执行，三份prepared input与native inverse为 `READY_FOR_LOCALIZATION_CPU`，不再依赖DATA native ledger补齐。

私有消费入口：`research/next-hospital-20261014/.local/phase2/first-real-e1e2/prepared_delivery.json`。
SHA-256：`b85eaf6c78d1547e2aa4b93458734f533d34be5de1ed056fd152c30b92ebaa99`。
接收收据：同目录 `data_v3_receive_receipt.json`；SHA `22c792e26a3fce9da7ff90a27e9052d00f15a52800404268fcb89c4c08875815`。
固定执行源码：`a13bbcc90140d4d8d2ba308b54fd6ad76a400f09`，`source_dirty=false`。

消费方校验顶层SHA及 `artifacts_sha256`，按 `records[].arrays` 读取image/valid_mask/model_tensor，按 `records[].prepared_contract` 构造其已发布的Prepared2DInput，校验每例geometry SHA后使用model_to_native/native_to_model及LPS链。此处实际调用LOCALIZATION提交 `8ac99308a123bee468374fff68df4c4f1ec08414` 的Prepared2DInput.validate，未运行或重实现其E1/E2。

真实几何证据：三例源DICOM头与DATA affine比较，最大world误差均为 `5.684341886080802e-14 mm`；逆映射最大误差 `2.842170943040401e-14 model voxel`。原HU与DATA native HU逐值一致，完整RGB/ImageNet normalized tensor与旧预处理严格相等。
这证明三份输入的技术空间链，不是浏览器overlay验收、完整医院E2E或临床病灶定位验证。

支持域由总控明确为完整原模型FOV。旧流程不做padding排除；实际两例有padding tag，一例UNKNOWN，均原样保留。valid_mask为算法工程支持域，不是肺掩膜、病灶标签或padding不存在的证明。
模型fill=0位于post-resize / RGB ImageNet normalization之前的scalar图，对应原窗下界常量HU -1350；不声称该填充是临床反事实。

准备器仅哈希核对旧checkpoint，无模型forward、无训练、无MPS/远程任务；未打开GT mask资产或使用GT改选切片。原生manifest含GT元数据，接收时仅利用其中native ledger。
LOCALIZATION可直接沿总控固定配置进行本轮CPU E1/E2。最新顺序是先收敛E1数值、真实CT与DATA独立空间/partialGT证据，再决定E1冻结或带限制冻结；随后推进E2重点研究与公平比较。已锁单阶段E2首轮可完成，新的多阶段实验等待E1可信基线决定。不因科研优先级自动决定医院默认算法。
医院接口接入、真实结果/保存恢复、三次演示、录屏及项目负责人批准仍未完成。3D CT-FM线独立推进，未降优先级。
