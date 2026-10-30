# C06 ILM/DLM 独立探针主树准备

导入作者 `3b6fa565e9c401fc56dc63e245eebe6239528028` 的十份版本源码；主树 `697c557` 保留当前 C02／C03／TF 实现，并更新六份 workstation profile 的 `build.py` 来源哈希。新入口仅 prepare，不自动运行 EDA 或板卡操作，不选择为完整工作站。详细寄存器、UART 与退役契约见[探针说明](../rtl/probe/AE350_LOCAL_MEMORY_PROBE.md)。

父级实际重跑六项回归，覆盖编译后的正式 loader 和 C 服务、32 KiB 非零 payload／CRC、ILM/DLM 地址 pattern、旧 16 KiB ROM 回卷和地址别名故障、可选 CSR 精确 trap 恢复、最新 UART 帧／CRC／异步快照／超时，以及实际 frozen wrapper 端口展开和 DAC 固定安全输出。accepted sources 十七项、ProfileSources 六项通过，六种配置来源锁均加载成功。

主树实际准备 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-prepare-v1`，身份 `custom138k-ae350-local-memory-probe-C21031C6`；37 项输入／7 编译源重新审计通过，inputs SHA256 `700b7258417b02cd4073d9de7fbfb95b4e730e7206e8c2232efb002ee11b84fc`。实际硬核／包装器／PLL 配置与正式 loader 字节保持。冷镜像 36,368 B、ILM 35,760 B、保守栈 96 B；ELF／BIN／ROM 与作者 v2 完全一致。counter 模型是合成值，尚非实际性能。

另实际 prepare 完整业务控制候选 `custom138k-workstation-ae350-business-v1-f2d86364e4ab5ebe`，612 项 staged 与新入口加入前 `8f615119768bfbf2` 逐字相同。新来源身份独立记录，正在运行的旧固定副本不改。

板级 SMUTE=A15 固定高、PDN=C13 固定低、MCLK/BICK/LRCK/SDATA 固定低，取 B7 已核对的排线映射，未使用 pinout-only 的同序候选。该电平策略不等于模拟无声验收。I/D cache 保持关闭，探针先读实际能力、PMA 与计数器，不将 cache 当普通 RAM。

机器记录：[ae350_local_probe_main_parent.json](workstation_task_20261030/ae350_local_probe_main_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-parent-v1` 的 `verify.py` 绑定 16 份源码快照及外部输入，可只读复核。本探针尚未综合、P&R 或上板；后续由独占 Gowin 流程生成独立物理证据，操作前读当前身份并保留回退，不写 Flash。
