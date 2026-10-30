# AE350 C8 平台观察与 C9 强制 PLL 位置修复

2026-10-31，来源 `a875d15` 的独立 C8 探针已完成一次授权 SRAM／两次 GAO 观察并回退，**未通过硬件验收**。新增观察定位到 APB 复位尚未释放；随后发现 C7／C8 的 CPU PLL 实际放在 `PLL_B[2]`，违反 AE350 官方物理要求。可见 PL 路径的正 STA 不能抵消此项，先前“物理通过”的描述应限于当时已检查的 PL 路径，不能作为完整硬核物理接受。

## 固定物理与 SRAM 结果

- 身份 `C21031C8`，输入固定的实际综合／P&R 退出 0，120.241 秒；FS SHA256 `0cd405db75f05a3bdd25f2f05ba722008bf967d640e3d01a9dedcdd428d30d44`。
- 报告最小 setup／hold／recovery／removal 为 +5.842／+0.140／+6.778／+0.403 ns，仅为可见 PL 路径结果。原始物理证据父包保持不变，见[机器记录](workstation_task_20261030/ae350_local_probe_physical_v6.json)。
- 独立操作前读到原 Flash `C11028E5`／状态 `00022020`。Programmer operation 4 返回 18／`Verify Failed`；后续独立读到 `C21031C8`／状态 `00022230`。用户代码匹配不能取代失败的 Verify。
- UART `/dev/cu.usbserial-21201`、115200 8N1、约 5 秒获得 0 bytes。C8 没有 SRAM 矩阵读回，不借用 C7 的读回结果，也没有编程后 BSRAM 数据证据。
- 两次 GAO 各有 128 个有效样本，544-bit packed bus 与逐位列一致。高 32-bit health 分别固定为 `0xffff0197` 和 `0xffff0187`，低 512-bit 软件摘要均为 0。reference counter 已饱和、PLL qualified／system reset／core reset 已释放；APB_PRESETN 仍为 0，UART 状态分别为 1 和 0。
- ROM sticky 随硬核 `ROM_HRSTN` 复位；其零值只表示未保留到观察时刻的访问证据，不能证明没有发生过 HTTRANS。UART 在 APB 未运行时仍应发送超时帧，因此空串口也留下物理 UART 路径的检查项。
- operation 1 重载原 Flash，第四次独立 identity poll 确认 `C11028E5`／`00022020`。全程未写 Flash。

## 官方约束及新候选

MUG1031 v1.3.1 第 7.3 节（PDF 第 54／56 页，印刷第 46／48 页）和 MUG1030 v1.3 的 PDF 第 17／18 页要求 CORE_CLK 来自 `PLL_R[0].clkout1`，并明确必须约束 PLL_ADV 位置。C8 `.tr` 第 10124 行及全部对应输出行实际为 `PLL_B[2]`，CST 没有 PLL 位置约束。独立审阅、原页及视觉核对已封存；这是已证明的配置偏差，尚不能断言为唯一启动根因。

维护探针新增 `INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];`，prepare 拒绝遗漏、错误、重复约束；新增实际 `.tr` 位置门禁，拒绝缺失 core output、错误实例或任一错误位置。8 项针对性回归通过，其中包括真实固件启动模型、CRC／ILM／DLM 模式、UART 异步快照及位置负控；独立门禁也实际拒绝了 C8 报告。

C9 prepare 使用新身份 `C21031C9`。所有编译 RTL、ELF／BIN／ROM 与 C8 逐字节相同，唯一硬件输入变化是 PLL 位置约束；生成身份及元数据随候选更新。100 MHz core／50 MHz bus 保持。RTC 仍继承 50 MHz 接线，偏离手册的 32.768 kHz，留待下一独立变量检查；缓存保持禁用。C9 此阶段仅 prepare，无新的物理或板级接受。

## 复核与范围

父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-c8-hardware-parent-v1` 的 `verify.py` 已实际通过，80 项外部输入；seal SHA256 `bebc10b4e41244a4fb9a84e5abf6b6c8d363463dd2ef3334281e099393472943`。机器记录见[失败硬件与新准备](workstation_task_20261030/ae350_local_probe_c8_hardware.json)。官方 PLL 审阅包 seal 为 `bb599a53e90049ca2c0c924504ae8ad483446f9f7e5431973834fbbe1e537fbd`；原 C8 物理父包 seal 为 `61ccfebb1aab8e867cdbaa5336be48fec33ef0233452efc1881e0a2c5c3f5a5c`，二者均已独立复验，保留各自原始结果。

本阶段不成立 ILM／DLM 硬件通过、Cache／DMA 可用、完整工作站资源／时序／音频通过或 Flash 部署。后续先核实 C9 的实际位置与 STA，再进行已授权的 SRAM 对照并独立读回、回退。
