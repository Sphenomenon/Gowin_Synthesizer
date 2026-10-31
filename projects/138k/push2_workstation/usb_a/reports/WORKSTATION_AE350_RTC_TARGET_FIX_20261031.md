# RTC 首次约束失败与综合网表目标修正

2026-10-31。固定 C10 `C21031CA` 的实际综合完成，但 P&R 读取 `probe.sdc` 第4行时因 `TA2003` 停止：约束使用 `u_rtc/rtc_tick_s0/Q`，实际保留的输出寄存器是 `u_rtc/rtc_tick_s1`（DFFCE）。17.928秒、退出1、输入保持，无位流、未访问板卡。该失败原目录保留，不覆盖生成输入或冒充物理通过。

维护约束改为实际 `rtc_tick_s1/Q`，新增 `audit_rtc_synthesis` 检查寄存器类型、常开 reference CLK、RTC Q 与 hard-IP wrapper 输入的同网关系，并拒绝接回 reference／bus／core。对实际 C10 VG 的正例及仅修改目标寄存器的 wrong-clock／wrong-output／wrong-target 三个负控均真实通过。prepare 也强制 RTC 约束目标及 1,524-cycle 周期界限。

RTC 算术收窄为足够容纳 `<50,000,000+65,536` 的26位，初始化使用显式 initial block，保留 GSR 初值及异步 reset；严格 Verilator `-Wall` 无豁免通过。源码修改后完整9项回归重新通过，包括整秒50,000,000 reference cycles、全部边沿周期／相位、复位及原固件／UART检查。原 lint 的声明初始化与未使用高位告警据此消除，没有压制告警。

最终新 prepare 为 `C21031CC`，目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-prepare-v10`。中间 `C21031CB` prepare 在 RTC 告警清理后被新身份替代，未运行 EDA 或板测；原目录保留。最终固件 ELF／BIN／ROM 与 C10／C9 相同。此阶段最终候选尚未物理运行，不能把失败版本 VG 的结构检查当作最终 P&R。

机器记录见[修正收据](workstation_task_20261030/ae350_rtc_target_fix.json)；父包 `ae350-rtc-target-fix-main-parent-v2` 的 `verify.py` 已实际通过，109项外部输入，seal `ad76692c2e562878fc2a6da68b220cd731b9f613c4e4f9188807aeb408870b84`，绑定原失败输出、新 prepare、源码快照、9项回归／lint及实际VG负控。首次封存误要求 lint 日志为空而停止；v2 接受 Verilator 正常统计输出，仍拒绝全部 warning／error，未改 RTL 测试或原始输出。板卡保持此前已确认的原 Flash `C11028E5`，本阶段没有 SRAM／Flash 操作。后续重新核查最终 VG、实际约束消费、routed timing 和授权板测。
