# Push 2 USB-A 与完整音频工作站合并

## 2026-09-16 P24 A/B/C 模式响度校准（实体通过）

P24 用相同 MIDI 60、velocity 127、音色、包络年龄和效果关闭的最终 48 kHz PCM 测量，按 A 计权频谱能量对齐五种音色的 A/B/C 响度。A 保持不变，B/C 只对各自增益 ROM 行做固定缩放，谐波比例、包络、活动声部与效果链不变。十五组 32 音和弦及三个最高峰 32 同音极限均无饱和；C 钢琴为峰值余量保留约 0.37 dB。

完整构建 setup/hold 0/0，最差 setup slack +0.087 ns；资源与 P23 相同。位流 SHA256 `7a37311de6df38ed1f0191bd2f07094904df826dd69c4b2007f2e0ec099c1c66`，UserCode `0x00000024`。已从 P23 `0x00000023` 仅写 SRAM并读回，Flash 未写。完整 routed audit 仍只因旧三个 `effect_mask_sync` reset 端点失败。用户完成五种音色、A/B/C 响度、高力度和弦以及既有功能回归后报告“没问题，完美”；验收后只读仍为 `0x00000024`。见 [正式版本记录](BOARD_CURRENT_P24_MODE_LEVEL.json)、[源码审计](P24_MODE_LEVEL_AUDIT.md)、[验证记录](P24_MODE_LEVEL_VERIFICATION.md) 和 [候选绑定](P24_MODE_LEVEL_CANDIDATE.json)。

## 2026-09-16 P23 PANIC 同步硬清理（实体通过）

P23 将明确的 PANIC 改为 CC120：接受事件时立即清 held、延音/释放扫描、声部分配可达状态、处理流水线和效果尾音；CC123 继续作为正常 RELEASE。10 bit PANIC 世代沿现有状态快照清 Push mapper/画面、AE350 UI gate 和电脑窗口重复状态，不改变 pitch 低 22 bit、Push 连续压力、声部分配策略或效果选择/顺序。

完整构建 setup/hold 为 0/0，最差 setup slack +0.087 ns；Logic 34848、Register 25381、BSRAM 253、DSP 43.5。位流 SHA256 `8bd54510c9e0637420a49c9e4235c27659a9e48417a97eec35137e322dda25b6`，UserCode `0x00000023`。已从 P22 `0x00000022` 仅写 SRAM 并读回，Flash 未写。用户确认电脑与 Push PANIC、持键防重触发、电脑长按、Push/连续压力/屏幕/灯光、HDMI、耳机和效果链均正常；验收后只读确认仍为 P23。完整 routed audit 仍只因原三个 `effect_mask_sync` reset 端点缺口失败。见 [正式版本记录](BOARD_CURRENT_P23_PANIC_SYNC.json)、[源码审计](P23_PANIC_SYNC_AUDIT.md)、[验证记录](P23_PANIC_SYNC_VERIFICATION.md) 和 [候选绑定](P23_PANIC_SYNC_CANDIDATE.json)。

## 2026-09-15 P22 电脑键盘连击（实体通过）

修复现有电脑 Tk 串口入口的长按去重行为：短按一次，长按 300 ms 后每 80 ms 发送 Note Off/On，松键立即停止重复计时器；原 X11 松键窗口和声部释放包络保留。空格延音期间暂停连击。Tk 和 UART→音频定向仿真通过，完整构建 setup/hold 0/0、最差 setup slack +0.010 ns，资源与 P21 相同。完整 routed audit 仍因原三个 effect_mask reset 端点缺口失败。

