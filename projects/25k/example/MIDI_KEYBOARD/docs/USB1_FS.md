# USB1 Full-Speed 面板配置

2026-10-28 新增显式 USB1 FS 配置。默认 `build.sh` / `build.tcl` 仍选择原 USB2/USB3300，不切换当前板上 SRAM/Flash。主机、构建命令、来源审计和电气边界见 [138K USB1 组件](../../../../138k/push2_workstation/usb_a/rtl/usb1/README.md)。

## 不另立板间协议

继续以 [USB 描述符/USB-MIDI 契约](USB_PROFILE.md)、[MK 控制](SCREEN_PROTOCOL.md)、[PL 屏控](PANEL_DISPLAY_PROTOCOL.md) 为线规依据。USB1 只替换物理与速度适配，不改变消息编号、CRC、PL session/序号、显示像素格式、按键/编码器映射、PANIC 或公共参数归属。

| 项目 | USB1 FS 配置 |
|---|---|
| 物理端口 | 25K USB1：D+ L6、D− K6；不是 USB3300 数据口 |
| 时钟 | 50 MHz → PLLA 48 MHz；应用域继续 50 MHz，原四个异步 FIFO 保持 |
| 速度 | 固定 FS 12 Mbit/s；不发送 HS chirp，不使用 ULPI/60 MHz 输入 |
| 设备身份 | 继续使用本地实验 `FB9A:FB9B`，不是获授权的商业 VID/PID |
| 控制端点 | EP0 64 字节；FS-only 对 Device Qualifier 和 Other-Speed Configuration 请求 STALL |
| IF1 MIDIStreaming | OUT01 / IN81，Bulk 64 字节，USB-MIDI 1.0 cable 0 |
| IF2 vendor | OUT02 / IN82，Bulk 64 字节，原 MK/PL 字节流路由 |
| PL 识别 | 原 HELLO/CAPS；Host 必须校验既有画布、格式、tile、超时字段，不只比较 VID/PID |

原 124 字节 FS composite 配置、MIDI jack、字符串和标准 EP0 请求处理复用现有模块；不改变生成的双速描述符 ROM 原字节。FS-only profile 在控制请求入口屏蔽不适用的双速描述符。两向端点提交、DATA toggle、重复包过滤、halt/clear、总线复位、deconfigure 与会话隔离仍由原设备核负责。

## 实现入口

- `rtl/usb_board/midi_usb1_clock.v`：25K 专用 PLLA 与官方 `PLL_INIT`、三拍同步释放；不能拿来替代 138K 的 `PLL`。
- `rtl/usb_board/midi_usb1_link.v`：原生 FS PHY、原 `midi_usb_bridge` 与原异步 FIFO 的组合。
- `rtl/usb_board/midi_usb_fs_state.v`：48 MHz 下持续 SE0 2.5 µs 判定 reset，FS idle J 3 ms 判定 suspend；正常 EOP 不清会话。总线活动解除 suspend，不产生设备主动 remote resume。
- `midi_usb_device.FULL_SPEED_ONLY` / `midi_usb_bridge.FULL_SPEED_ONLY` 默认 0；新配置显式为 1，USB2 仍用原双速状态机。
- `rtl/midi_keyboard_top.v` 根据独立配置 header 选择 USB1 端口，其余外围和业务连接保持；默认根目录 `usb1_profile.vh` 不定义 FS 选择。

新配置由现有 138K `build.py --usb1-identify --usb1-board 25k` 显式准备/综合，复用本目录所有实际业务源和 BLE patch ROM。不是复制整套工程的新生产 builder。配置 header 只有常量，不生成协议或业务实现。新 CST 从原键盘约束剔除 ULPI 端口，加入 USB1 位置/电气属性；SDC 使用 48 MHz 相关生成时钟，保留 FIFO Gray 路由和现有机械/I²C/UART 首级同步约束，不增加异步时钟组来掩盖路径。

USB MIDI/PL 端点仍按原 buffer/FIFO 容量接受整包，忙时 NAK/ready 背压，不覆盖旧消息；CRC/PHY 错误整包回滚，失去 ACK 时保留同一 IN payload。断开/重置按原应用会话规则清队列，PL 恢复不冒充音源初始化。音频工作站的参数应用和 18-bit 生命周期仍在 138K，不搬到设备侧。

## 必须保留的验收缺口

USB1 的 D+ 必须有物理 1.5 kΩ 上拉，参见 [独立 USB1 工程](../../USB1_FS/README.md)；不能靠 FPGA 弱上拉或持续驱高 D+ 替代。接 138K Type-C USB1 前还要核实其 CC Host 角色与 VBUS 防反灌，详见主机说明。本批没有改硬件、上电、下载、固化或读回。

两端数字仿真与完整键盘旧 USB2 回归不等于新 USB1 实物 USB 合规、持续吞吐、LCD 刷屏率、音频延迟或无线并发验收。综合等效 BSRAM 与物理资源分开记录；本批没有 P&R 和 routed 时序/CDC/PLL 门禁，不生成可部署位流。
