# AE350 ROM128 分区实验的主树复验

2026-10-31，独立源码 `f0a5792268d58d3aadae16ad06dd86c4e525b372` 已以 `387cb93` 合入，仍未选入工作站 profile。主代理复核 linker、真实 AUIPC/JALR 指令目标、ELF 段重建、原 loader 和掩码译码边界后，从合入源码独立编译 25 个实际单元。生成 ELF／BIN／ROM 与作者封存包逐字节相同，完整布局与限制见[源码实验报告](WORKSTATION_AE350_ROM128_SPLIT_20261031.md)。

主树复验通过 47 项检查：分区与实际机器码模型 10、本地存储 12、boot-storage 4、callback-stack 4、accepted 来源 17。实际 ROM128 RTL 遍历、跨 ROM／ILM 调用、完整调用图 112 个可达函数／35 个直接远调用／77 个已审查间接点，以及 11 组 SBC 各两帧、3,712 个样本、最大误差 5 LSB 均通过。静态保守栈上界 1,792 B；模型子集栈观察不替代完整实测。

实际 BIN 82,288 B，包含 18,352 B 地址空洞；payload 63,936 B。ILM 使用 46,576 B，保留末字后可用余量 18,956 B；DLM 静态 8,448 B、保留前缀 256 B 和栈 16 KiB 后余 40,448 B。它证明代码可分区放置，尚未提供慢总线取指性能或额外 BSRAM 的实际成本。

作者父包 `ae350-rom128-split-parent-v1` 的重建式 verifier 已由主代理实际复验：85 份源码快照、271 个封存文件、6,194 个外部工具链文件，seal `75711989f6acdc341b74914203d98b025a701ca0200de3235f2c1c06d8ba5ba6`。主代理父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-rom128-split-main-parent-v2` 的 verifier 也已通过，85 份主树来源快照和 458 项直接外部文件，seal `364e7bf0da1e40af797815f14aead3e021150a568e3ae8a5631f6c5f52942451`。容量、实际产物身份及模型结果见[机器记录](workstation_task_20261030/ae350_rom128_split_main.json)。较早 v1 包绑定了可变主树路径，已保留并由 v2 的源码快照封存替代。

本阶段没有综合、P&R 或板卡操作。Cache 保持关闭，原 profile／普通 staging 仍只允许 16／64 KiB；128 KiB 仅由显式实验入口使用，96 KiB 明确拒绝。预算 adapter 尚未退出，HCI／安全配对／手机互通和最终 PCM transport 未闭环；不能据此提升整机、性能或硬件验收状态。
