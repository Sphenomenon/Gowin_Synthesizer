# M11／W10 完整候选测量与阻塞

2026-10-31。两套显式 DEMO 各从 822 项维护来源锁重新 prepare 并全量综合，未复用旧 VG。实际消费 TF 容量／配置 ACCEPT、D 精确运算、I2S source hold、HCI 池比较及两处接收边界的修改。两份 manifest 的全部 588／645 项封存输入再次逐项核对。

| 候选 | 独立身份后缀 | LUT | ALU | FF | 综合 BSRAM equivalent | SSRAM | 严格综合门 |
|---|---|---:|---:|---:|---:|---:|---|
| M11 | b5f6da2e64a82b66 | 51,393 | 12,890 | 46,931 | 195 | 141 | 通过 |
| W10 | d1dddd2e83ad1cfd | 60,993 | 20,321 | 45,073 | 257 | 310 | USB 写许可证明拒绝 |

M11 VG SHA256 `15115fd5beaf5d1ea4c383da795436639dec401fc2bf2d5b78f3e2f6779e0227`。两份完整配置、实际输入／输出 hash、W VG 身份与原始失败日志均固定于[机器证据](dual138k_m11_w10_candidates_20261031.json)，SHA256 `e88aad459e5f388e183748c5f531ef14fb56457f725712755595affc7d856602`。综合 equivalent 不代表后续物理 BSRAM。

M11 严格综合门通过后，以新 `D2103115` 默认布局完整 P&R，工具 exit0 并生成位流；物理 Logic65,562、FF46,931、CLS49,901、BSRAM235／340、DSP120。setup 5,619 端点、最差 −3.762 ns；hold 1 端点、最差 −3.556 ns；recovery +3.349 ns、removal +0.275 ns，**整机时序仍失败，不可部署**。DDR 目标路径保留原 3.500 ns 要求，实际 launch／capture 为 R90C8／R90C5。

四条 50 MHz 专项报告各有100条路径：同域 setup 最差 −0.766 ns、前100条中11条为负，来自实际 stream epoch→TF 恢复扇区 CE；同域 hold +0.164 ns。全局主同步路径是 compute release／delay underflow→音频 core_ce 配置资格重汇合→矢量 DSP／CE，不能把 CDC 接收例外当作该同步长链的修复。

M11 原生协议 VG／VO 局部门、四条新增接收边界的实际 VO 清单及 SDC 检查通过。六 PLL／DDR 来源／serializer／AE350 等子门通过；首轮 PLL 运行因子进程未发现官方仿真模型而退出，日志保持，新外部 workspace 显式指定已装官方 `GOWIN_SIMLIB` 后原工具通过。它不覆盖完整 STA 或整机 CDC。

W10 全量综合 exit0，但严格门在 `workstation_usb_fifo_reset.audit_synthesis` 的“实际 packet RAM 不可在最终本地 release 前写入”布尔证明处拒绝，原始 traceback 已封口。当前尚未物理 prepare、没有使用预留 `D2103116`、没有 W10 物理资源或时序结果。正在独立核对真实 CEA 的完整组合锥与重汇合切点；任何后续审计修正使用新身份／证据，不改 W10 的封存输入或失败记录。

当前仅 M11 默认完成物理测量。DDR far 派生另以新身份、该实测及 hash 绑定 VO 生成，结果随后独立记录；首次派生命令因漏传既有电气风险确认参数而在修改前拒绝，原失败日志保留。未改变 clocks／false paths、未删共同声画或 USB 功能，未下载 SRAM／写 Flash。真实 HDMI 像素、DAC、手机 A2DP／D 处理、BLE 录音下载及双板并发仍待验收。
