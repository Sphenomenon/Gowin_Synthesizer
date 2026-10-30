# AE350 C9 强制 PLL 位置后的启动观察

2026-10-31，源码 `d10d384`，独立探针身份 `C21031C9`。只修正 CPU PLL 的物理位置后，GAO 首次观察到 loader／C service 的 `PASS`、ILM 内执行地址、DLM 栈地址以及正确的 32 KiB ROM payload CRC。**SRAM Verify 仍失败，完整硬件验收未成立**；UART 0 bytes、RTC 接线及完整诊断仍待处理。

## 固定输入与物理检查

C8 与 C9 的七个编译源和固件 ELF／BIN／ROM 逐字节相同，CPU 100 MHz／bus 50 MHz 保持。硬件变化仅为 `INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];`，另分配新 UserCode／GAO 身份。C8 的实际 `PLL_B[2]` 和官方要求见[上一阶段](WORKSTATION_AE350_LOCAL_PROBE_C8_HARDWARE_20261031.md)。

实际综合／P&R 89.568 秒，退出 0，全部固定输入前后不变。`.tr` 的 4,107 条 CPU PLL 输出记录均为 `PLL_R[0]`，包含 CLKOUT0 和供 core 的 CLKOUT1；综合网表分别连接 bus／core，原 50 MHz PLL 参数、复位链和同步链保持。报告最小 setup／hold／recovery／removal 为 +7.019／+0.189／+6.778／+0.299 ns，最小 pulse-width slack 为 +3.557 ns。它们限定于可见 PL 路径，不能独立证明加密硬核内部时序。

FS SHA256 `c5e0f843ecff337f4ecdfb241a641879690b1ab862ec08360a30bcdb8ec65017`。完整物理父包 `ae350-local-probe-main-physical-parent-v7` 已复验；seal 为 `59716b5d3a2e3351f53d28e322f65cd0e60c44479130353e3549fcbd32878c9c`，83 项外部固定文件。见[机器物理记录](workstation_task_20261030/ae350_local_probe_physical_v7.json)。

## 授权 SRAM 与实际观察

操作前独立读到原 Flash `C11028E5`／状态 `00022020`。Programmer operation 4 返回 18／`Verify Failed`；随后独立读到 `C21031C9`／状态 `00022230`。失败不能因新身份或软件 PASS 而忽略；本次没有 SRAM 主配置矩阵或 BSRAM 内容读回。

UART 115200 8N1、约 5 秒采集仍为 0 bytes。GAO 获得 128 个有效样本，packed 544-bit 与逐位列一致，高 32-bit health 为 `0xffff078f`：PLL／qualification／core reset／APB reset 均已释放，ROM 及 upper-ROM sticky 均为 1。相比 C8 的 APB reset 为 0、软件摘要全零，观察已发生明确变化。

低 512-bit 的 16 个摘要字段保持一致，逐字段独立核对如下：

| 摘要字段 | 观察与判断 |
|---|---|
| loader／service | 两者 `0x50415353`（PASS），error=0，phase=7，progress=8,192 words |
| PC／SP | `0xa0000a64` 位于实际 ELF 的 ILM 区；`0xa020ffc0` 位于 DLM 栈区，16-byte 对齐 |
| ILM／DLM 配置 | 两个 geometry CSR 均 `0x00439ada`，符合容量编码；local base `0xa0000001`／`0xa0200001`，均启用 |
| ROM payload | LE CRC32 `0xf44c0cf9`，首 word `0x1aba497d`、末 word `0x66ba777d`，均与独立 host payload 相同 |
| 有效 CSR mask | `0x1ff`；只表明此摘要值，不能替代未观察的 CSR 或计数器数据 |

这提供硬核启动、正式 loader、ILM 执行／DLM 栈和大于旧 16 KiB 冷 ROM 访问的实际支持证据。摘要未包含 cache control、内存 pattern 的完整计数／错误、mcycle／minstret delta 或完整 64-word CRC 帧；不能把这些字段补猜为通过。缓存仍按源码保持禁用，Cache／DMA 一致性未验证。RTC 仍继承 50 MHz，偏离手册 32.768 kHz，需另行修正。

## 回退与后续

观察后 operation 1 重载原 Flash，第四次独立 identity poll 确认 `C11028E5`／状态 `00022020`。全程无 Flash 写入。

硬件父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-c9-hardware-parent-v1` 的 `verify.py` 已真实通过，38 项直接外部文件并链接已封存物理及 C8 对照包；seal SHA256 `7f7fe7da668813328d8c3c902017152ce70496f772a2841485ea3fdc737cdba3`。原始命令、工具输出、UART、GAO、逐字段复算和回退由[机器记录](workstation_task_20261030/ae350_local_probe_c9_hardware.json)绑定。

后续将强制 PLL 位置及实际位置门禁带入维护中的原生整机装配，生成新来源身份，保持冻结基线及 accepted 输入不变；完整固件存储／调用栈、RTC／完整诊断／SRAM Verify、缓存一致性、整机资源／时序与手机音频闭环分别验证。本探针不提供整机资源预算、完整音频功能或 Flash 部署接受。