新位流 UserCode `0x00000022` 只是 P22 发布标识，硬件生产输入与 P21 相同；功能修复在电脑脚本。本次已读回 P21 `0x0000D14C`、仅写 SRAM、再读回 `0x00000022`，Flash 未写；实体键盘验收后再次只读确认仍为 P22。U15 板端回报仍为 0 字节；窗口排旧缓存 2 秒后进入标黄的“单向演奏”状态，不伪造板端状态。用户确认电脑控制正常，会话中 Note On/Off 各 254 次且每个音高完全配对；随后确认 Push、连续压力、HDMI、耳机和效果链均正常。受保护原 Xilinx Web Serial 页也存在 `event.repeat`/active 去重根因，本轮未修改。P21/P10 回退完整保留。见 [正式版本记录](BOARD_CURRENT_P22_KEYBOARD_REPEAT.json)、[源码审计](P22_KEYBOARD_REPEAT_AUDIT.md)、[验证记录](P22_KEYBOARD_REPEAT_VERIFICATION.md) 和 [候选绑定](P22_KEYBOARD_REPEAT_CANDIDATE.json)。

## 2026-09-15 P21 屏幕硬件装包（实体通过，延迟约 0.35 秒）

用户确认 P20 力度正常，屏幕操作仍约 0.6 秒。P21 用同一 48 MHz 时钟域的装包状态机替代 CPU 逐像素读、XOR、暂存及逐字节搬运，经原寄存器握手直接装载原 512 字节 USB FIFO；每包 1793 周期、约 37.35 µs。模拟 CPU 阻塞装包、音频连续运行、NAK 重装及字节一致性已通过。用户实测屏幕延迟降至约 0.35 秒，画面、连续压力、灯光、HDMI、耳机和效果链正常。327696 字节在 12 Mbit/s 下仅载荷就需 218.464 ms，因此 0.2 秒目标未记为通过。

最终 P&R setup/hold 为 0/0，最差 setup slack +0.010 ns；Logic 33830、Register 25192、BSRAM 253、DSP 43.5。位流 SHA256 `77a4a62e8e0323c94f4c58b73e9de0b1142a5fa612966c4c7f86de3a346fb039`，UserCode `0x0000D14C`；已从 P20 `0x0000F9B7` 单独写入 SRAM并读回，Flash 未写。见 [P21 阶段记录](P21_SCREEN_LOADER_VERIFICATION.md) 和 [版本记录](BOARD_CURRENT_P21_SCREEN_LOADER.json)。

## 2026-09-15 P20 力度校准与 Push 旧帧立即重启（力度通过，延迟约 0.6 秒）

P20 将 Push pad 的每个非零原始力度增加 28 并饱和到 127，精确实现 `002` → `030`；映射同时用于 Note-On、poly-aftertouch、channel pressure、声音事件和 Push 状态显示，零值仍为零。屏幕保留官方 16 字节帧头和 640×512 字节完整帧格式；传输旧保活帧期间检测到模式、音色、效果、路由或持键变化时，丢弃尚未发送的旧帧尾部并立即从新帧头重启，避免先等旧帧完成再排一个新帧。连续压力数值不触发中止，以免压力不断变化导致永远没有完整帧提交。

P&R setup/hold 0/0，最差 setup slack +0.247 ns，Logic 34293、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `50bbf9eeddbc2184c5deeecc89340041b28e09e09f8c07288da05e0cb56084cb`，UserCode `0x0000F9B7`；已从 P19 `0x00005169` 单独写入 SRAM 并读回，Flash 未写。完整帧仍约需 450 ms，本次实体确认重点是 `002` → `030` 的声音/显示结果，以及离散操作不再承担旧帧尾部加新帧的近一秒等待。见 [版本记录](BOARD_CURRENT_P20_FORCE_SCREEN_RESTART.json) 和 [阶段验证](P20_FORCE_SCREEN_RESTART_VERIFICATION.md)。

## 2026-09-15 P19 Push 屏幕完整帧保活（保活通过，交互延迟由 P20 取代）

