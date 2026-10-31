# AE350 C10 RTC 修正后的物理与板上观察

2026-10-31，固定源码 `26b9438`，独立探针身份 `C21031CC`。本阶段把 AE350 RTC 从原 50 MHz 接线改为 32.768 kHz 平均频率的专用分频输出，完成实际综合／P&R、授权 SRAM 观察和原 Flash 回退。GAO 再次观察到 loader／service PASS、ILM 执行和 DLM 栈；**Programmer Verify 仍失败，硬件验收未成立**。

## 输入与物理检查

RTC 维护源码及纠正综合网表寄存器目标的过程见[上一阶段](WORKSTATION_AE350_RTC_TARGET_FIX_20261031.md)。最终使用 `u_rtc/rtc_tick_s1/Q` 的 DFFCE 输出，源时钟为 50 MHz，综合网表和 P&R 网表都把 `rtc_tick` 接入硬核 `RTC_CLK`。平均 32,768 Hz 的源码证明已通过一秒、50,000,000 周期仿真；STA 使用 1,524 参考周期对应的保守最小周期 30,480 ns，而非平均周期。

实际综合／P&R 298.114 秒、退出 0、固定输入前后不变。CPU PLL 的 4,235 条物理输出记录均为 `PLL_R[0]`，CORE_CLK 仍使用 CLKOUT1；core／bus 为 100／50 MHz。可见路径最小 setup／hold／recovery／removal 余量为 +4.675／+0.162／+7.590／+0.402 ns，最小 pulse-width slack +3.556 ns。RTC 约束被实际报告消费，但报告没有硬核内部 RTC 路径，不能据此宣称内部 RTC STA 或实测频率／抖动通过。

FS SHA256 为 `135fb6c29b612b8ec444943d80e716dd9337b61964eff4ff688fa7f383a97784`。物理父包 `ae350-local-probe-main-physical-parent-v10`、84 项直接外部文件，seal SHA256 `e953162b602b9d8de6fe55c69f3a3035ebeb866525d1b3b0c3d92a0f79a3d2df`；[机器物理记录](workstation_task_20261030/ae350_local_probe_physical_v10.json)保留详细来源和限制。

## 实板观察与回退

操作前独立读回原 Flash `C11028E5`／状态 `00022020`。operation 4 SRAM 操作返回 18／`Verify Failed`；随后的独立读回为 `C21031CC`／状态 `00022230`。未进行主配置矩阵或 BSRAM 内容读回，不能以新身份替代失败的校验。

UART 采集为 0 bytes。GAO 的 128 个有效样本，其 544-bit packed 值与逐位列一致，health 均为 `0xffff078f`。16 个软件摘要字段与 [C9](WORKSTATION_AE350_LOCAL_PROBE_C9_HARDWARE_20261031.md) 完全一致：loader／service `0x50415353`、error=0、phase=7、progress=8,192 words；PC `0xa0000a64` 位于实际 ELF 的 ILM 区，SP `0xa020ffc0` 位于 DLM 栈区；ILM／DLM geometry 均为 `0x00439ada`，base 为 `0xa0000001`／`0xa0200001`。ROM payload CRC `0xf44c0cf9`、首 word `0x1aba497d`、末 word `0x66ba777d` 均匹配 host 数据。

这支持 RTC 修正后硬核仍能启动并使用本地存储。未观察完整 64-word 诊断、cache CSR、计数器 delta 或完整内存 pattern 检查计数；未测实际 RTC 频率。Cache 保持禁用，Cache／DMA 一致性仍待验证。本探针不等于整机候选、实际解码性能或音频功能验收。

观察后 operation 1 重载原 Flash，第四次独立 poll 确认 `C11028E5`／状态 `00022020`。全程无 Flash 写入。

硬件父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-c10-hardware-parent-v1` 的 `verify.py` 已实际通过，39 项直接外部文件并链接 C9 对照及最终物理父包；seal SHA256 `e60ebe1d7ffc5d31ff7335cbd0f419d642f2e71e9b893e2e9dc991afffae8d61`。原始命令、GAO 复算、失败校验和独立回退记录由[机器硬件记录](workstation_task_20261030/ae350_local_probe_c10_hardware.json)绑定。
