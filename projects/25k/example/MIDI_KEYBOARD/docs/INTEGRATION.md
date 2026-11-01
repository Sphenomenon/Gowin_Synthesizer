# 完整键盘集成说明

应用已由抽象框架接成真实外设和传输链路：50 MHz域内完成QT2160扫描、演奏状态、PCA9685、WS2812、BLE和横屏显示；USB3300的ULPI保持独立60 MHz域，以完整事件/字节FIFO和握手跨域。文档描述当前RTL实现，板级构建、CDC/时序与主机实测的结论以独立报告为准。

## 板级连接

方向从FPGA观察，所有已确认I/O采用3.3V LVCMOS33。详细机器可读记录见 [board.json](../config/board.json)，实际综合使用CST/SDC。

| 功能 | 管脚与用途 |
| --- | --- |
| 50 MHz | E2 |
| USB3300 ULPI | CLKOUT L4输入60 MHz；DATA[0:7]=L2、L1、K1、K2、J4、K4、G2、G1双向；DIR J1、NXT J2输入；STP L3输出 |
| RTL8723DS | 模组TX J8输入，模组RX K9输出，BT_DIS# K8低复位；UART115200/8E1 |
| NV3007 | MOSI H8、SCK K5、DC L5、NCS J5输出；TE H5输入，当前不用TE等待 |
| E1 | A K10、B L8、KEY L10，低有效按键 |
| E2 | A L7、B K7、KEY J7，低有效按键 |
| QT2160键盘 U1 | I²C1：SDA B11、SCL C11，7位地址0x0D |
| QT2160触摸条 U2 | I²C2：SDA B10、SCL C10，7位地址0x0D |
| PCA9685 U3 | I²C3：SDA A10、SCL D10，7位地址0x40 |
| 触摸共享CHANGE12 | A11输入；底板旧网名CS，不是片选输出 |
| WS2812 | D11输出，16颗串联RGB |

三路I²C独立开漏，只驱动低或释放，子板4.7 kΩ上拉。CHANGE低有效并两级同步，读状态消耗通知，同时轮询防漏。旧BLE例程曾占用E1按键复位无线，本工程的E1属于乐器控制，按下只切换触摸条模式。USB3300没有FPGA控制复位GPIO；QT2160/LCD的硬件复位固定供电，需软件初始化及相应等待。

## 输入、演奏和灯光

`midi_touch_frontend`按用户参考ZIP的流程初始化、回读、校准两颗QT2160。U1提交原始16键快照，U2提交触摸/位置，异常时撤销ready并提交释放状态。顶层将U1原始位经`midi_key_layout`重排为A=bit0..P=bit15；用户已确认A–P依次对应原始0基位`5 3 1 7 13 11 9 15 4 2 0 6 12 10 8 14`。MIDI、显示、WS2812和主机按键反馈从此统一采用逻辑位序。映射不改变原始快照时序或多键/释放状态。

当前按键NTHR=12、NDIL=1、BL=4；2026-11-02将按键NDIL由7降至合法最小值1（连续2次采集确认），取消原8次确认配置以降低延迟，实际延迟和误触率待重新板测；滑条NTHR=12、NDIL=3、BL=8；两颗均写入并读回LP=1、BREP=1。键盘读取信号/参考的四笔块读和前后状态，要求前后均按下、参考不小于信号，新按差值≥12，已按保持差值≥10。滑条经`midi_slider_filter`设置3 counts死区：差值3..32的正常移动直接接受；差值>32的跳变需连续两次I²C读样的候选位置在±3内确认。新增采样调度按起始到起始计时，默认20 ms轮询，共享CHANGE为低时也必须等满16 ms下限；避免持续低电平使滑条反复读取同一检测结果。LP=1约16 ms扫描，但芯片没有可核对的扫描epoch，不能保证两次读取一定跨越两个ASIC扫描周期，也不能据此保证拒绝单扫描噪声。失触/故障立即释放并保留末位置。阈值、检测积分与突发长度按设备分别提供编译期参数，USB协议不提供运行时灵敏度设置。生产默认100 kHz I²C、100 ms上电等待、500 ms校准等待不变；实际误触和快速滑动效果仍需本板记录。详细时序与错误恢复见 [TOUCH_DRIVER.md](TOUCH_DRIVER.md)。

芯片ID检查后、配置前新增`RESET_BASELINE`状态读取，先清除旧的上电RESET标记。配置/校准之后的首个采样不再豁免RESET：之后任一采样读到General Status bit7，都报错误`07`、撤销ready、发布释放并重新配置，避免沿用复位时已经丢失的配置。前后状态与信号/参考读出仍不是ASIC保证的原子epoch。