P18 实体确认连续压力正常，但静止超过约 2 秒后 Push 按官方行为自动黑屏。P19 保留状态变化立即发帧，并在上一完整帧结束后 1000 ms 发送合法完整保活帧；不试验协议保留的短帧或局刷格式。P&R setup/hold 0/0，Logic 33760、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `08db9c8fd1c97e9a9bcad63e330eaaa43fe6158ed022ae13f3793d4b825adab9`，UserCode `0x00005169`；已从 P18 `0x0000D914` 单独 SRAM 下载并读回，Flash 未写。用户实体确认屏幕保活和连续压力正常，随后复测确认操作刷新仍接近一秒；压力灵敏度也未在本阶段改动。这两项由 P20 处理。见 [版本记录](BOARD_CURRENT_P19_PUSH_SCREEN_KEEPALIVE.json) 和 [阶段验证](P19_PUSH_SCREEN_KEEPALIVE_VERIFICATION.md)。

## 2026-09-15 P18 官方 poly-aftertouch 与事件驱动 Push 屏幕（压力通过，屏幕由 P19 取代）

P18 显式发送 Ableton 文档规定的 `Set Aftertouch Mode 0x1E, mode 1`，使按住 pad 的持续压力以带 note 的 poly key pressure 返回并只更新原声部 expression。Push 屏幕改为 UI 状态变化时才发送合法完整帧，空闲每轮轮询 MIDI，传帧中每 4 个包轮询；不再让无变化整帧持续占用 FS 链路。P&R setup/hold 0/0，Logic 33760、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `b9ef014335aec28ac3f1272c128b710ca4cb8bfe87a93044c88d168eee5af72f`，UserCode `0x0000D914`；已从 P17 `0x0000F123` 单独 SRAM 下载并读回，Flash 未写。用户实体确认连续压力正常，灵敏度略高；静止屏幕因 Push 的 2 秒无完整帧黑屏规则而未通过，由 P19 保活修复。见 [版本记录](BOARD_CURRENT_P18_PUSH_AFTERTOUCH_SCREEN.json) 和 [阶段验证](P18_PUSH_AFTERTOUCH_SCREEN_VERIFICATION.md)。

## 2026-09-15 P17 连续压力兼容与 Push 屏幕调度候选（待本轮实体验收）

P17 在 P16 基础上兼容 Push 的 CIN A poly-aftertouch 与 CIN D channel-pressure 两种压力包；按住同一 pad 时只更新已有声部的 expression，不重新分配音符。屏幕仍使用原 16 字节帧头和 640 个 512 字节包，固件改为每 16 包轮询 MIDI、每 32 包服务灯光，去掉每包空闲 IN 轮询造成的额外等待。P&R setup/hold 0/0，Logic 33820、Register 25164、BSRAM 253、DSP 43.5。位流 SHA256 `90a3d5563149a5ae40c431647fdb229730e8f3078812be4657e5d22f34fe9e02`，UserCode `0x0000F123`；已从 P16 `0x0000C706` 单独 SRAM 下载并读回通过，Flash 未写。RTL、CPU/USB 和生产固件回归通过；真实压力和 Push 屏幕延迟待本轮用户验收，见 [版本记录](BOARD_CURRENT_P17_PRESSURE_PUSH_LATENCY.json) 和 [阶段验证](P17_PRESSURE_PUSH_LATENCY_VERIFICATION.md)。

## 2026-09-15 P16 连续压力与 Push 屏幕刷新候选（待本轮实体验收）

P16 在 P14 C 模式 32 声部基础上加入 Push USB-A poly-aftertouch 连续压力控制，并修复 Push 屏幕只显示首帧的问题：主机每次发起屏幕帧请求都会提交新的 control/options、pad held、note 和 velocity 快照。P&R setup/hold 0/0，Logic 33793、Register 25164、BSRAM 253、DSP 43.5。位流 SHA256 `85f6eba4b9db18468b300a58567bfb4a096123fbf699eea041ecc8f426450e82`，UserCode `0x0000C706`；已从 P14 `0x00005610` 单独 SRAM 下载并读回通过，Flash 未写。RTL 压力、声部和 Push 刷新回归通过；真实压力听感、Push 动态画面、HDMI 和耳机仍待用户验收，见 [版本记录](BOARD_CURRENT_P16_PRESSURE_PUSH_REFRESH.json) 和 [阶段验证](P16_PRESSURE_PUSH_REFRESH_VERIFICATION.md)。

