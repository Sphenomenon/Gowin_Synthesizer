# 外部输入画面与本地设置

2026-10-19面板接入更新：USB端点、PL包和下述消息语义保持；默认顶层`HOST_PANEL_CONTROLS=1`使用已确认CC7／Program／Pitch Bend及CC89／CC88短按，不分配长按，也不在远端页屏蔽旋转。下述E1长按设置、MOD/EXPR切换及E2 PANIC页面操作仅描述保留的`HOST_PANEL_CONTROLS=0`独立兼容分支；端点仍支持既有manual状态和设置toggle输入，但默认顶层不将其绑定到长按。详见[设备控件落地报告](../../../../138k/push2_workstation/usb_a/reports/GW25K_CONTROLS_20261019.md)。

本实现参考用户提供的 `gowin_接口.zip`。原件共11个规划文件，原始字节和校验清单保存在 [vendor/gowin_panel_interface](../vendor/gowin_panel_interface/)。ZIP SHA256 为 `bb6d95165fa931c3c964f6264bfd10ad2e7c36f66e65b3ab17350867c6564bad`。附件没有可直接调用的RTL，也没有HighSpeed物理信号、时钟、引脚和消息编号；以下编号、载荷和请求响应规则是本板明确补充的 **PL local-v1**，主机需按本文适配。

按用户确认，MIDI与屏幕数据均通过USB2完成。屏幕承载为厂商接口2，OUT `0x02` / IN `0x82`，与原有`MK`命令共用字节流；MIDI使用自己的端点。`panel_display_endpoint`本身不依赖USB。本轮没有分配额外HighSpeed引脚。

## 页面行为

- 上电或没有有效显示输入时，显示现有乐器总览/设置页。
- `HELLO`、`HEALTH`、USB枚举、MIDI输入和旧`MK SET_PAGE`都不会切换画面。首个完整有效的`DISPLAY_TILE`进入输入页；先清黑，再写像素。
- 有效同会话请求维持250 ms在线时限，静态画面需每100 ms发送`HEALTH`。超时、USB总线复位或取消配置后恢复本地界面，强制完整重绘，避免残留远端像素。
- E1长按1秒进入设置，并锁定本地页；主机继续发像素也不会把它切走。再次长按解除锁定，仍需新的像素数据才进入输入页。没有远端画面时长按不预先锁住未来输入。
- E1短按在释放时循环MOD/EXPR/BEND；长按不附带短按。E1/E2旋转只在本地页调参数。E2按下在两个页面都立即panic。编码器反向、半速和原消抖保持。
- 无整帧缓存。进入/重新进入输入页后主机须重发完整画面；局部更新前的清黑不能恢复旧图。主机通过响应中的`redraw_required`获知重画请求。

## 16字节包头

多字节整数均小端；`payload_len`不包含包头。包头后立即跟载荷，最大512字节。USB CRC负责物理传输完整性，PL不另加CRC；替换物理链路时应保证完整性校验。

| 偏移 | 长度 | 含义 |
| --- | --- | --- |
| 0 | 2 | `50 4c`，ASCII `PL` |
| 2 | 1 | version = 1 |
| 3 | 1 | type，见下表 |
| 4 | 4 | session，非0；由主机选择 |
| 8 | 2 | seq，本逻辑通道请求序号 |
| 10 | 2 | ack；当前主机请求填0，响应等于已处理请求seq |
| 12 | 2 | payload_len，0..512 |
| 14 | 1 | bit0可靠标志必须1，bit2:1为通道（0控制、1显示），其他位0 |
| 15 | 1 | credit，反方向对应通道可再接收的业务包数 |

本板采用主机逐包请求、设备逐包响应；设备不主动插入响应。响应seq与ack均回显请求seq，session与逻辑通道对应原请求，响应本身不消耗另一套序号。控制和显示各自递增16位seq，允许回绕；`HELLO`建立控制序号起点，显示首包seq=0。主机始终先收完整响应，再发下一包。同通道重发最近一个已接受seq会得到响应而不会再次执行；新内容不能复用已接受seq。`BUSY`或错误不消耗序号，须按状态恢复。新session必须先`HELLO`。

