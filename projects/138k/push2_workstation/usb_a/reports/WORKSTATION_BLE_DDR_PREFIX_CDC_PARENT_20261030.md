# BLE DDR prefix CDC 范围父级组合（2026-10-30）

新显式范围 `runtime-r00-no-local-panel-ble-ddr-prefix-v1` 已合入维护工具并在父级重新通过四项公开审计。它只接受固定 `c7d66b419868f7f4` 的实际 593 staged／269 enabled 来源、编译顺序、native counter 替代关系、TF 发布源码及 VG `8c5d1e5a…`。旧 serial helper 字节、旧端点表、默认入口和严格拒绝保持；相同 business revision2 不代表可以继承另一个实际网表的接受。

13 个 phase1 与 42 个 raw 完整闭包由声明的唯一生产者独立枚举。四个 phase1、七个 raw 哈希变化对应 backend memory CE factoring：按逻辑名称比较增加 96、移除 42 个 CE 端点，逻辑 FF 集合与 opaque／top 端点相同；接受仍使用全部精确 D／CE／CLEAR 端点及哈希，没有用归一化或时钟过滤放宽。共享 seal reset 的完整闭包和十个功能 CLEAR 重新核对，未因观察到相同哈希而继承。新视频别名只在 prefix 范围选择 `u_video/front_valid`，唯一生产 FF Q、memory 时钟及接收首级 D 仍必须一致；旧 `front_valid_Z` 范围不改。

父级 10 tests／14 实际网表负控及 28 个来源子负控、17 accepted 来源测试通过；独立审另外保留旧 277 的五项／12 实际负控和 24 项旧定向测试。共享仍检查全部 88 行安装约束，USB 仍检查三处接收 CLEAR 及完整复位扇出；phase1 的 425 FF／42 Gray／82 payload 与 raw 的 13 普通对／50 Gray／528 逻辑位、524 映射源 FF 保持。seal code 四位消除仍未接受。

四份 profile 只更新四个已审工具哈希，并锁定四个新增工具／测试／契约输入，其他字段和业务 revision 不变。新 prepare 为 enabled `0b8c819877ff25be`、no-CNN `540e40c2219c1fcf`、R00 `2bf5c907b10b3c8e`、no-panel `5edcba8696e13308`，各 12 项来源测试通过，profile 20 项通过（一个可选历史项跳过）。全部 staged 和 enabled 实际字节与各自 counter 前序一致；CST／SDC 的来源说明 map 精确反映四项更新、三项新增工具，但约束字节不变。它们不继承 c7 的综合或 CDC 身份。

初始来源漂移拒绝、prepare 后比较脚本的父目录拼写错误，以及过严 provenance 相等比较的失败均保留。新独立 validator 验证准确的来源差异并通过，没有重写失败证据或成功 prepare。父级还逐项核验独立 seal 的 81 份相对文件与 656 项绝对依赖；完整路径、SHA 和各阶段记录见[机器记录](workstation_task_20261030/ble_ddr_prefix_cdc_parent.json)。

本阶段不安装 SDC；phase1 的 18 receiving CLEAR 仍只是提案。完整 CDC、reset、held payload／RAM 物理约束、Gray 位飞行、PLL、routed STA、板卡及部署均未验收，没有 SRAM 或 Flash 操作。