## 2026-09-15 P14 C 模式 32 声部候选（已保留，可回退）

P14 在 P13 共享 DDR 显示数据基础上恢复 C 模式 32 声部：统一振荡器使用 1024×80 bit slot RAM，C 模式按 32 个 voice 映射，上层满载判断检查完整 32 位。RTL 满载扫描为 1024 slots、sample latency 1035/1600 个 76.8 MHz 周期；P&R setup/hold 0/0，Logic 33781、Register 24931、BSRAM 253、DSP 42.5。位流 SHA256 `5249dc938d6288e87a2e5ca2ae3ce21808a3c11671b3b47f38b767754a869a86`，UserCode `0x00005610`。已从 P13 `0x0000F002` 单独 SRAM 下载，写后读回通过，Flash 未写。实体 HDMI、Push、耳机、32 声部声音和交互延迟待确认，见 [版本记录](BOARD_CURRENT_P14_C_MODE_32.json) 和 [阶段验证](P14_C_MODE_32_VERIFICATION.md)。

## 2026-09-15 P13 阶段 4（已保留，可回退）

P13 已完成共享 DDR → HDMI reader → Push 64 位摘要 mailbox 的 RTL、仿真、P&R 和 SRAM 下载；它是 P14 的直接回退版本，UserCode `0x0000F002`，写前 P12 `0x0000C8A1`、写后 P13 均读回，Flash 未写。位流 SHA256 `894c51d40336fe86213adfddb3b151bc2c5d019b3cbd2e46a62acc0aa696539c`，setup/hold 0/0，最差 slack +0.024 ns。Push 仍走原 USB-A 协议，见 [版本记录](BOARD_CURRENT_P13_PUSH_SHARED_SUMMARY.json) 和 [阶段验证](P13_VERIFICATION.md)。

## 2026-09-15 P12 当前 SRAM 候选（待实体回归）

当前板上 UserCode `0x0000C8A1`。HDMI 已从 P11 版本化双 bank DDR 紧凑块读取 waveform、李萨如位图、频谱列和效果元数据，并保持原 dashboard、RGB565 framebuffer 与 scanout。setup/hold 违例 0/0，最差 slack +0.002 ns；Logic 33502、Register 24893、BSRAM 254、DSP 42.5。写前 P11 `0x0000D767`、写后 P12 `0x0000C8A1` 均读回，Flash 未写。见 [版本记录](BOARD_CURRENT_P12_HDMI_SHARED_DISPLAY_READER.json)、[阶段验证](P12_VERIFICATION.md) 和 [数据布局](DISPLAY_DATA_LAYOUT_V1.md)。Push 读取同一 descriptor 留在阶段 4；当前等待用户检查 HDMI、Push、耳机和效果链实体运行。

## 2026-09-13 P10 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0x0000ED8B`。HDMI 卡片顺序已接入真实音频调度：一至三个不同效果按选择次序串联，前一级输出进入后一级；单个效果只处理一次。选满三个后再按任一效果仍会清零并淡出到精确干声。P9 已获用户“没问题，继续”反馈。见 [版本记录](BOARD_CURRENT_P10_SERIAL_EFFECT_ORDER.json) 和 [分层验证](P10_VERIFICATION.md)。只写 SRAM，Flash 未写。

656 帧效果单元仿真、Push 统一事件回归、完整 CPU/USB/音频回归、综合/布局布线、后布局音频审计及 SRAM 写后数字遥测均通过。setup/hold 违例 0/0；BSRAM 248/340，DSP 42.5/298。旧完整 DDR/video 审计仍保留 P8/P9 已知的三个显示效果 mask 复位端点覆盖缺口。实际顺序听感、实体 HDMI 动画、Push 和耳机输出待用户验收。

## 2026-09-13 P9 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0x0000C2D3`，选满三个不同效果后再按任一效果键会全部清零，下一次按键才开始新一轮。去重与左右滑动保留。P8 已获用户“没问题”反馈。见 [版本记录](BOARD_CURRENT_P9_CLEAR_ALL_EFFECTS.json) 和 [分层验证](results/build_20260913_175110_528097/P9_VERIFICATION.md)。未写 Flash。实际音频串联和旧显示复位审计覆盖缺口仍待处理。