`screen_stream_router`按`MK`固定长度或`PL`长度路由，像素内的魔数不会被当作新帧。请求和响应可跨USB包；不依赖USB包边界。输入残帧和缺失端点回复默认100 ms中止，PL接收器自身也有残帧时限。主机阻塞已提供的回复字节不会触发路由超时。超长包不予执行并复位PL解析状态；应重新握手，不能把恶意/损坏字节流当作可无损续传的会话。

## 消息

| 请求 | 通道 | 请求载荷 | 正常响应 |
| --- | --- | --- | --- |
| `01 HELLO` | 0 | 空；非0新session | `81 CAPS`，12字节 |
| `02 HEALTH` | 0 | 空 | `82 STATUS`，8字节 |
| `20 DISPLAY_TILE` | 1 | 16字节描述+像素 | `a0 ACK`，8字节 |
| `21 FRAME_END` | 1 | page u16、reserved u16=0、frame u32 | `a1 DRAWN`，8字节；等待物理完成 |

`CAPS`为：width u16@0=428、height u16@2=142、pixel_format u8@4=1（RGB565小端）、reserved u8@5=0、max_pixels u16@6=248、max_payload u16@8=512、heartbeat_ms u16@10=250。

`DISPLAY_TILE`描述：page u16@0、reserved u16@2=0、frame u32@4、x u16@8、y u16@10、width u16@12、height u16@14。像素从@16开始，按逻辑坐标逐行排列，RGB565低字节先传（R[15:11]、G[10:5]、B[4:0]）。宽高必须大于0，x+width≤428、y+height≤142，`payload_len=16+2×width×height`，最多248像素。推荐32×4块；右边/底边不足时缩小。LCD适配器按反向横屏坐标重排，并发送RGB565高字节。

除`CAPS`外响应载荷8字节：status u8@0、state_flags u8@1、page u16@2、frame u32@4。`STATUS`的page/frame为0。state_flags bit0=`manual_settings`、bit1=`remote_enable`、bit2=`redraw_required`，其他位0。`FRAME_END`完成一次完整主机重画后才解除重画提示；提示不验证主机是否真的覆盖了所有像素。

| status | 含义 |
| --- | --- |
| 0 | OK |
| 1 | SUPPRESSED：本地设置覆盖、会话失效或画面需重新输入；没有绘制 |
| 2 | BUSY：tile缓冲仍被显示器占用；稍后重发同seq |
| 3 | BAD_VERSION |
| 4 | BAD_SESSION |
| 5 | BAD_SEQUENCE |
| 6 | BAD_FORMAT：通道、保留字段、长度或载荷不合法 |
| 7 | BOUNDS：矩形越界或FRAME_END不匹配 |
| 8 | UNKNOWN：未知type |

错误响应type=`ff ERROR`。被设置页抑制的显示包返回`a0 ACK`、status=1；不能当作`DRAWN`。正常tile ACK只说明像素已进入不可变缓冲，尚不代表屏幕写完；主机可发心跳，下一tile若忙则返回BUSY。LCD尚在初始化、清黑或等待接收tile时，`FRAME_END`也立即返回ACK/BUSY，不消耗seq；有效BUSY请求维持心跳，主机稍后以同一seq重试。最后一个匹配tile结束并等到SPI物理CS释放后，`FRAME_END`才成功返回`DRAWN`。这证明SPI写入完成，不能证明LCD扫描或人眼已看到画面。

## 实现和测试

接收缓存与正在绘制的tile RAM分离。新session、链路软复位、超时和手势都不能覆盖已被LCD接受的像素；旧窗口安全收尾后才释放RAM。单个`lcd_spi_stream`继续独占LCD引脚，页面切换只发生在完整窗口边界。MIDI、触摸、灯光与蓝牙不等待显示应答。

本地界面保持60 Hz快照与变化区域传输。50 MHz SPI仿真：26个动态区域11.539220 ms，全屏19.450840 ms；外部任意整帧同样受链路/SPI吞吐限制，不承诺60 fps全屏输入。

主机工具在工程目录执行：

```sh
python3 tools/panel_display.py --help
python3 tools/panel_display.py demo --seconds 10
python3 tools/panel_display.py image input.ppm --seconds 30
```

工具使用标准库与本机libusb，输入图像为428×142的P6 PPM。演示停止后250 ms自动回到本地页；运行时可长按E1检验设置覆盖及恢复重画。仅占用USB接口2，音乐软件可继续使用MIDI接口。功能和硬件验收记录见 [BUILD_VALIDATION.md](BUILD_VALIDATION.md)。
