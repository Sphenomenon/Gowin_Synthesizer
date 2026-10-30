# TF 发布与并行 counter 实际网表复核（2026-10-30）

对固定 `c7d66b419868f7f4`／VG `8c5d1e5a…` 完成独立只读审查，父级重现实际网表证明及全部 20 项负控。独立 seal 的九份相对文件和 1,473 项绝对依赖已逐项重新哈希；旧证据中指向可变工作树的来源路径通过新 relocation 记录映射到原哈希一致的固定副本，原证据不改。

TF `quiet_published` 是计算域唯一注册生产者，Q 只到 `quiet_sync[0]/D`，首级 Q 只到第二级 D；三寄存器时钟、无条件 CE、共同 runtime CLEAR 及复位断言逻辑通过。发布寄存器 D 锥有 81 个顺序前沿，均在计算时钟域，组合 primitive 最大深度 35。它被发布 FF 隔开，但自身计算域时序仍须 P&R 验证，不能仅凭两级同步结构宣称全部 CDC 通过。

四个实际 counter 的 32 位 Gray 生产者、32 位首级和 32 位次级同步均核对唯一 Q、严格逐位连接及完整首级扇出。补充检查覆盖所有位的共同本地 CLEAR、三拍复位释放、源 D 锥只含源域前沿；未从优化后消失的 formal 端口推造源函数证明。显示 counter 保留的完整输入还通过实际 LUT INIT 的注册 Gray encoder 矩阵证明。

MIDI、物理观察和显示 counter 的三个完整 32 位输出分别以实际 LUT INIT 的 GF(2) 矩阵证明所有输入上的 suffix-XOR 等价，最大映射 primitive 深度由 29／22／29 降至各 4。录音 counter 的完整输出 formal 已被消费端优化，不宣称完整输出矩阵通过；其 97 个 live affine 节点及 17 个 suffix 位的最大纯仿射深度为 4，不能用来代表后续消费算术。源函数仍由精确版本化源码及另行全域源码等价证明约束。

17 项主负控和三项逐位补充负控均被预期原因拒绝，包括旁路、额外 D／CE 扇出、错时钟、条件 CE、共同 CLEAR 分离、异域源 D 前沿和实际译码 LUT INIT 损坏。原 VG 前后保持，所有修改只在内存中。综合前五条路径未出现 TF／counter 只是列表事实，不是被省略路径的时序界限。

本阶段未安装或扩大 SDC，也没有 P&R、板卡、SRAM 或 Flash 操作。完整 CDC、Gray 物理位飞行、reset、PLL、routed STA 和硬件验收仍未通过。详见[机器记录](workstation_task_20261030/runtime_prefix_vg_parent.json)。
