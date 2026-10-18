# USB3300 3-pin FS serial 适配核对

本记录仅核对规范与当前 FS 核行为，未修改 RTL，也未构建或下载。资料边界为本机官方 USB3300 数据手册 **Microchip DS00001783C**（缓存 `/private/tmp/usb3300_official.pdf` / `.txt`）、已安装 Gowin USB IP 说明和项目内 WangXuan95 FS 核。未找到本机 ULPI 1.1 全文，未开展网络 clone。

## 官方资料明确的内容

DS00001783C §6.1.10、Table 6-7，印刷第32页：

| 串行信号 | FPGA连接 | 方向（相对PHY） | 官方定义 |
| --- | --- | --- | --- |
| tx_enable | DATA[0] | 输入 | 高有效发送使能 |
| data | DATA[1] | 双向 | tx_enable=1时发送差分数据，=0时输出接收差分数据 |
| se0 | DATA[2] | 双向 | tx_enable=1时发送SE0，=0时输出接收SE0 |
| interrupt | DATA[3] | 输出 | 未屏蔽中断，高有效 |

进入模式先写 Interface Control（地址07h；08h为set，09h为clear）的3-pin FsLsSerialMode bit1。§6.1.4.6、§6.1.10要求需要保留60MHz时钟时，在进入串行模式前设置 bit3 ClockSuspendM；稳妥顺序是先 IF=08h，再 IF=0Ah。若直接同时写0Ah，bit3和bit1会一同生效，但资料没有单独证明这种顺序等同“先设置bit3”。

§6.1.10原文：PHY会“assert DIR and shut off the clock after at least five clock cycles. Then the data bus goes to the format of the serial mode selected”。设置ClockSuspendM后时钟保留。应先完成ULPI寄存器写事务、让出正常ULPI数据总线，再等待模式进入；常规ULPI DIR高之后仍需留转换守护期。该段没有给出固定进入最大延迟，单纯16拍守护属于实现选择，而非手册明确保证的上限。

退出串行模式由Link置STP=1发起；PHY返回后DIR拉低，再由Link拉低STP恢复同步ULPI。因此**串行运行期间STP应保持0**，不能继续运行会产生STP脉冲的ULPI事务机。DIR/NXT在串行模式下不能继续充当三线数据口的常规ULPI仲裁条件。

Function Control §6.1.4.5，印刷第21页：XcvrSelect[1:0]=01选择FS，SuspendM bit6=1不挂起。FC=45h包含FS、TermSelect=1、正常OpMode和SuspendM=1。三线口送的是差分线态和SE0，FS核继续自行提供NRZI、bit stuffing、SYNC和EOP；不能再把这些数据作为ULPI字节TX CMD发送。

## D1极性的证据边界

官方Table 6-7将D1称为“differential data”，**没有给出D1=1/0对应DP/DM的真值表**。本机Gowin USB Device Controller、USB1.1/2.0 SoftPHY说明只涉及UTMI接口，没有补充USB3300三线极性。因此不能把“D1=1一定对应DP=1/DM=0”称为本次查得的官方明确结论。

按通常的正向差分数据约定，合理的适配假设是：非SE0时D1=DP，D1=1对应FS J（DP=1/DM=0），D1=0对应FS K。建议在PHY接入、FS上拉已使能且总线空闲时，核对实际D1=1、D2=0；若没有这项读回，本项仍是待实板确认的极性假设。

采用上述约定的接收映射为：

```verilog
rx_dp = !se0 && data;
rx_dm = !se0 && !data;
```

三线格式只携带差分数据与SE0，不能恢复独立的DP/DM SE1状态；原FS核的SE1检测不能据此视作电气SE1检测仍然完整。

## Pad mux建议与EOP交接

正常ULPI与串行模式使用独立的pad所有权选择。正常ULPI继续遵守DIR和turnaround；寄存器写完成后让出总线，转换守护期间不要同时启用串行驱动。进入串行后建议：

- DATA[0]始终由FPGA驱动：空闲/接收为0，发送为FS核的tx_oe。
- DATA[1]、DATA[2]仅在tx_oe=1时由FPGA驱动；分别为tx_dp与`!(tx_dp | tx_dm)`。接收时两者均高Z，让PHY输出接收数据。
- DATA[3:7]由FPGA保持高Z；STP=0。不能再用`!DIR`门控串行发送，PHY在串行模式中的DIR状态不表示这两根线的逐包方向。
- 输出使能与DATA[0]使用同一个已注册发送控制，维持同拍切换；不要通过任意增加一拍延迟，使DATA[0]与D1/D2 pad OE分离。

原核 `prj/vendor/fpga_usb_device/RTL/usbfs_core/usbfs_bitlevel.v` 的接收输入持续进入5拍采样链（约第96–102行），但TX期间FSM不执行RX包解析。TX末尾的`S_TXEOP1`继续SE0，`S_TXEOP2`先保持usb_oe=1并发送J，然后下一bit边界的`S_TXDONE`才usb_oe=0、回`S_JWAIT`（约第255–279行）。因此它已经在收回OE前发送完整J bit，并非在SE0末尾直接放开输出。

为保留原来直接D+/D− inout回读的语义，可在tx_oe=1时向核的RX输入回送本地tx_dp/tx_dm；收回OE后立即改读PHY的D1/D2解码值。这样TX时的EOP/J序列与原核一致。PHY串行D1/D2切换的模拟传播延迟、pad高Z时序并未由上述表格给出，不能据此宣称OE交接边沿的回读完全无延迟；原核已有J等待与输入采样滤波，应在仿真/实板中核对交接后没有虚假SOP或丢失主机响应。

## 当前GAO区分

PHY寄存器probe镜像为GAO ID **D2A6**；FS serial CDC镜像为独立 **D2A7**。capture与decoder均用`--image probe|serial`选择，默认probe。serial页1的FC/IF/OTG值是成功写入的初始化影子值，不能当作回读证据；serial页2的received_seen不能解成probe的scratch_ok。CSV本身不携带GAO ID，解码时应与采集JSON中的image/ID对应。

serial页1现为`{FC_written8, IF_written8, OTG_written8, line_flags8}`；真正的stage8继续位于页2最高byte。decoder同时输出`line_flags_byte`和以下`line_flags`布尔字段：

| 位 | 字段 | 含义 |
| --- | --- | --- |
| 7 | attach_request | FS核请求接入 |
| 6 | init_done | 三线初始化完成 |
| 5 | usb_oe | FS核当前发送输出使能 |
| 4 / 3 | dp_rx / dn_rx | 送入FS核的解码/本地回送线态 |
| 2 / 1 / 0 | ulpi_data2 / ulpi_data1 / ulpi_data0 | 三线pad实际D2/D1/D0电平 |

按本记录的正向差分假设，attach_request=1、init_done=1且空闲接收FS J时，预期usb_oe=0、dp_rx/dn_rx=10、D2/D1/D0=010，即`line_flags_byte=0xD2`。需结合总线确实处于空闲J确认，不能把任意收到的K态当成极性错误。TX期间dp_rx/dn_rx可能来自本地TX回送，应配合usb_oe与原始pad位判断。此byte来自跨域一致快照，单次采集可能只展示此前状态，不保证恰好捕获收发转换边沿；本次修改不改变probe页1的last_read定义。