## 2026-09-13 P8 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0xA64B`，左右连续移动动画与队列去重已下载，未写 Flash。见 [版本记录](BOARD_CURRENT_P8_SLIDE_UNIQUE_QUEUE.json) 和 [分层验证](results/build_20260913_172135_776685/P8_VERIFICATION.md)。未选满时重复按同一种效果不占新槽；选满三种后下一次按键开始新一轮。

源码核对纠正：当前音频只接收 effect_mask，并叠加 wet 输出；UI 顺序尚未接入实际串联处理。旧文档的“固定串联”不能作为现版验收结论。综合/PNR、功能仿真、SRAM 下载通过；旧路由审计仍有六个显示复位例外的覆盖缺口，失败报告保留。硬件听感与实际 HDMI 动画待用户验收。

## 2026-09-12 热插拔修正版

用户反馈 D50E 正常操作“完美”，但插拔 Push USB 后失去 MIDI、灯光、屏幕。D50E 原固件只在启动时枚举；现已补齐失联检测和重新枚举，保持所有 RTL、音频、HDMI 三图、DDR、AE350 和约束与 D50E 相同。

修正版已 SRAM 下载，见 [HOTPLUG_READY.json](HOTPLUG_READY.json) 和 [BOARD_CURRENT.json](BOARD_CURRENT.json)。**UserCode 仍为 D50E，必须用 SHA256 区分新旧固件**：新位流 `0e5a3cd5d6641c76777d76e1b5f5feddf65d661586ef0de14587cf0e1f09c1af`，构建 `results/build_20260912_001551_009746`。门级初始化比较的 359 个变化块全部属于 USB 固件 RAM。

- EP2 IN 连续 50 ms 没有有效 DATA/NAK 回复 → 清连接状态，由现有 RTL 松音和重置灯光/屏幕会话 → USB 复位、枚举、各方向 DATA0 重新开始 → 完整初始化恢复。
- 空闲 MIDI 的 NAK 是活跃连接，不误判断线；灯光/显示 NAK 重试间仍轮询 MIDI。USB OUT STALL 本身不停止正常 MIDI。
- 使用实际固件的离线测试通过：枚举失败重试、静默 NAK、短暂错误、计时回绕、重复 IN 包、ACK/NAK toggle、屏幕中途拔线、重连后 MIDI 和完整帧。
- 完整构建和路由审计通过，setup/hold 0，资源仍为 Logic 29178、BSRAM 244/340、DSP 42.5/298。下载后音频 48 kHz、HDMI 60 帧/秒、DDR/AE350/UI 数字检查通过。实际拔插验收以 `BOARD_CURRENT.json` 的对应捕获记录为准。

本轮下载前曾读到旧 Flash 版本 18D6；用户表示挪动板子时可能短暂断电。它与 USB 枚举问题不同：SRAM 位流断电即丢，重新上电会加载原 Flash。没有为此改写 Flash。

## D50E 首次合并记录（2026-09-11）

**当前：用户已在后续消息明确授权烧录，D50E 已 SRAM 下载并回读通过，Flash 未写。** 版本绑定及当前验收状态见 [BOARD_CURRENT.json](BOARD_CURRENT.json)。HDMI 三种图形、音频、DDR、AE350/UI 全部保留。

10 秒板端数字验证通过：音频 48000 样本/秒；HDMI 渲染/扫描均 60 帧/秒且欠载 0；DDR 和 AE350/UI 检查通过。Push 已配置，84 条灯光命令 ACK，屏幕持续约 2 帧/秒，OUT 错误 0。首次稳定窗口没有新增映射事件；累计 13 个映射事件不能充当本次人工按垫验收。耳机听感与实际屏幕画面等待用户确认。

此前离线阶段遵守了“不烧录、不占用板端”的要求；`READY.json` 和构建内 `verification_summary.json` 保留为该阶段的不可混用验收快照。

