# 屏幕与设备控制协议 v1

这是 `screen_control_endpoint` 的字节流协议，已接入 **USB 2.0 复合设备的厂商自定义 bulk 接口2**，使用OUT `0x02` / IN `0x82`。MIDI使用独立MIDIStreaming接口和端点；屏幕控制字节不能发送到MIDI端点。本工程已实现USB3300设备适配和NV3007横屏渲染，真实主机收发仍需整机验收。该接口不采用CDC，也没有串口文本命令。

新增外部像素输入采用独立的 [PL local-v1](PANEL_DISPLAY_PROTOCOL.md)。`screen_stream_router`在同一厂商接口按魔数路由，旧MK帧格式及命令保持兼容；只有有效PL像素触发输入页。以下内容仅描述MK设置协议。

## 帧格式

所有请求与响应均为固定 16 字节，所有多字节整数均为小端。

| 偏移 | 字节数 | 字段 | 定义 |
| --- | --- | --- | --- |
| 0 | 2 | magic | ASCII `MK`，即 `4d 4b` |
| 2 | 1 | version | `01` |
| 3 | 1 | opcode | 请求 bit 7 必须为 0；响应为请求值 OR `80` |
| 4 | 2 | sequence | 主机序号，响应原样回送，不进行去重 |
| 6 | 4 | arg0 | 请求参数；响应状态码 |
| 10 | 4 | arg1 | 请求必须为 0；响应结果 |
| 14 | 2 | crc16 | 对字节 0..13 的 CRC，低字节在前 |

CRC 使用 CRC-16/CCITT-FALSE：多项式 `0x1021`、初值 `0xffff`、不反射、最终不异或。标准检查串 ASCII `123456789` 的 CRC 为 `0x29b1`。

## 请求

每条请求的 `arg1` 均为保留字段，必须为 0。有效写操作在整个帧接收并完成校验后一次性生效。

| opcode | 名称 | arg0 | 成功响应 arg1 |
| --- | --- | --- | --- |
| `01` | GET_STATUS | 必须为 0 | 核心提供的 32 位 `status_flags` 快照 |
| `10` | SET_CHANNEL | 0..15，MIDI 线上通道值，对应用户界面通道 1..16 | 已接受的 arg0 |
| `11` | SET_TRANSPOSE | 有符号 int32，-48..+48 半音 | 已接受的 int32 原始编码 |
| `20` | SET_PAGE | 0..15 | 已接受的 arg0 |
| `21` | SET_THEME | 0..65535，RGB565 | 已接受的 arg0 |
| `22` | CLEAR | 0..65535，RGB565 | 已接受的 arg0 |

RGB565 格式为 R[15:11]、G[10:5]、B[4:0]。颜色参数的高 16 位必须为 0。移调的负值必须进行 32 位符号扩展，例如 -12 编码为 `f4 ff ff ff`。`status_flags` 的位定义由上层核心约定，本模块透传该值。

完整板级应用的GET_STATUS位定义如下；独立旧`midi_keyboard_core`仍使用其自身诊断约定，不能把两者混用：

| bit | 板级应用状态 |
| --- | --- |
| 0 / 1 | USB / BLE业务online |
| 2 / 3 | USB / BLE路由FIFO满 |
| 4 | 至少一个活动键 |
| 5 | panic或链路恢复忙 |
| 6 | 曾有无在线目标的事件 |
| 7 | 屏幕协议错误非零 |
| 8 / 9 | USB / BLE接收编解码错误非零 |
| 10 / 11 | USB / BLE发送编解码错误非零 |
| 31:12 | 保留，0 |

`SET_PAGE`、`SET_THEME`、`CLEAR`每次成功执行产生一个时钟周期的`screen_update`脉冲，包括参数与当前值相同的情况。当前横屏渲染器在每帧snapshot时锁存主题色和背景色；CLEAR更改背景颜色，参数卡/键/文字仍按界面绘制。SET_PAGE保留0..15寄存器和成功响应，当前仅有固定乐器总览布局，没有按page切换不同页面。MK不传任意像素或文本；PL协议单独传RGB565 tile。

复位默认值：MIDI 通道 0、移调 0、页面 0、主题色 `0x07ff`、清屏色 `0x0000`、错误计数 0。

## 响应与错误

响应的 version 始终为 1，opcode 为收到的请求 opcode OR `0x80`，sequence 原样回送。

