# HCI ACL generation 比较的维护源码修复

2026-11-01。W17 far 的实际 50 MHz 路径仍由 host RX generation 穿过 HCI 许可链到 reliable 状态，最差 −3.708 ns。维护 `workstation_hci_flow_owner.sv` 现先并行比较每个 handle slot 的完整 32-bit generation，再由原 `acl_slot` 选择一位结果；每个比较保持四个 8-bit 归约组。句柄查询、信用、错误优先级、同拍取消及全部 clocked 字节保持，未增加流水周期。

生产构建消费维护 RTL；新增来源 helper 只为仿真严格逆变换重建完整旧模块。逆变换已与本阶段之前的 Git 源码逐字比较，正反变换和四个来源漂移负控均通过。既有 owner 回归只迁移 stale-generation 变异的唯一锚点。

| 验证范围 | 结果 |
|---|---|
| 两套完整 owner 新旧逐拍对照 | 各 91,711 周期，32 输出、19 scalar groups、8 array words；合法／过期 ACL 及四个同拍优先场景 |
| 实际模块四态 | 151,160 组合，HANDLE_SLOTS=1／2／16，含未知值、非法 selector 与错误优先级 |
| 组合关系证明 | 128 个独立 known-mask／value 位，差异 UNSAT；手工提升关系，非完整 SV 时序归纳证明 |
| 新实际模块／来源负控 | 8／4，全部拒绝；含 transport／timeout 即时取消 |
| 原 pool 对照／独立 oracle | 118,730 周期／270,336 向量，4 负控 |
| 完整 native 默认入口 | 268 checks、11 负控；未跳过 prior 或 UART |
| prior bootstrap／host RX／shared owner | 418／160,228／116,780+9,174 checks，17／13／11 负控 |
| UART8E1／H5 RTL 模型闭环 | patch253、bootstrap4、hostreturns10、notifications3、reconnect1 |

默认 Python 缺少 z3 的两次原始失败保留于 `flow-acl-generation-runtime-failure-v1/`；未改 fixture 或验证工具，使用本机已有 Miniforge Python 3.14.6／z3 5.1.0，在新 v2 输出完整通过。另保留 CLT Python 的完整 native v1 结果。

主线程独立重算 757 份封存文件、4 份维护输入和 10 份回归交付，并核对严格 inverse 与 Git 源码相同。维护 RTL SHA256：`e32a9ef62a527907da7baeaaf4ec592b38261483f9f6f7d7fa3429cbd32b9dc8`。完整身份及运行记录见[机器报告](DUAL138K_HCI_ACL_GENERATION_20261101.json)。证据根为 `/Users/sphenicidition/.cache/gw138k-dual-20261031/flow-acl-generation-maintained-handoff-v1/`。

本阶段未修改 profile 来源锁，尚未进入新整机综合／P&R；固定 M19／W17 输入及失败物理证据保持。没有实测物理收益，未做 SRAM／Flash 或真实蓝牙声画验收。下一候选显式更新来源锁并重新测量；回滚可还原本阶段四份 RTL／sim 文件并使用原锁定候选，不能把旧 W17 位流当成已消费本修复。
