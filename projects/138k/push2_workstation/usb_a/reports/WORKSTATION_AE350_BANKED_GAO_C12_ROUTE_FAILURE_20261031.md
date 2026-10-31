# C12 分组 GAO 探针：实际布线失败复核

2026-10-31，探针 `custom138k-ae350-local-memory-probe-C21031CE`，固定构建源
`fe8e44bd0a7cc7e45249e2fc783a81bd5ea7615c`。实际工具在 1,743.658287 秒后
退出 **1**，日志和 P&R 报告均为 `PR0004: There are total 91 unrouted nets`。
这是工具完成该次尝试后报告的布线失败；[C11](WORKSTATION_AE350_FULL64_GAO_C11_ROUTE_BUDGET_20261031.md)
是在仍活跃时因诊断预算主动 SIGTERM，两次运行的身份和结论独立保留。

本复核在 `d745697` 的独立 clone 中执行，只读使用主线审计器，未改工具、约束、
门禁或固定输入，没有再次运行 EDA／JTAG。原 prepare 全部 40 个文件与 runner
的运行前库存逐字相同，physical 副本也保持；manifest 的 39 项、九份编译源码、
五份 native RTL 和五份固件源的 Git 身份分别复核。30 个登记实现输出、完整工具
日志及两份记录的工具二进制 SHA256 均与实际文件一致。

| 审查边界 | 结果与限制 |
|---|---|
| prepare／编译来源 | 原 prepare 和 physical 副本的 `audit_prepare` 通过；冷镜像 36,368 B，ROM 65,536 B，ILM 35,760 B。不是 CPU 运行期或硬件容量接受 |
| GAO 实际 VG | 主线 `audit_gao_synthesis(..., gao_mode='banked4')` 通过：704 位完整保留为 `clk_50m` 寄存器；A1386402、四页×16 字、深度128。不是四页硬件采集已完成 |
| RTC 实际 VG | probe 检查与严格 `audit_synthesis_netlist` 均通过；50 MHz 保持 FF 直接接唯一不透明 `RiscV_AE350_SOC` 的 `rtc_tick`，不声称看穿加密内部 |
| RTC 约束 | `cpu_rtc_bound` 精确 divide1524，最短周期30,480 ns；32,768 Hz 是平均输出频率，没有以平均周期放宽 STA |
| RTC 实际 VO | 路由失败仍生成 `.vo`；严格 `audit_netlist` 通过：保持 FF 直接接可见唯一 `AE350_SOC/RTC_CLK`，没有额外消费者。该文件的接线证明不等于完成布线或时序通过 |
| CPU PLL 源约束 | 显式 `u_cpu_pll/PLL_inst` 约束 `PLL_R[0]` 通过 |
| CPU PLL 实际位置 | 原位置门拒绝：`routed AE350 CORE_CLK PLL evidence missing`。本次 resource 报告没有最终时钟位置表，无法授予 PLL 物理位置接受 |
| 最终物理产物 | 无 `.fs`、`.tr`、`.sdf`；setup／hold／recovery／removal 及最终时钟时序均为 null，不从 90% routing 进度或 `.vo` 推断成功 |

实际 P&R **主设计资源表**为 Logic 5,031（4,881 LUT＋150 ALU）、Register 10,687、
CLS 7,800／69,120、BSRAM 40／340（8 SDPB＋32 pROM）、I/O 8、AE350_SOC 1。
**独立 GAO 资源表**另列 Logic 1,078（1,068 LUT＋10 ALU）、Register 3,032、
BSRAM 40、I/O Port 709 与 I/O Buf 4。主设计40不是含 GAO 的总量；两表必须同时
保留，GAO 的709是仪器内部接口计数，不能说占了709个封装引脚。GAO 综合 XML 的
BSRAM20与物理 GAO 表40属于不同阶段，不能混算。报告没有给出包含 GAO 的组合总
CLS，本次也不是完整工作站资源预算或净收益测量。时钟资源表列 PRIMARY4／8、
LW4／8、PLL1／12；这些资源行不代替最终 PLL 位置或 routed STA 门禁。

工具报告版本 V1.9.12。runner 冻结的 `gw_sh`、`GowinSynthesis` 哈希及编译器版本
在机器记录中逐项保存并重新核对；没有独立 `gw_pnr` 二进制哈希记录，不能补造。
原运行保留四条输出声明初始化警告和两条 frozen PLL 截位警告，没有为本次复核
消除或隐藏它们。91 条未布通网络的归属和根因尚未证明，不能归因于某个 GAO 页、
RTC 或硬核端口，也不能以较窄 GAO 自动宣称路由改进已经成立。

C12 没有位流，从未部署或采集。该次尝试和本审查均未操作板卡。最新已记录的
独立只读身份仍为原 Flash `C11028E5`／状态 `00022020`，来源是 C11 封存的
operation0；本次按只读任务边界没有重新执行 JTAG 查询。此前 SRAM Verify 失败、
完整64字诊断、CPU真实周期、Cache／PMA属性与外部 UART 接收等缺口继续保留。

机器记录：[ae350_local_probe_c12_route_failure.json](workstation_task_20261030/ae350_local_probe_c12_route_failure.json)。
原文件及审计工具快照封存在
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-c12-route-failure-audit-v1`；
`verify.py --originals` 已通过135份固定文件和117份原始文件，seal SHA256：
`db8e0fd8a311780b4fc82ebe9a284067541ee0f1866e593dde04b34e4897a588`。
固定 prepare／physical、runner、日志、已有板卡只读记录、审计脚本和来源均可复核；
后续须新候选身份，不能覆盖 C12 失败或复用其身份宣称部署。
