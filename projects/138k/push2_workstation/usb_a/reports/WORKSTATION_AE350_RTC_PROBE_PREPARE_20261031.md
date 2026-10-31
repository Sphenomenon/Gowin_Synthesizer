# AE350 C10 独立 RTC 修正准备

2026-10-31。C9 已因强制 PLL_R[0] 观察到启动及 ILM／DLM 软件摘要 PASS，但其 RTC 仍继承 50 MHz，偏离官方 32.768 kHz 要求。新探针身份 `C21031CA`（C10）只修正 RTC 功能输入：由常开 50 MHz reference 产生平均 32,768 Hz；固件 ELF／BIN／ROM 与固定 C9 逐字节相同，CPU／bus 为原 100／50 MHz，PLL_R[0]、摘要和 UART 格式保持。

新增维护 RTC 不依赖 CPU／APB，半周期为 762 或 763 reference ticks，边沿相位误差小于一个 20 ns reference tick。分数分频不是无抖动晶振，不能用于精确音频时钟。显式 generated-clock 以最短两半周期 1,524 ticks 作保守 STA 周期界限，另记实际平均 32.768 kHz；没有移除路径或放宽其他时钟。P&R 仍需确认目标寄存器、硬核连线、实际约束消费和完整时序。

`sim/test_ae350_local_probe.py` 实际 9 项回归通过（69.343 秒）。新增一整秒／50,000,000 个 reference cycles 的 RTL 检查，观察 65,536 个翻转、32,768 个上升沿，检查全部半周期／上升沿间隔、每个边沿的相位界限、异步复位、持续复位与重新起振；原固件执行模型、PLL 位置负控、CRC／本地存储、顶层引脚和 UART 回归同时通过。日志位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-tests-v9.log`。

prepare 位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-prepare-v8`，含 8 个编译源和独立 `rtc_clock` 预算，`audit_prepare` 已通过。来源及全部准备字节由该目录的 `inputs.json` 固定；该目录不重用。此阶段没有新综合、P&R、SRAM、Flash 或板级接受。后续继续单变量实际对照；C9 的失败 Verify／空 UART 及未捕获完整诊断不能由离线 RTC 测试消除。
