# TF epoch 比较分组：维护源码与回归

2026-11-01。M19 reference `D2110124` 的实际 50 MHz 最差路径为 `stream_epoch_o[1]` 经 TF epoch 不等比较、invalidate／media_stop 到时钟事务 booting，slack −1.264 ns。逐级核对的 32 个 ALU_MODE3 NE 单元确实比较全部 `rate_epoch`／`launched_epoch` 位。维护 `workstation_tf_runtime_service.sv` 现将完整 32-bit XOR 归约分成四个保留的 8-bit 组，再 OR 汇合；无新增状态、周期或 NBA 修改，即时取消和 X／Z 语义保持。

验证已完成：

- 实际完整 TF 模块 66,560 个四态组合检查、7 项即时控制、4 个实际变异及 2 个来源漂移负控；128 个自由 known/value 位的局部归约关系 UNSAT。
- 原 failure-factor 完整 owner 四种配置共 1,069,069 个边沿，50 输出／24 状态组一致；原 99-bit 故障关系和 4 个实际负控保持。严格逆变换逐字恢复 Git 前版 `90618bda…`，历史 fixture 未改。
- TF clear／stop 两个 buffer 配置、禁用路径、负控及 strict lint通过；当前来源回归 17 项通过。
- M19 实际 VG／D2110124 实际 VO 的 native 入口各执行 58 项，分别有 6／4 项 skip、68／71 个变异全部拒绝。其中 vendor 注册读模型因环境变量缺失额外 skip，已使用原冻结 GW5A 模型单独补跑通过（18／36-bit、1024 次 busy 写入、512 次停止读时钟）；余下 5／3 项为具名映射不适用。旧网表仅验证检查器兼容，未消费此次 RTL。

两位独立审阅者均无发现；主线程复验 104 个绑定文件及严格逆变换。源码身份、验证记录及 SHA256 见同名 JSON。初始路径摘录选错报告标题、四态 runner 误用不存在的 TB 变量，以及主线程复核器相对输出路径解析错误均保留说明；修正测试／复核入口后用新输出重跑，未为这些失败修改 RTL 或既有证据。

本阶段未更新 profile、综合或 P&R，没有实测时序／资源收益。完整时序归纳证明和物理 CDC 未接受，M19／W17 固定候选不变，未 SRAM／Flash。下一完整候选必须显式刷新来源锁并确认综合是否保留分组。回滚可还原本阶段五份 RTL／sim／工具文件并选用原锁定来源。
