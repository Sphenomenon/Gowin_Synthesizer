# USB2 MIDI 与屏幕控制接口框架

本目录的 USB 设备目标是 USB 2.0 复合设备：标准 USB-MIDI 1.0 承载键盘 MIDI，独立 Vendor Bulk 接口承载屏幕控制。机器可读的接口规划见 [`config/usb_composite.json`](../config/usb_composite.json)。当前配置是设计目标，尚未生成描述符 ROM、接入 USB3300 或完成真实枚举。VID/PID 保持 `null`，需要在枚举实现前使用有授权的标识；旧 CDC 例程的本地测试编号不构成产品分配。

| 接口 | USB Class / Subclass / Protocol | 端点 | 用途 |
|---|---|---|---|
| IF0 AudioControl | `01 / 01 / 00` | 无 | Audio 1.0 类头，关联 IF1 |
| IF1 MIDIStreaming | `01 / 03 / 00` | OUT `01`、IN `81`，Bulk | USB-MIDI 1.0，虚拟线缆 0 |
| IF2 ScreenControl | `FF / 00 / 00` | OUT `02`、IN `82`，Bulk | 屏幕控制请求与应答 |

IN/OUT 方向相对 USB 主机。所有 Bulk 端点的目标最大包长为 HS 512 字节、FS 64 字节；USB 数据包可以包含多个完整的 4 字节 MIDI Event Packet。设备级 `bDeviceClass=00`，功能由接口声明。实际描述符实现还需要配置总长度、AudioControl 类头、MIDIStreaming 类头、MIDI Jack、类专用端点关联、字符串、Device Qualifier 与 Other-Speed Configuration，以及 EP0 标准请求。FS/HS 的声明与包长必须随当前协商速度一致。

MIDI Jack 规划为：Embedded IN Jack 1 → External OUT Jack 2 对应主机到键盘；External IN Jack 4 → Embedded OUT Jack 3 对应键盘到主机。OUT `01` 的类专用端点关联 Jack 1，IN `81` 关联 Jack 3。每个方向提供一个虚拟线缆。屏幕协议见 [`SCREEN_PROTOCOL.md`](SCREEN_PROTOCOL.md)，主机通过原始 USB Bulk API 访问 IF2；操作系统访问授权和接口绑定留到主机集成阶段验证。

## 编解码接口

[`rtl/transport/usb_midi_codec.v`](../rtl/transport/usb_midi_codec.v) 将一条完整 MIDI 消息与一个 USB-MIDI Event Packet 互转，不包含 PHY、USB 枚举、传输重试或字节流成帧。模块时钟可以来自后续应用域；接到 USB3300 的 60 MHz ULPI 域时，跨域必须使用异步 FIFO 或经过验证的桥接。

| 接口 | 字段 | 约定 |
|---|---|---|
| 发送 MIDI | `tx_valid / tx_ready`、`tx_message[23:0]`、`tx_length[1:0]` | 消息 `{status, data1, data2}`，长度为 1/2/3 个 MIDI 字节 |
| 发送 USB | `packet_tx_valid / packet_tx_ready`、`packet_tx_data[31:0]` | `{data2, data1, status, cable+CIN}`，低字节先上链路 |
| 接收 USB | `packet_rx_valid / packet_rx_ready`、`packet_rx_data[31:0]` | 与发送 USB 相同字节序 |
| 接收 MIDI | `rx_valid / rx_ready`、`rx_message[23:0]`、`rx_length[1:0]` | 未使用的数据字节为 0 |
| 诊断 | `tx_errors`、`rx_errors` | 16 位饱和错误计数，达到 `FFFF` 后保持 |

每个接口仅在 `valid && ready` 的上升沿传输；源端遇到 `ready=0` 必须保持 `valid` 和数据。发送和接收各有独立的单条输出寄存器，输出被阻塞时保持不变；同周期可消费旧输出并接受新输入，连续合法消息可每周期一条。非法输入也遵守输出槽位背压，在被接受的一次握手中消耗并计错，不产生输出。同步高有效 `reset` 清空待发消息和计数，并将两个输入 `ready` 拉低。

