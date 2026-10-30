# 录音 owner8 双客户端源组件（2026-10-30）

为已授权的 BLE 短录音 DDR 迁移增加未选入整机的 `workstation_recording_ddr_owner_mux.sv`。它只仲裁两个互不重叠的存储客户端及归属返回；CPU R00 对象与 BLE 录音仍分别持有自己的业务状态，未复制 ID、任务或 CRC 权威。

每个客户端保留真实 native-commit bridge。slot 接受不等于 DDR 提交，写命令锁定到 native accept，读命令锁定到返回；支持 native accept／read response 同拍。轮转、BL8 对齐、完整 burst 区间及 mask 保留，最多一个 outstanding。超时、无归属事件、非法地址或通道资格撤销立即隔离并锁存故障。

`channel_ready_i` 只是外部 DDR authority 的资格输入。独立回归保留了反例：如果只复位 mux／客户端，就错误重新开放通道，旧无标签返回仍可能被交给新 owner。此组件没有解决物理排空，实际控制器／返回账本复位及不可重复 rearm 必须在整机接线时单独证明。合同同样禁止把包含广播输入的 bridge `transport_fault_o` 回接 mux 输入形成组合环。

父级回归 2 项通过：1,937 checks、88 次写、75 次读及八个源码突变拒绝。独立回归追加 496 checks、四个突变，覆盖末允许周期、持续双请求、公平性、未授权事件、资格撤销与完成同拍、重新抬高 ready 不能解除故障。五个审查输入（含既有 bridge）与根目录逐字节一致，完整独立封存重新核对通过。

Verilator 严格 lint 在非零、29-bit 显式测试区间通过。默认零起点产生一条恒真无符号比较提示；首次命令行使用 32-bit 参数值产生宽度提示，两次原日志保留，改用精确 29-bit 参数后零警告，没有抑制诊断或修改 RTL。

机器证据：[recording_owner_mux_parent.json](workstation_task_20261030/recording_owner_mux_parent.json)。独立 seal SHA256 为 `244d8d3782662785b6fd710a8cfe7b86af811233e979f2ac5598eb7e27835f6c`，父级日志及严格 lint 位于同一 cache。契约见 [RECORDING_DDR_OWNER_MUX_CONTRACT.md](../rtl/memory/RECORDING_DDR_OWNER_MUX_CONTRACT.md)。

未更改生产编译选择或 DDR 权威分配；通用参数及测试区间不构成实际存储分区。没有综合、物理净资源收益、完整 CDC／STA、BLE 协议闭环或硬件接受，没有 SRAM／Flash 操作。回退可删除本次未选择组件及测试，已选入的 R00／accepted 输入不受此组件影响。