**离线交付已完成：D50E**，见 [READY.json](READY.json)。构建目录 `results/build_20260911_210232_835684`；原音频/DDR/HDMI/AE350 检查与新增 USB/跨时钟布线路径检查全部通过，setup/hold 违例均为 0。位流 SHA256：`4d8648cbc1e059e2b0367fbd6537fe8ad2010426bf14bbffe7214e0855bc5a17`。

资源：Logic 29178/138240，BSRAM 244/340，DSP 42.5/298。相对 3BE2 完整工作站，Logic +302，BSRAM +30，DSP 不变。D50E 已完成 SRAM 下载和数字运行验证；用户声光验收与此分开。

链路：Push 2 ⇄ J18 USB-A（D+ H13、D− G13）⇄ FPGA 内 VexRiscv USB Host + RTL PHY ⇄ 既有 Push 控制映射 ⇄ 异步事件 FIFO ⇄ 原音频工作站。

这条已上板工作的参考方案使用 **VexRiscv 固件处理 USB**，不属于“USB 全部纯 RTL”。音频仍由 RTL 逐样本运行，AE350 继续负责工作站 UI/控制；不使用 CH569、电脑中转或 DDR 来传演奏事件。

## 复用范围

- 音频/HDMI/DDR/AE350：冻结的 `../results/workstation_20260911_174045_306332`（3BE2）。保留精确 48 kHz、三模式/五音色、力度/弯音/滑音/颤音、延迟/合唱/混响、PT8211、三种分析图和原有 PC/G1 控制入口。
- USB：`migration/midi_device_reference/push2_usb_host/results/fs_surface_build_20260911_200312_216160`（8FC3，SHA256 `f3873e508df04b9caf0b3664a2b9c23d5bcae07d5bca0488b2b7234c5447c0c1`）。VexRiscv、USB Host、PHY、512 字节收发 FIFO 及 PLL helper 源码保持一致；仅给 SoC 增加控制寄存器接口。
- Push 映射、状态灯和屏幕像素使用既有 `push2_controls`、`push2_midi_rx`、`push2_lights`、`push2_led_tx`、`push2_surface_pixels`。屏幕显示实际合成器状态，经应答握手快照传入；电脑改参数也能反馈到 Push。
- 删除新顶层里的 CH569 HSPI 接口和旧 J18 Host 实例。原源码/旧位流/证据保留在原位置。

## 操作映射

| Push 操作 | 合成器功能 |
|---|---|
| 64 垫，Note 36–99 | 音符/力度；按住不重复触发，松开或速度 0 释放 |
| 触摸条 Pitch Bend | 弯音；触摸条松开 Note 12 Off 回中心 |
| 上排 CC 102–104 | A / B / C 模式 |
| 上排 CC 105–109 | 笛 / 弦 / 铜管 / 马林巴 / 钢琴 |
| 下排 CC 20–22 | 延迟 / 合唱 / 混响开关 |
| 下排 CC 23–26 | 立体声 / 左 / 右 / 静音 |
| CC 27 或 29 | 硬 PANIC：立即清声部与效果尾音 |
| 旋钮 CC 71 或 79 | 音量；有符号相对增量，范围钳位 |
| 旋钮 CC 72 / 73 | 颤音 / 滑音 |

A/B/C 改变振荡器分配，原合成器在所有释放尾音结束后才提交模式。64 垫映射不等于三种模式都有 64 路同时发声；保留原核心声部分配。

## 时序与 USB 实机特例

USB 时钟 48 MHz；音频时钟 76.8 MHz，每 1600 周期一帧，即准确 48 kHz。音频事件 FIFO 满时，只让 USB CPU 的寄存器写等待；音频不等待灯光、屏幕、AE350 或 DDR。

MIDI IN 保留 DATA0/DATA1 去重；EP1 OUT 屏幕与 EP2 OUT 灯光分别维护 toggle，仅 ACK 推进。发送屏幕每个 512 字节包之前轮询 MIDI；OUT NAK 重试间也轮询。灯光命令保持至 USB ACK，失败可重试。

