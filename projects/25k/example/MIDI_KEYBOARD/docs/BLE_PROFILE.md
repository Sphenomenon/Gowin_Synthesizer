# BLE MIDI 协议与编解码范围

标准BLE MIDI已接入 `rtl/ble_board/midi_ble_link.v`：RTL8723DS UART115200/8E1、H5可靠传输、ROM-v2补丁、HCI初始化和实际ATT/GATT。广播名 `GWK-MIDI`，包含完整128位MIDI服务UUID；新键盘固件的真实无线MIDI主机互通尚未验收。控制器实现及仿真详见 [BLE_IMPLEMENTATION.md](BLE_IMPLEMENTATION.md)。

## GATT配置

| 项目 | 值 |
|---|---|
| MIDI service | `03B80E5A-EDE8-4B33-A751-6CE34EC4C700` |
| MIDI I/O characteristic | `7772E5DB-3868-4112-A1A9-F2669D106BF3` |
| Characteristic properties | Read、Write Without Response、Notify，属性0x16 |
| CCCD | `0x2902`；主机写入 `01 00` 启用通知 |
| ATT MTU | 固定23 |
| 当前特征值长度 | 3、4或5字节；每个值一个完整MIDI事件 |
| 业务online | 连接成功且MIDI CCCD已订阅 |

支持128位服务/特征发现、Read、Write Without Response、Notify与CCCD。Read返回最近由发送接口接受的值，初始为 `80 80 F8`。通知按H5及控制器ACL信用流控；接收在ready前保持值不变。没有旧演示180秒超时，断线后真实发送HCI重广播命令，复位重新执行H5/HCI及完整补丁；完整板顶层对持续5秒的failed自动发复位重试。支持单连接、Legacy Just Works配对和链路加密、完整L2CAP ACL包；bond仅保存在本次上电的RAM内；长写入、分片重组和EATT不在实现范围。

## 编解码接口

时钟域只有 `clk`，`reset` 为高有效同步复位。所有输入必须与 `clk` 同步；跨时钟桥接由集成层负责。每个方向有一个弹性输出槽。输入仅在上升沿 `valid && ready` 时被接收；输出的 `valid`、数据、长度和时间戳在下游停顿期间保持稳定，允许同周期取走旧值并接收新值。发送端必须保持输入直至握手完成。

MIDI 消息以 `message[23:0] = {status, data1, data2}` 表示，长度是原始 MIDI 字节数 1/2/3；短消息的未使用输入数据字节被忽略，输出一律补零。时间戳为 13 位毫秒计数，取值 `0..8191`，之后自然回到 0；编解码层不推算时间或扩展溢出计数。发送时间戳在消息握手时捕获，随后改变 `timestamp_ms` 不改变等待发送的值。

特征值数据 `value_*_data[39:0]` 按**低字节先传输**：

| 字节位置 | 内容 |
|---|---|
| 0 / bits 7:0 | `0x80 | timestamp[12:7]`；bit 7 = 1，bit 6 = 0 |
| 1 / bits 15:8 | `0x80 | timestamp[6:0]` |
| 2 / bits 23:16 | MIDI status |
| 3 / bits 31:24 | data1，仅长度 4/5 时有效 |
| 4 / bits 39:32 | data2，仅长度 5 时有效 |

例如时间戳 8191 的 Note On `90 3C 7F` 编为 `BF FF 90 3C 7F`（总线十六进制为 `40'h7F3C90FFBF`）。下一个时间戳 0 的同一事件编为 `80 80 90 3C 7F`。接收时忽略 `value_rx_length` 之外的总线填充字节；输出发送值始终将未使用字节置零。

支持所有通道语音状态 `8n..En`：`Cn` 和 `Dn` 长度为 2，其余长度为 3。支持系统消息 `F1/F3`（2 字节）、`F2`（3 字节），以及 `F6/F8/FA/FB/FC/FE/FF`（1 字节）。有效数据字节的 bit 7 必须为 0。`F0/F7` SysEx、保留状态 `F4/F5/F9/FD`、running status、实时字节插入其他消息、多事件值和扩展/分片值均不在本框架子集内，将被拒绝。接收需要精确的 `2 + MIDI 长度`；额外的时间戳或消息字节不能当成同一事件接受。

`tx_errors`、`rx_errors` 分别统计发送侧和接收侧已握手的无效输入，16 位饱和至 `FFFF`，复位清零。无效输入被消费但不产生输出；在背压期间未握手的输入不会增加计数。持续拉高 `valid` 且每周期都握手表示每周期提交一个输入事件，每次提交分别计数。复位清空两个方向待发事件及数据、长度和时间戳。

## 实现与验证边界

同仓库旧 `example/RTL8723DS_BLE` 的FFF0/FFF1测试例程保持不变；本工程派生H5/UART/HCI并新增标准MIDI GATT，保留NOTICE与固件来源信息。原BTST定时测试值和180秒退出不进入MIDI链路。

`tb_ble_board_system`从物理UART引脚建立独立控制器模型，逐字节校验原厂bin重建的30,147字节补丁/120片段、初始化参数、标准UUID发现、CCCD、3..5字节收发、背压、断线重广播、持续运行与复位。错误ROM另有下载前拒绝测试。`tb_ble_midi_codec`验证准确字节序、支持消息、时间戳回绕、非法值、背压、计数和复位。

上述证据属于RTL仿真。真正的BLE MIDI端口发现、不同系统兼容性、长期无线收发、实际延迟及无残留音符仍需本次整机硬件测试；旧例程的无线实测不能替代新服务验收。
