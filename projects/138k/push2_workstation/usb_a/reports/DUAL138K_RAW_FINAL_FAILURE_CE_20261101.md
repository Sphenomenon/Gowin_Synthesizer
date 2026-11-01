# W raw 录音最终故障写使能修复

2026-11-01。W17 far 的实际 DDR UI 最差路径为 arbiter `tags[19][3]`→raw `memory_failure[1]` CE，−5.123 ns。维护源码现将该私有 4-bit 寄存器的六处 NBA 写入移到同一时钟／复位的独立 process：已知即时故障直接经过原 first-fault guard 写入，零故障时并行计算协议失败写资格；X／Z 沿用原完整投影。其他目标的 NBA target／RHS／顺序逐项保持，既有邮箱、DDR 接口、完成码与取消优先级不变，没有新增周期。

| 验证范围 | 结果 |
|---|---|
| 完整真实 raw owner 两几何新旧对照 | 356,656／304,921 边沿；24 输出、117 原寄存器、182 信号及 4,096 cache cells |
| 任意原始状态／四态 | 4,096 边沿＋32 定向场景，含 sticky first-fault、取消、超时与同拍 clear／START |
| 最终 CE／value 四态投影 | 524,288 向量；协议 kind／guard 16,384 唯一四态向量 |
| 本修复负控／来源漂移 | 5／4，全部拒绝 |
| 原 raw 回归 | 两几何／5 负控；精确保留既有 4 类 lint warning |
| 真实 DDR queue／bridge | 27 正场景、6 故障场景、11 负控、两种 strict lint |
| 原 return-preload／global-failure | 4 正场景／5 负控；4 正场景／6 负控 |
| 原 BLE 录音五层模型链 | 5 正项／27 负控；真实协议 6 场景／3 seals |

维护来源 helper 严格恢复 W17 的 `d2e39654…`，再通过已有逆变换保持 return-preload／global-failure／CLEAR 的历史 fixture 身份。原 fixture 和门槛没有改。正式 BLE 入口最初被旧 raw source pin 拒绝，失败保留；经显式核对新 RTL 身份后，仅提升 `workstation_bluetooth_ddr.py` 的该 source pin，在新 v2 输出完成五层回归。cache v1 包装器的编译前语法失败也保留。

主线程独立重算 552 份证据、4 份维护文件及工具 pin，并确认新源码严格 inverse 与提交前 Git 源码相同。新 RTL SHA256：`5262395f5031a14aa6cf18b359852590d3dcab33ee3fde9ce5f4e069b6fb9739`。完整输入、六项入口与封存身份见[机器报告](DUAL138K_RAW_FINAL_FAILURE_CE_20261101.json)，cache 为 `raw-final-ce-maintained-handoff-v1/`。

本阶段未更新 profile 或启动新综合／P&R，没有实测资源／时序收益。BLE 链使用 native DDR 模型、测试链路注入和缩短预算，不是实际手机／无线／声画验收；完整时序归纳证明与 physical CDC 仍未接受。原 M19／W17 固定输入不改，下一完整候选重新锁定与测量；未做 SRAM／Flash。回滚可恢复本阶段五份 RTL／sim／工具文件并选用原锁定来源，不能推断旧 W17 位流已消费本修复。
