# DATA唯一三SOP应用派生交接

本轮MVP_LOCAL已获批准：总控申请SHA `2dcc61df10fb2be0964dc4e0e0797e8f2d2c874367026b9a909e66fdc4f35e12`，owner记录SHA `4a4e9cb141a689533498acdb1d2c77b83222a9a1bad15f9c210b15c7698af9a3`。DATA独立生成，不需等待模型接缝；INTEGRATION不发布第二份allowlist。范围仅既有prepared_delivery三条case_index1/2/3中原固定SOP；不选新病例/新切片，不用封存集，医院展示未批准。

固定引用：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/research/next-hospital-20261014/.local/phase2/first-real-e1e2/prepared_delivery.json`；SHA `b85eaf6c78d1547e2aa4b93458734f533d34be5de1ed056fd152c30b92ebaa99`。其中records给出原source_ct_path/source_ct_sha256/source_sop_uid及Study/Series、切片索引；只按原三条对应，不再枚举715 SOP。原数据只读；派生物放DATA获准私有本地目录。

现有Backend v2与FrozenRunner联合必要约束（不能改协议迁就上传）：

- 常规单帧CTImageStorage、Modality CT、MONOCHROME2，不得LOCALIZER；Rows/Columns各2–4096，总像素≤16777216，单文件≤20MiB。
- 清空或去除非空字段：PatientName、PatientID、PatientBirthDate、AccessionNumber、InstitutionName、ReferringPhysicianName、StudyDate、SeriesDate、AcquisitionDate、PatientAddress、StudyDescription、SeriesDescription、ImageComments；去除所有private tags（含嵌套）。不把移除字段的原值写进交付摘要。
- PatientIdentityRemoved=`YES`，BurnedInAnnotation=`NO`，去标识声明不得凭空写成像素无身份信息；DATA做本地脱敏检查并留痕。
- 保留原像素值、Rows/Columns、BitsAllocated/BitsStored/HighBit/PixelRepresentation、PhotometricInterpretation、RescaleSlope/Intercept；保留PixelSpacing、IOP、IPP及原生空间/切片身份映射。不裁剪、resize、重采样或改变window/preprocessing语义。
- 使用既有本机decoder可读的TransferSyntax；如必要仅无损重编码且验证解码像素等值、空间不变，单列转换与SHA，不能静默改变数据或安装正式环境组件。

建议唯一交付ledger使用`schema=EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V1`，含`prepared_delivery_sha256`、`owner_scope_sha256`（上列总控申请SHA）、`hospital_display_authorized=false`及按case_index1/2/3排序的`records`。每条至少：`case_index`、派生绝对`path`、`sha256`、原`source_ct_sha256`、原SOP/Study/Series对应、原/派生解码像素SHA、`pixel_values_equal=true`、`native_geometry_equal=true`、`deidentification_checked=true`、去标识/重编码操作清单（不含原敏感值）。UID如需更换，保留获准本地映射，摘要只给ledger路径/SHA。

请由DATA经总控发布ledger实际路径和SHA。INTEGRATION只消费该交付，核对原3条及派生SHA，真实运行仍等待总控依序dispatch（P1后MVP）；本交接不授予医院受众/上传/部署权限。

## 10月11日总控补充：烧录像素 UNKNOWN

DATA已确认原3 SOP均缺BurnedInAnnotation；缺字段保持UNKNOWN，不能静默填NO，也不能只依据header去标识宣布像素通过。真实上传ready继续BLOCKED，等待负责人在获准本机环境逐图核查DATA复核页及精确SHA。INTEGRATION不复核、生成或代签记录。

消费接缝需要每条派生记录关联`burned_in_pixel_review={path,sha256}`，其正式逐图记录可映射为`status=PASS_NO_BURNED_IN_IDENTIFIERS`、`inspection_mode=HUMAN_PIXEL_REVIEW`、`case_index`、`source_ct_sha256`、`derived_pixel_sha256`及实际`reviewer/reviewed_at`。这只是集成字段要求，当前没有真实人工PASS记录；若DATA正式格式不同，由总控交接后实现字段映射，不创建第二份批准或allowlist。已批准的3 SOP/96批前向scope保持有效，满足数据门后仍需总控唯一dispatch。