当前 Push 实测 Full-Speed 身份是 **2982:9999，9 字节配置描述符且接口数为 0**，但 EP1 OUT 屏幕和 EP2 IN/OUT MIDI 可用。按已验证设备特例处理，不能用旧 HS 描述符条件将其拒绝。屏幕保留 16 字节帧头 + 640 个 512 字节包及行填充/XOR 编码。

参考 demo 的用户已确认垫灯/屏幕，且有实际 MIDI 输入记录；**这不等于合并工作站已真机验收**。合并版已测得 Push 屏幕传输约 2 帧/秒、HDMI 60 帧/秒；操作延迟和耳机听感仍待用户确认。首次 D50E 沿用参考固件的无热插拔恢复限制；2026-09-12 修正版已补恢复流程。USB IN 错误计数仍未实现，回读标为未知。

## 离线构建与验证

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/run.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/p23/run.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/audit.py <新构建目录>
```

`LATEST_BUILD.txt` 指向最新构建尝试；必须结合该目录的 `tool_result.json` 和 `usb_a_audit.json` 判断是否通过，不能只看指针。所有结果带 `hardware_tested:false`。

- MMIO/CDC 仿真：450 个事件按序通过，1746 个等待周期，覆盖 64 垫、零速度松键、通道/端口过滤、模式/音色/效果/声道/旋钮/触摸条；LED 不 ACK 时不阻塞音频事件；输出 960×160 像素并验证行填充。
- Vex 实际执行测试固件 → 真正 SoC 寄存器总线 → 既有合成器：3696 帧 PCM，其中 3574 帧非零；A/B/C、五音色、三效果、表达/声道路由/松音通过，帧间隔始终 1600 周期，音频错误计数为 0。AE350 总线时钟全程停止。
- `sim/run.py` 的测试固件只用于仿真。实际位流嵌入的是 `firmware.c` USB Host 固件，不是测试程序。

USB-A 工作站版本的 P138 回读应使用 `../scripts/control.py --usb-a`。它保留 A138/C350/K138/E138，P138 给出收到字数、映射数、灯光 ACK、屏幕帧数和 OUT 错误。USB IN 错误显示 `null`；不把旧 CH569 诊断字段套在这个版本上。此命令会打开串口；离线阶段未执行，后续经用户授权上板后已用于只读回读。

后续 30 秒交互窗口（序列 108–137）：新增 7 个映射事件、8 条灯光 ACK、58 帧 Push 屏幕，OUT 错误 0；实际核心回读观察到左右/立体声、钢琴、C 模式变化。该窗口未采到持键状态，不推断耳机发声或实际画面已由用户验收。记录：`../results/capture_20260911_212820_205862/interaction_summary.json`。

## P2–P5 核对（2026-09-13）

本轮未改 RTL、未删除 HDMI/DDR/AE350 或原音频旁路，核对结果保存在 [`P2_P5_STATUS.md`](../results/p2p5_regression_20260913_010545/P2_P5_STATUS.md) 和 `p2p5_status.json`：

- P2：48 kHz 下沿用 192 kHz 频率表乘 4，MIDI 0–36 最大误差 0.00449 cents；32 位相位连续，滑音/颤音按帧更新，不加 PLL。
- P3：固定链顺序为合成混音 → 延迟 → 合唱 → 混响 → 路由 → PT8211；mask 0=关闭、1/2/3 可单独或叠加、7=全开；映射仿真覆盖 1/3/7，关闭由复位/清零路径覆盖。
- P4：256×64 位曲谱 RAM、绝对帧、LED 掩码、开始/停止/完成状态及 APB 入口均已存在；不产生音符。
- P5：已统计当前绑定 CC 20–29、71–73、79、102–109。已按 Ableton MIDI Implementation Chart 补齐物理按键 CC 清单（3/9、28–31、35–63、85–90、102–113、116–119）；未根据另一台 2982:1967 Push 的 CC14/15 记录猜测映射。曲谱/录音按键需要把 UI 命令接入统一事件协议后再绑定。