| 响应 arg0 | 含义 | 响应 arg1 |
| --- | --- | --- |
| 0 | 成功 | 上表定义的结果 |
| 1 | 未知 opcode，或请求 opcode 的 bit 7 为 1 | 0 |
| 2 | 参数越界或保留字段非 0 | 0 |
| 3 | CRC 错误 | 0 |
| 4 | 版本不支持 | 0 |

检查顺序为 CRC → version → opcode → 参数；一帧含有多种错误时只返回优先级最高的错误，错误计数只加 1。任何错误都不会修改 MIDI/屏幕设置，也不会产生 `screen_update`。`protocol_errors` 是可供核心读取的 16 位饱和计数器，达到 `65535` 后保持，复位清零；它不是 `GET_STATUS` 隐式返回值。

## 流控与恢复

- 输入在 `rx_valid && rx_ready` 的时钟上升沿接收一个字节；输出同理。所有端口属于同一时钟域，`reset` 为高有效同步复位。
- 每次只处理一个请求。接收完整帧后，校验与响应期间 `rx_ready=0`，直到响应的第 16 个字节被接受。USB OUT 适配器必须通过 FIFO 或 NAK 遵守这一背压。
- 响应 CRC 按每时钟一个字节计算，共 14 个时钟，避免长的组合 CRC 路径；这段准备时间内同样保持输入背压。
- 输出被阻塞时，`tx_valid` 与当前 `tx_data` 保持，设置不会重复执行，`screen_update` 不会重复产生。响应完成前主机应保持下一请求或等待。
- 空闲时丢弃 magic 前的字节；连续的 `M` 可作为新 magic 的起点。仅有前导垃圾不会增加错误计数。识别 `MK` 后按固定长度接收，不在帧内部扫描 magic；完整错误帧回复错误后重新搜索。
- 独立MK端点本身没有接收超时；板级新增`screen_stream_router`对残帧和缺失回复提供100 ms超时，并脉冲复位对应解析器。主机阻塞有效回复不触发超时。USB总线复位/取消配置映射为`control_reset`，清掉半帧与待响应字节；新会话重新发送完整请求。
- 不依赖 USB 数据包边界：一个控制帧可以跨多个 USB 包，也可以与其他帧位于同一个 OUT 包中；适配器必须按流控依次传送字节。主机应按 16 字节积累完整响应后再解码。
- sequence 仅用于匹配响应；相同 sequence 的请求会再次执行。USB会话断开及50/60 MHz跨域由当前板级USB适配器处理；主机超时和应用层重试仍由主机负责，重发同序号不会去重。

## 主机工具

工具仅使用 Python 标准库，输出或解析十六进制帧，**不执行 USB 传输**。在 `example/MIDI_KEYBOARD` 下使用：

```sh
python3 tools/screen_control.py status --seq 1
python3 tools/screen_control.py channel 0 --seq 2
python3 tools/screen_control.py transpose -12 --seq 3
python3 tools/screen_control.py page 2 --seq 4
python3 tools/screen_control.py theme 0xf81f --seq 5
python3 tools/screen_control.py clear 0x0000 --seq 6
python3 tools/screen_control.py decode '4d 4b 01 01 01 00 00 00 00 00 00 00 00 00 2c c5'
```

示例：

```text
GET_STATUS seq=1
4d 4b 01 01 01 00 00 00 00 00 00 00 00 00 2c c5

SET_TRANSPOSE -12 seq=2
4d 4b 01 11 02 00 f4 ff ff ff 00 00 00 00 5f c8
```

Python API：`encode_request(opcode, sequence=0, arg0=0, arg1=0)`、`decode_frame(bytes)`、`encode_response(opcode, sequence, status=0, result=0)`。请求编码器的移调参数采用 Python 有符号整数；其余字段采用无符号整数。解码结果保留原始 uint32，`Frame.signed_arg0`/`signed_arg1` 提供有符号解释。编码与解码均检查类型、字段范围及协议约束，解码还检查长度、magic、版本与 CRC；含非法请求字段的原始帧只应在故障测试中手工构造。

验证：

```sh
python3 -m unittest discover -s sim -p test_screen_control.py -v
iverilog -g2012 -s tb_screen_control_endpoint -o /tmp/midi_screen_control_sim \
  rtl/control/screen_control_endpoint.v sim/tb_screen_control_endpoint.v
vvp /tmp/midi_screen_control_sim
```

RTL 仿真覆盖有效命令、参数边界、保留字段、未知/响应 opcode、CRC/版本错误、错误优先级、饱和计数、分段接收、前导垃圾、响应背压、复位中止半帧及待发送响应。主机测试使用独立的 `binascii.crc_hqx` 校验编码结果，并使用标准 CRC 检查串。