| MIDI 状态 | MIDI 字节数 | USB CIN |
|---|---|---|
| `8n`、`9n`、`An`、`Bn`、`En` | 3 | `8`、`9`、`A`、`B`、`E` |
| `Cn`、`Dn` | 2 | `C`、`D` |
| `F1`、`F3` | 2 | `2` |
| `F2` | 3 | `3` |
| `F6` | 1 | `5` |
| `F8`、`FA`、`FB`、`FC`、`FE`、`FF` | 1 | `F` |

支持全部 16 个 MIDI 通道。SysEx（`F0/F7`）、running status、未定义系统状态 `F4/F5/F9/FD` 不在当前框架支持范围。发送端校验状态与长度、有效数据字节的 bit7，并将未使用的字节归零；接收端还校验线缆号必须为 0、CIN 必须匹配，以及未使用的填充字节必须为 0。`C0 05` 的 USB 字节序示例为 `0C C0 05 00`，对应 RTL 字为 `32'h0005C00C`；`90 3C 7F` 为 `09 90 3C 7F`，对应 `32'h7F3C9009`。

## 接入现有 USB3300 例程

参考工程 [`example/USB3300_HS`](../../USB3300_HS/README.md) 已有 USB3300 启动和高速 CDC 链路基础。现有文件保持原样，本框架后续在独立目录内集成：

1. 复用或明确引用 `hs/usb2_hs_boot.v`、`vendor/ultraembedded_usb_hs/ulpi/ulpi_wrapper.v` 与 UTMI SIE 传输层；从 `hs/usb2_hs_top.v` 提取启动复位、PHY 总线控制、时钟连接。保留引用代码原有许可证。
2. 新建复合设备描述符 ROM 与 EP0 请求处理。现有 `hs/usb_desc_rom.v`、`hs/usb_cdc_core.v` 的 ROM 地址和接口请求均为 CDC 布局，不能仅替换设备类值。实现本配置的 IF0/1/2、Jack 及端点关联，并拒绝不适用的 CDC 请求。
3. 扩展端点路由、独立 FIFO、数据 toggle、STALL/清除与总线复位处理。旧 CDC 核固定单对应用字节流，使用 OUT `01` / IN `82`，另有 CDC 通知 IN `83`；它不能直接提供规划中的两对独立 Bulk 端点。要同时支持 MIDI OUT/IN `01/81` 和屏幕 `02/82`，必须修改或替换端点数据通路与调度。
4. MIDI 端点增加 4 字节组包/拆包适配器，将低字节先来的端点数据交给本模块，并处理 USB 包边界、短包、尾部非 4 字节包与总线复位。USB 接收应在 CRC 校验成功后提交完整包，避免将损坏数据作为有效应用消息。
5. 屏幕端点绑定屏幕控制状态机；应用时钟与 USB 时钟不同时，两个方向分别设置跨域 FIFO。帧解析不能假定一条控制帧等于一个 USB Bulk 包。
6. 审核 `constraints/usb2_device.cst` 与 `constraints/usb2_device.sdc` 后再用于新板级顶层；先仿真枚举与端点隔离，再完成 FS/HS 主机枚举、MIDI 收发及屏幕通信验证。

USB3300 例程已有 HS 枚举与 CDC 回环证据；这些证据只属于旧例程，不等于本复合配置已实板验证。原核关于 ACK 丢失后的重传、接收 CRC 回滚、suspend/resume 等限制也需要在复合设备集成时评估与修复。

## 离线验证

从仓库根目录运行：

```sh
iverilog -g2012 -Wall -s tb_usb_midi_codec -o /tmp/gw25k_tb_usb_midi_codec \
  example/MIDI_KEYBOARD/rtl/transport/usb_midi_codec.v \
  example/MIDI_KEYBOARD/sim/tb_usb_midi_codec.v
vvp /tmp/gw25k_tb_usb_midi_codec
python3 -m json.tool example/MIDI_KEYBOARD/config/usb_composite.json > /dev/null
```

仿真覆盖 16 通道的全部 7 类通道消息、全部支持的系统消息、所有不支持状态、CIN/线缆/长度/数据 bit7/填充错误、双向独立背压、同周期进出、一次错误计数、计数饱和与带待发数据复位。它验证消息编解码边界，不验证真实 USB 枚举或 PHY。
