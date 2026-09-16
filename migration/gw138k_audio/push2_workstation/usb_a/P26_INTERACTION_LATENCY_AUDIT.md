# P26 真实交互延迟路径审计

2026-09-16：本阶段先量化电脑串口、DIN MIDI、Push 事件和 Push 屏幕刷新路径，再只优化确定存在的屏幕装包开销。没有改写输入架构、音频事件队列、声部分配、Push pad held/连续压力、PANIC、HDMI、DDR、效果链或公开 USB 协议。

## 音符到音频路径

电脑入口仍是 115200 bit/s UART，三字节 Note On 在线路上需要 260.417 us；DIN MIDI 仍是 31250 bit/s，三字节需要 960 us。两者经过原接收器、事件 CDC、音频 core、48 kHz 样本提交和 PT8211/DAC16 观察点。Push 测量边界从 USB 固件已经接受并写入 MMIO 的事件开始，因此不包含实体 pad、USB IN 事务和主机轮询时间。

五个 48 kHz 相位偏移的数字测量结果：Push MMIO 接受后到 core 为 0.141–13.462 us，到最终 DAC16 为 104.784–124.784 us；电脑从首个 UART 起始位到 DAC16 为 385.596–401.436 us；DIN MIDI 为 1073.056–1088.876 us。这些结果用于分离数字链路开销，不能充当实体交互延迟。

## Push 屏幕路径

P21 状态机已经在 USB 48 MHz 域读取 256 个 RGB565 像素、执行原交替 XOR 并生成一个 512 字节包，但仍让每个输出字节经过 CPU 寄存器写应答。P26 新增 `push2_screen_fifo_streamer`，在同一 48 MHz 域把完全相同的字节直接推入现有 512 字节 USB TX FIFO。CPU 在一个完整包装入前仍阻塞，原 token、PID、ACK、NAK 重装和 DATA toggle 继续由既有固件处理。

每包装载由 1793 周期、37.354 us 降到 769 周期、16.021 us；640 包共减少 655360 个 48 MHz 周期，即 13.653 ms。公开格式仍是 16 字节帧头加 640 个 512 字节像素包，12 Mbit/s 纯载荷下限仍为 218.464 ms，不能把 0.2 秒记为达到。传帧期间仍每 4 个像素包轮询 MIDI、每 32 包处理灯光；P19 保活和 P20 旧帧重启也未改变。

## 时钟、队列和背压

streamer、USB Host 和 TX FIFO 全在原 48 MHz 域，没有新增 CDC 或 BSRAM。像素读取继续使用原 MMIO `ready` 背压；固件只有在上一 USB OUT 事务结束后才发起下一包装载，512 字节正好填满现有 FIFO。CPU 屏幕装载命令仍等到完整包完成，NAK 时从包头重新装载，音频事件 FIFO 与 USB→音频 backpressure 不变。

P23 PANIC 定向回归覆盖 CC120 硬清理、CC123 正常 RELEASE、Push/AE350/电脑 UI 状态，全部通过。本阶段没有扩大 PANIC 功能。USB IN error 诊断仍为 `null`。

## 物理约束审查

第一次完整 P26 实现 `build_20260916_185814_508399` 的 setup/hold 为 0/0，但音频 PLL_INIT RESET 全传播为 10.011 ns，超过原 10 ns 独立审计门槛，因此该位流没有下载。根因是已有 R39C72 整 tile 约束允许 helper 单元在子位置间改变，RESET 最后一段路由从 P24 的 4.444 ns 增到 4.736 ns。

最终实现把原接受布局中四个 helper 寄存器固定到其实际子位置，并把同一 tile 的 reset LUT 固定到空余子位置；没有增加时序例外或放宽门槛。最终音频 PLL_INIT 最大传播为 9.945 ns。完整 routed audit 仍失败，错误仍且只有旧的 `u_managed/effect_mask_sync_0_s0/RESET`、`_1_s0/RESET`、`_2_s0/RESET` 覆盖缺口；不能把独立音频审计通过写成完整 audit 通过。