`midi_performance`比较快照产生Note On/Off，默认音符48..63、力度100。触摸无真实力度测量，VEL只控制固定Note On力度1..127。E1循环六项，E2调整当前项：SHIFT±12半音至±48、CH1..16、VEL、STRIP、PROG1..128、LAMP0..255；E1按键随时循环条模式，E2按键panic。条MODE为CC1、EXPR为CC11；BEND松手回8192。模式/通道切换清理原通道CC1=0、CC11=127和弯音回中。

每个活动键保存Note On时的音高和通道，配置改变后Note Off仍匹配原消息。全局panic对所有16通道发CC120/CC123/弯音回中，按住的键先被屏蔽，必须松开后才能重新触发。发送背压期间完整输出槽保持稳定，Note Off优先于新键和普通控制器流量。

PCA9685以MODE1睡眠/配置PRE_SCALE/唤醒/重启初始化，AI写完整64字节PWM帧，16路同一STOP生效，OUTDRV推挽适配普通LED阳极驱动。WS2812独立发16颗GRB、800 kbit/s并留300 µs复位低电平；DIN首颗起链序保持用户确认的`ABCDHGFEIJKLPONM`，颜色跟随逻辑A–P键。PCA的16路灯属于滑条区域，由`midi_slider_led_map`将`strip_value`转成0..16段条形指示，滑条未就绪时全灭，MOD/EXPR松手保持、BEND松手回中。按键输入与主机当前通道Note On/Off仅驱动WS2812按键灯；主机消息不自动回送。LAMP调节滑条灯与按键灯，LCD没有独立背光GPIO。

## USB2与BLE

USB2使用USB-MIDI AudioControl/MIDIStreaming和厂商屏幕三个接口。MIDI使用EP1 OUT/IN，屏幕使用EP2 OUT/IN，彼此独立；实际端点、EP0、描述符、重传和CDC边界见 [USB_PROFILE.md](USB_PROFILE.md)。USB1不参与该数据链路。`FB9A:FB9B`仅为本地诊断ID，未证明已获产品VID分配，发行需获授权ID。

BLE使用标准128位MIDI服务 `03B80E5A-EDE8-4B33-A751-6CE34EC4C700` 和特征 `7772E5DB-3868-4112-A1A9-F2669D106BF3`。`midi_ble_link`执行真实H5/HCI、ROM-v2检查及30,147字节补丁下载，提供Read/WWR/Notify/CCCD。`online`须连接且订阅；没有旧180秒演示超时；断线会发送HCI Advertising Enable重新广播。正常复位从BT_DIS#低电平开始重做全流程；板顶层在BLE failed持续5秒后自动脉冲reset，重新执行模块禁止/H5/HCI/全部补丁初始化。实现及支持边界见 [BLE_IMPLEMENTATION.md](BLE_IMPLEMENTATION.md)。

USB和BLE各有独立FIFO、codec弹性槽与会话复位。普通背压通过ready传播，结束会话才拉低online；该链路旧事件和codec槽会清掉，健康链路继续运行。新会话先向新链路发送所有通道恢复消息，再补发仍按住的活动音符。恢复不会向另一健康链路重复Note On。本地ready/valid或panic结束仅说明事件交给下一层，无法保证断线时旧主机收到了Note Off或已经停止发声。

## 横屏与屏幕控制

`midi_landscape_display`复用NV3007初始化、SPI mode0和RGB565高字节先发，GRAM保持MADCTL00，完整窗口为CASET12..153、RASET0..427。逻辑横屏428×142，默认反向映射 `logical_x=427-native_y`、`logical_y=native_x`（ROTATE_CW=0），右侧竖条显示滑条值。显示按60 Hz节拍发出snapshot，将键、参数、链路、颜色和S2诊断一起锁存；`midi_display_regions`逐字段比较上次snapshot，输出27位掩码：bit0全屏，bit1..26为标题状态、六参数卡、S2行、16键、右栏和诊断页脚。未变区域不重传；静态场景不产生SPI流量。

新`lcd_spi_stream`使用50 MHz ODDRC输出mode0连续字节流；四像素FIFO把四级renderer与RGB565传输重叠，每个区域以CASET/RASET/RAMWR建立独立窗口。RTL引脚仿真测得全部26动态区域35,860像素在11.539220 ms内完成，连续场景快照间隔交替为16.666660/16.666680 ms。首次或主题/背景变化会全屏重画，仿真19.450840 ms超过单节拍；扫描器保留该快照直到整批结束，期间错过的tick计入`overrun_count`，不会混用下一场景。

当前动态界面区域更新满足60 Hz，任意全屏60 fps的RGB565像素数据需要58.345 Mbit/s，超过50 MHz SPI容量；仅像素传输的理论上限约51.42全屏fps。NV3007的PFSET=05/06分别支持16/18位格式，没有RGB444模式。MOSI名义setup/hold各10 ns仅达到手册最低值；FPGA STA与理想引脚仿真不能证明板上SPI波形或TE同步，未宣称LCD实屏全屏60 Hz。MIDI和外设不等待显示；区域坐标、FIFO和验证边界见 [DISPLAY_60HZ.md](DISPLAY_60HZ.md)，最终固件状态见 [BUILD_VALIDATION.md](BUILD_VALIDATION.md) 与 [FLASH_PROGRAMMING.md](FLASH_PROGRAMMING.md)。

