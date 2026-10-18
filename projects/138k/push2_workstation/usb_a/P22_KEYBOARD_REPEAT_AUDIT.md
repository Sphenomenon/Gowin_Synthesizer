# P22 电脑键盘连击源码审计

基线：main / 4f40137，P21 源码 f1323dd；审计开始时工作区干净、无 remote。P21 与受保护 P10 位流 SHA256 均与交接值一致。只修改现有电脑入口及构建版本标识，不增加 performance keyboard 页面。

## 输入与事件路径

1. 受保护的原 Xilinx 工程 `fpga/app/index.html` 另有 Web Serial 调试台：`keydown` 明确在 `event.repeat` 时返回，`noteOn` 还用 active set 去重，所以它同样只在首次 keydown 产生 Note On。该页面不属于 P21 当前 Gowin 工程，本轮只读审计，未修改。当前迁移工程使用 `ae350/play_keyboard.sh` 启动 `ae350/scripts/keyboard_midi.py` 的 Tk 窗口；`KeyPress/KeyRelease` 使用物理 keycode，25 个音符映射保持原样。
2. `key_press` 合并同 X11 时间戳的 Release/Press 自动重复对；真实不同时间戳的快速松按先调用 `finish_release`。原 `pressed` 去重直接返回，`Notes.press` 还有 `held` 去重，因而长按只发送首次 Note On。这是本次缺陷来源，发生在串口发送之前。
3. `send` 向调试器串口发送通道 1 原始 MIDI，115200/8N1、无硬件流控。Note On 为 `90 note velocity`，Note Off 为 `80 note 00`。串口写超时 100 ms，失败走已有待释放 recovery。K138 每秒回读不是逐事件 ACK。
4. 完整构建中的 `gw138k_push_workstation_top` → `gw138k_usb_controlled_audio.u_audio` → `gw138k_controlled_adapter.u_pc_rx`，V14 PC RX 在 50 MHz 域接收。`u_pc_cdc` 为单字节保持/toggle 握手，转到 76.8 MHz 音频域；没有源端 ready，忙时丢弃会计数。
5. `gw138k_event_workstation.pc_decoder` 解析 MIDI/running status，FIFO 深度 32。满且不能同时 pop 时计 overflow；无 held 去重。`gw138k_three_event_arbiter` 在完整事件层轮询 G1/PC/CPU，一级寄存器，随后 workstation 再一级寄存器。消费端 `ready` 受样本、装载、混音、模式切换和延音释放扫描影响。
6. Note On 更新 workstation `held` 并交给 `unified_oscillator_engine` 分配空闲声部；Note Off 匹配同音高尚未释放的一个声部，不重复释放旧尾音。原包络继续到 IDLE 才回收资源。音频域每 1600 周期处理一帧，48 kHz，经已有串行效果链和 PT8211 输出。

G1 MIDI 是独立 P16/31250 UART、独立字节 CDC 和解析队列。Push 2 仍从 J18 H13/G13 进入 48 MHz USB Host，经过既有映射/持垫去重、64 深度异步事件 FIFO，进入音频域并与 AE350 控制事件仲裁，再进入上述完整事件仲裁。FIFO 满向 USB MMIO 传播等待，不停止音频。AE350/APB/UI/DDR 不在 PC note 关键路径内。

## 最小修改与边界

- 首次音符立即发送；按满 300 ms 后以 80 ms 间隔发送 Note Off/On。采用 Tk 每物理音符键一个计时器，系统重复事件仅维护按住状态，不能增开计时器。UI/串口停顿后不补发积压连击。
- 收到 KeyRelease 当次立即取消重复计时器。保留原 30 ms X11 配对窗口再发最终 Note Off；不同时间戳的再次按下无需等窗口结束。同时间戳重复对恢复原截止时间。实体事件到主机的延迟和原释放包络不包含在“立即停止重复”内。
- CC64 延音时，板端会推迟 Note Off；如果继续连击就会积累未释放声部。因此本机空格延音期间暂停连击，放开踏板后按原节拍继续，不发送额外全局 CC 去强制释放其他来源。界面明确提示此行为。
- PANIC/模式切换沿用原 `Notes.drain` 和物理按键锁存，只取消本轮新增计时器；失焦、关闭、断线同样取消。没有扩展 UI/Push/PANIC 同步清理。
- P21 下载后的短 UART 窗口已有 0 条记录，本轮 P22 也观测到 U15 返回 0 字节。为不把只读回报故障误判为 V14 输入故障，当前窗口在排出 2 秒 FTDI 旧缓存后进入明确标黄的“单向演奏”状态；不会伪造板端状态。若之后收到有效 K138，会自动恢复双向确认和原超时保护。
- 原 PC/G1/Push/CPU 按音高共享 held/释放和全局控制，已有跨来源同音高所有权限制仍存在；本轮不引入来源隔离或改变声部分配。
- 单键重复 75 字节/秒，25 键上限 1875 字节/秒，占 115200/8N1 有效 11520 字节/秒约 16.3%。只核对这一正常负载的队列及音频，不增加极端压力测试。

## 构建与验收计划

硬件逻辑/固件保持 P21。使用 Gowin 官方本地 SUG1220-2.0E 的 `set_option -user_code`，仅给新构建副本写入发布标识 `00000022`；进行完整综合和布局布线，不复用综合结果。电脑脚本 SHA256 与位流 SHA256 共同绑定 P22，因为功能修复在主机脚本。

定向验证覆盖短按、长按、X11 重复对、松键、快速重按、多键、延音、原 PANIC 锁存、失焦/关闭/断线及实际 MIDI→音频链。完整 routed audit 不规避旧 `effect_mask_sync_[0..2]_s0/RESET` 缺口。只有检查构建后才按 P21 `0x0000D14C` 写前读回、SRAM 写入、新 UserCode 写后读回。Flash 未写；电脑键盘、Push、连续压力、HDMI、耳机和效果链均由用户实体确认正常。
