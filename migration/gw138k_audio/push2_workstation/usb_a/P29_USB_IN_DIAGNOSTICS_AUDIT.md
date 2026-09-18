# P29 USB IN 错误诊断审计

2026-09-18：本阶段补齐 FPGA USB-A 路径里一直为 `null` 的 USB IN 诊断。改动只经过现有 VexRiscv USB Host 固件、MMIO 和 P138 遥测，不改 Push pad、连续压力、通用 MIDI 事件内容、音频声部分配、HDMI、耳机或效果链。

## 原因与完整路径

USB SIE 原本已经给出 CRC 和响应超时状态，`usbhw_transfer_in()` 也会返回 NAK、STALL 或超时结果。生产固件只用这些结果维护 50 ms 失联检测，没有累计诊断值。控制 RTL 的 P138 word 6 固定为 `0xffffffff`，电脑端 `control.py --usb-a` 又把它强制解释为 `None`，所以真实 USB-A 版本始终只能显示 `usb_in_errors: null`。

P29 沿用原来的数据通路：J18 D+/D− 在 48 MHz USB 域进入 PHY/SIE，VexRiscv 固件的 `poll_midi()` 分类每次 IN 结果，经 `0x58` MMIO 写入 `push2_usb_a_control`，再占用 P138 已保留的 word 6。224 bit P138 快照仍经过原有 USB 48 MHz → 50 MHz held-snapshot CDC 和 UART 输出，电脑脚本只负责校验 CRC 并解码。没有增加新的跨时钟握手。

## 计数格式

P138 word 6 分为四个独立的 8 bit 饱和计数器：

| 位 | `control.py --usb-a` 字段 | 含义 |
|---|---|---|
| 7:0 | `usb_in_errors` | 非 NAK 传输失败、无效 DATA PID 或畸形 MIDI 包 |
| 15:8 | `usb_in_duplicates` | 与期望 DATA0/DATA1 toggle 不符的重复包 |
| 23:16 | `usb_in_naks` | 设备正常返回的 NAK |
| 31:24 | `usb_disconnects` | IN 回复连续失效 50 ms 后触发的既有断线流程 |

计数从 USB CPU 复位开始累计，重连时保留；每项到 255 后停止递增，不回绕。普通 NAK 会刷新链路存活时间，不计入 `usb_in_errors`，也不触发断线。合法但重复的 DATA 包同样刷新存活时间，记录重复次数后丢弃，不重复生成音符事件。

底层 `usbhw_transfer_in()` 会把部分 CRC 错误和响应超时折叠成同一负返回值，另一路 CRC 检查也可能返回 STALL。因此 P29 的 `usb_in_errors` 是可靠的传输/协议错误总数，但不能再从这个总数中还原 CRC 与 timeout 的各自数量。这个限制在输出中保留，没有伪造更细的分类。

## 队列、背压与 PANIC

诊断 MMIO 与 MIDI 事件 FIFO 都位于 USB 48 MHz 侧，但计数写入不进入事件 FIFO。只有校验通过且 toggle 正确的 MIDI DATA 才沿原有异步 FIFO进入 76.8 MHz 音频域；FIFO 满时的 CPU 写等待、事件顺序和声部分配没有变化。

P29 保留原 50 ms `disconnect()` 调用及其现有松音行为，没有扩展或改写 PANIC。显式 PANIC 的 UI、Push、持键和音频同步清理继续使用 P23 路径。

## 路由约束

新增寄存器使首次完整实现的音频 PLL RESET 初始化路径达到 10.115 ns，超过原审计的 10 ns 上限。没有放宽上限或加入 false path；最终只把原有 `pll_reset_s` LUT 放到 `state_0` 所在 LUT/FF site，功能网表不变。最终 RESET 路径为 9.756 ns，完整 routed audit 通过。