实际界面显示标题/链路、六项参数、触摸条和16键，另加U2独立诊断：`S2 R1 T0 RAW128 POS128`及`G02 E00 OV0 N7F`。R为滑条ready，T为滤波后触摸，RAW/POS分别为原始/滤波8位位置；G是实际寄存器2（`G02`的CC位正常），E是滑条错误，OV锁存见过的bit6扫描超限直至FPGA复位，N是成功采样8位循环计数。G不由错误码推导，读取失败保留末状态；这些字段随帧一起快照，便于区分芯片采样与位置滤波问题。`tools/render_preview.py`用Icarus采样真实RTL像素生成 [预览](../reports/midi_keyboard_preview.png)。显示测试从模拟的物理SPI引脚逐位解码，核对完整/局部窗口、旋转、RGB565字节序、多场景更新与快照一致性；仿真不代替LCD外部时序或实屏颜色/方向验收。

厂商协议见 [SCREEN_PROTOCOL.md](SCREEN_PROTOCOL.md)：主机可改通道、逐半音移调、主题和背景；SET_PAGE保留0..15寄存器/响应，目前只有固定乐器总览页。当前协议传设置，不传任意像素、文本或音频。

## 时序约束和跨域检查

`constraints/midi_keyboard.sdc`定义50 MHz和60 MHz输入时钟，以及USB3300 ULPI的输入/输出延迟。USB数据以四个完整事件/字节双时钟FIFO跨域，Gray指针仅进入各自首级同步FF；SDC对这64个首级D施加15 ns最大延迟，并仅豁免其异步hold采样，第二级同步器和后续逻辑仍检查时序。没有使用覆盖整个50/60 MHz时钟域的blanket false path或异步clock group。

编码器6个触点、UART RX、CHANGE与三路I²C的6个观测管脚均只豁免从外部端口到各自首级D的异步路径，14条约束不覆盖同步器级间。LCD TE当前未使用，无需编造同步路径；顶层未使用的USB hs_active也使hs_sync被综合删除，没有对不存在的寄存器施加例外。

Gowin网表层级分隔符仍是`/`，但可能为与端口/网络同名的实例加后缀，例如`usb_33`、`touch_33`、`ble_33`。SDC使用`usb*`/`touch*`/`ble*`前缀兼容此类后缀，而不写死某次综合编号。对当前已生成综合网表的静态递归核对中，Gray两条get_pins各命中64个首级D，其余14条各命中1个首级D；仍须由每次实际PnR确认约束非空、执行成功，并检查setup/hold和未约束路径报告。匹配检查不等于最终时序通过。

## 来源与验收

参考ZIP `QT2160_Keypad16_Slider_Source_20261016.zip` 原件展开于 `vendor/qt2160_reference/`，原文件未改，archive SHA256见SOURCE.json。USB、BLE和LCD派生文件分别保留目录NOTICE及许可；RTL8723DS RAM补丁为第三方厂商固件，不由本工程重新授权。旧例程不因本次整合而修改。

| 验收范围 | 实板仍需记录的证据 |
| --- | --- |
| 板级与电气 | 独立50/60 MHz、复位释放、CDC结构、setup/hold；三路I²C、CHANGE、LED供电/电流和WS2812波形 |
| 输入/灯光 | 16键电极实际顺序、同时触摸/松开、抗扰和持续扫描；条方向/端点/松手回中；PCA/WS键序与亮度 |
| USB主机 | FS/HS枚举、MIDI端口、独立屏幕接口、并发双向传输、复位/拔插和长时间运行 |
| BLE主机 | 标准MIDI端口、订阅、双向音符/CC、断连重广播/重连、持续在线 |
| 演奏交付 | 按住改通道/移调后Note Off、双链路背压、panic/重连恢复、主机无残留音符、真实端到端延迟 |
| LCD | 横屏方向、颜色、重复初始化、更新连贯、刷屏时MIDI不阻塞 |

此前`0x00006712`基线已完成24个测试台回归、整机综合/布局布线、50/60 MHz时序、Flash写入校验与重载，以及USB 480 Mbps枚举，包含完整键序和灵敏度/滤波修改。本轮新增采样节拍、RESET处理、S2诊断和LCD刷新率修改，须以本轮独立记录确认；当前构建及板上固件身份集中见 [BUILD_VALIDATION.md](BUILD_VALIDATION.md) 和 [FLASH_PROGRAMMING.md](FLASH_PROGRAMMING.md)，历史记录不能替代新增修改的通过证据。实际触摸抗扰与滑动响应未因仿真、烧录成功而视为验收。
