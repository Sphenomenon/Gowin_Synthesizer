# Chorus 新 VG 的 TF／counter 父级复核（2026-10-31）

父级在候选 `6b9610324164f0c9`／实际 VG `2cfe81e5…fe316c8` 上重新执行 TF quiet 和四组 counter 映射审查，17 个实际网表负控、三项全位 reset／source-D 前沿负控全部通过。旧脚本及 c7 证据保持原字节；新负控脚本只在精确单锚处改为新 stage 和 VG hash，不转移旧接受。封存 11 文件和 606 输入依赖，详见[机器记录](workstation_task_20261030/runtime_chorus_TF_counter_vg_parent.json)。

实际 TF quiet publisher 为唯一 compute 域寄存器，直接送 source50 的严格两级同步器；publisher、首级和第二级的完整消费者、共同 runtime CLR 及 81 个 compute D 前沿均重新验证。D 锥 35 个原语级主要包含 carry 比较，不能当作物理延时；未安装首级或其他新 SDC 例外。

四组 counter 各有 32 producer／32 first／32 second，逐位 CLR、source-D 域与 reset release 保持。MIDI／observation／display 的 32 位实际 affine 解码矩阵深度均为 4；recording 的全 32 位 formal 已被优化，仍只接受实际存活 affine 节点和 17 个后缀位，不宣称完整输出证明。display 实际注册 Gray 编码矩阵也重新核对。

新 VG 独立生成的全部 counter 和 TF quiet 映射明细与 c7 相同；这一结论来自实际重跑和逐对象比较，非依据 RTL 相同推定。新最差五条路径仍为 pitch，counter／TF 不在该列表不构成时序上界。TF 其他握手与 held36、完整 CDC／reset／PLL、routed 时序及硬件仍未接受，没有 EDA、板卡或部署操作。
