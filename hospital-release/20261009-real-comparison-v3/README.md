# 已有真实结果本地对照交付 v3

本包仅有无患者身份的集成摘要，不包含CT、mask、权重或像素。医疗派生HTML/三张PNG留获准ignored本地目录，入口见manifest。E1=旧ResNet18固定target margin响应；E2=旧ResNet18 HSPI-inspired single-stage变体（全logits一致性），独立版本，不能称病灶概率。三例E1 OK，候选194/195/157；E2 NO_FEASIBLE_MASK，均零候选，不用替代热图填充。仅总控发布的3train固定切片，非封存、非独立测试。

读取DATA原生HU和发布NPZ/官方partialGT union，SHA/SOP/切片身份严格绑定；无模型重算、GT重算、GT过滤或新增指标。DATA独立候选逆映射PASS引用固定evaluation SHA，模型冻结由总控决策。部分参考未标注区域UNKNOWN，padding保护及完整病灶GT不成立。

180 tests通过，clean源码固定；三次独立readback均exit0且哈希相同，核查所有本地收据产物和上游结果/NPZ/官方mask。构建exit0。详细命令/日志留本地verification目录。重复读取不等三次真实模型或医院E2E演示。浏览器视觉审阅未执行，PNG仅本地生成及完整性检验。

当前医院默认未选、最终冻结/临床验证/三次医院流程NOT RUN。F0/F1真实对照NOT RUN。沿用旧版应用入口回退，新算法未替换现有Frontend/Backend/Worker协议。负责人钟佳桦通过总控汇总审阅；不自行宣布医院PASS。不上传、不push、不部署，旧v1/v2交付保留。

总控state重复回退专项：只读检索本工作树代码、脚本、测试（含ignored Python），未发现总控状态文件名或state_path引用。测试fixture写入tmp_path/TemporaryDirectory；本轮执行输出只在本树ignored目录。未定位回退源，不写总控state、不终止未知进程。
