# 25K USB2 原生 RXCMD／SE0／NXT 诊断

日期：2026-10-29，UTC+08:00。接续 [10月28日诊断](USB2_LINK_DIAGNOSTIC_20261028.md)。用户要求先定位USB2原生接收链，暂不切换USB1 FS。25K的JTAG和USB2连接电脑，138K不参与本次采样。

最新状态：03:21在USB1供电、USB2接138K USB-A的接法下，临时加载DC到25K SRAM并完成四窗原生统计；原生及UTMI均观察到约3 ms的SE0，状态历史进入HS，但PHY／UTMI接收字节始终为0、地址0。诊断后已恢复完整 `C12528DA` 到SRAM并读回身份；25K DA Flash及138K E5均未改写，下一步查138K握手结束后的端口状态与发包。此前00:50的电脑端HS／PL／MIDI成功与01:05的DA固化记录保留，见 [DA固化记录](FLASH_DA_20261029.md)，不作为本次板间枚举成功证据。

## 配置与来源

- SRAM候选 `C12528DC`，显式 `--usb2-probe`，不是完整键盘。继续使用原USB3300启动、ULPI wrapper、双速设备核、描述符、端点和FIFO，只增加观察统计；不改USB1、vendor源码、锁定网表或历史基线。
- GAO改为D2BD／256 bit／50 MHz／128 samples。八流每流32 bit，前两流保留当前状态与历史，后六流是独立mailbox的统计；流内一致，不声称跨流原子采样。
- 原生RXCMD仅在连续DIR=1且NXT=0时接受；PHY数据仅在连续DIR=1且NXT=1时计数；link确认仅在连续DIR=0且NXT=1时计数。方向切换首拍及boot访问排除。
- 最长SE0分别在原生RXCMD保持线态与wrapper UTMI线态上计时，只在WAIT_RST／FULLSPEED且先观察到idle J后arm，排除启动未知状态、250 ms延迟和HS idle。计数24 bit饱和，段数8 bit饱和；不随USB总线reset清除。字段定义及复现命令见 [USB2_DEBUG](../docs/USB2_DEBUG.md)。

## 构建与离线验证

构建00:00:34.372569至00:01:03.210982，共28.84秒。完整回归43个RTL bench、50个Python用例通过；默认／完整观察／USB-only顶层展开通过，输入未漂移，BLE ROM拒绝与原引用完整性检查保留。

新增 `tb_usb_board_bus_statistics` 验证：先见J才arm、180000周期SE0在DIR归零后仍持续计时、chirp／HS阶段排除、原生与UTMI不一致可见、方向切换排除、PHY／UTMI／link三路计数独立、计数饱和及全局reset。解码用例验证256 bit配置、周期换算、分流字段和不完整统计流拒绝。

保持50 MHz、60.002 MHz与GAO TCK20 MHz原约束：setup／hold违例端点0，最差setup +0.222 ns、hold +0.195 ns、recovery +5.415 ns、removal +1.037 ns；Fmax分别169.344／60.811／133.082 MHz。新增SDC只覆盖观察器Gray、mailbox首级／受保护数据及原attach首级，不放松业务时钟。

首轮构建因Gowin旧库与系统fontconfig链接失败，未生成或下载位流；显式预载系统libstdc++／zlib／freetype后重建。保留失败目录，不将失败记录改为通过。

```text
~/.cache/fpga-usb2-hdmi/25k-midi-probe-c12528dc-20261029_000034/
  build.json
  source_snapshot/
  impl/pnr/ao_0.fs
  deployment.json
  capture_20261029_000634/
~/.cache/fpga-usb2-hdmi/25k-midi-probe-checks-dc-20261029_000059/validation.json
```

位流SHA256：`ba1c3e4a17e8b0167082a303e0172a2f17e2f09301e4ea5d85fd2d64fdb14930`。构建清单绑定实际源码快照、配置、输入哈希和实现产物。部署清单绑定该构建、离线回归及DB／完整DA回退身份。

## SRAM下载及初始采样

00:06:29至00:06:34，WINUSB location786，operation0下载前读回DB，operation4下载并校验DC，operation0独立读回 `ID=0x0001281B / UserCode=0xC12528DC / Status=0x70022020`。随后匹配DC manifest／D2BD采样，采样前后仍为DC。25K Flash C1251032及138K Flash C11028E5未写。

初始采样 `capture_20261029_000634/`：

| 观察量 | 数值 |
| --- | --- |
| boot | stage0x12，done1，error0 |
| 原生时钟 | 1 ms分频计数235，约60 MHz |
| 当前状态／地址／online | WAIT_RST(1)／0／0 |
| 原生RXCMD与UTMI线态 | 均为J(1)，有效且两路SE0计时均已arm |
| 原生／UTMI最长SE0 | 均0周期、0段 |
| 协议释放后有效RXCMD | 1周期，末值0x4d |
| 原生PHY NXT数据／UTMI有效字节 | 0／0 |
| link方向NXT确认 | 2周期；不是USB数据包ACK数量 |
| MIDI发送／接收受理 | 0／0 |

该窗口是加载后的初始对照，没有新的电脑枚举尝试；不能用它替代10月28日的重插测量。已请求只拔插USB2数据线电脑端，保持JTAG和板卡供电，并监听新内核接入事件。后续应在同一次主机尝试结束后读取粘滞统计，避免把加载前日志与加载后历史拼成一次测量。

00:08:21至00:08:38的几次新接入均明确识别为 `0403:6010 / Dual RS232-HS`，在 `usb 3-1.1` 与 `usb 3-1.2` 间移动，是FTDI下载器；没有USB2数据设备的新枚举过程。通用接入监听虽触发，不能把它当作25K USB2主机尝试，分类另存 `host_attempt_classification_0009.json`，保留原监听日志。00:09再次按location786只读采样，前后仍为DC，原生／UTMI最长SE0仍0，RXCMD仍1，PHY／UTMI有效字节仍0，link确认仍2；捕获与同期内核日志在 `capture_20261029_000932/`。此时仍需真正的USB2数据口重插，不据此判定硬件损坏，也未转用USB1。

## 判读与回退

### 00:13重插确认后的新状态：运行身份丢失及原生停钟

用户再次确认接入后，00:13:57首次采样在身份检查处停止：GW5A-25A身份正确，但UserCode为Flash旧固件 `C1251032`，不再是DC。失败记录在 `capture_20261029_001357/`，没有把旧固件当作DC读取。该身份变化说明SRAM候选在此期间已被重载或丢失，符合拔线引发板卡掉电／重启的情形，但没有直接电源测量确认原因。

无需重新综合。重新校验DC位流、完整回归和当前源码哈希后，00:15:39至00:15:44再次operation4下载并校验DC，operation0独立确认恢复 `0x0001281B / C12528DC / 0x70022020`；证据为 `sram_recovery_20261029_001539/`。25K与138K Flash均未写。

恢复后的 `capture_20261029_001544/` 和 `capture_20261029_001750/` 前后身份均为DC，但独立50 MHz观察流在运行，原生计数连续为0、clock_alive=false、源快照为初始0，没有boot完成信息。与00:09的约60 MHz／初始化完成状态不同。此时RXCMD、SE0等0值是源统计器没有采样的结果，不能解释为USB线上确实没有复位，也不能继续套用上表的已运行分支。

00:22另用此前已验证的D3位流（SHA256 `b298ba5ac87d5009fbf9166c8a4b520e461e3a54ed75920a6d7afbfc411372b1`）执行独立50 MHz STP切换1.5秒，随后恢复同一DC位流；全程仅operation4及operation0，身份顺序DC→D3→DC，记录在 `stp_wake_test_20261029_002203/experiment.json`。恢复后 `capture_20261029_002213/` 仍没有原生时钟计数。本次未在D3阶段采样，不能据此排除D3阶段曾短暂起钟再停止。

截至00:22，电脑内核00:12之后没有新的USB接入记录。当前先确认25K的实际供电路径及USB3300供电／CLKOUT状态，暂不继续修改MIDI／PL、宣称某颗芯片损坏或切换USB1；当前SRAM已恢复DC。

### 00:28至00:35：USB1供电接法下，USB2 HS枚举及MIDI回环通过

用户确认USB1供电已接好。00:28:19电脑内核在 `usb 3-6` 记录新的High-Speed设备，VID/PID `fb9a:fb9b`，产品 `GW25K MIDI Screen`；sysfs实读480 Mbps、configuration1、三个接口，ALSA注册 `hw:1,0,0` MIDI端口。此阶段未重新综合或下载，JTAG读回仍为 `ID=0x0001281B / UserCode=C12528DC / Status=0x70022020`。本次接法下停钟未复现，但未通过对照试验将先前停钟的原因唯一归为供电。

00:33:15采样 `capture_20261029_003315/`，00:34:54执行128条Note On／Off回环，随后再次读取匹配DC／D2BD的GAO。两个窗口的采样前后身份均为DC。

| 观察量 | 实测结果 |
| --- | --- |
| 原生时钟／boot | 分频计数234或235，约60 MHz；stage0x12、done1、error0 |
| USB状态 | HIGHSPEED(5)，online1、hs_active1、control_online1 |
| 原生最长SE0／段数 | 180002周期，标称3000.033 μs／2段 |
| UTMI最长SE0／段数 | 180001周期，标称3000.017 μs／2段 |
| 回环后有效RXCMD累计 | 11090236周期 |
| 回环后原生PHY／UTMI接收累计 | 9508765／9508765字节 |
| 回环后link方向NXT累计 | 132887周期，不是USB包ACK数量 |
| 主机MIDI回环 | 发送128条、384字节，收到384字节，完整内容逐字节一致 |
| FPGA应用侧MIDI受理累计 | 接收128字、发送128字，与回环消息数一致 |
| 历史接收错误 | rxerror_seen=false |

统计为同一次持续运行的累计值，不把两次GAO之间的全部接收增量算作MIDI载荷；各统计lane仍不保证跨lane原子性。证据在候选目录 `pc_usb2_acceptance_20261029_003454/`，包括 `usb_sysfs.json`、内核／USB拓扑／ALSA端口日志、`midi_loopback.json` 及 `capture_after_midi/`，后者保留身份前后读回、原始CSV和解码JSON。

本次实测打通的是电脑主机→25K USB3300／ULPI→USB2设备核→MIDI应用侧→电脑的HS回环，无需切换USB1 FS。该阶段结束时SRAM保持DC探针，未写任何Flash，也未操作138K。探针不含完整键盘和PL业务响应；下一阶段须恢复完整25K候选，再将USB2连接138K验证实际PL握手及演奏消息，不将本次电脑回环当作板间业务验收。

### 00:43至00:50：恢复完整DA，电脑端PL握手及整屏传输通过

用户要求继续后，00:43:22至00:43:27恢复原完整键盘观察版 `C12528DA`，没有新综合或修改候选输入。写前验证原acceptance构建清单及原回归清单哈希、127个冻结源码快照输入、位流头和SHA256 `61af877c9a7883e28e36fd28bb3fb038d978ee4f7d9b5b01629300388da4778b`；通过原setup／hold／recovery／removal门禁的身份不变。仅执行operation0→4→0，独立读回器件 `0x0001281B`、UserCode `C12528DA`、状态 `0x70022020`。原DC仍可作为诊断回退，两个板的Flash均未写。

00:43:26电脑自动重新以480 Mbps枚举，未要求用户额外拔插。完整DA的GAO为D2B8／32 bit，继续观察实际60 MHz、PHY初始化、USB状态及MIDI受理计数；不使用DC的256 bit解码配置。恢复后boot done1／error0、HIGHSPEED(5)、online1、hs_active1、control_online1。

00:45第一次PL尝试在libusb打开设备时停止，尚未发送HELLO；`/dev/bus/usb/003/035`属于root、模式0644，本用户O_RDWR明确得到PermissionError(13)。用户给予该设备临时读写权限后，00:50:02使用现有 `tools/panel_display.py` 的传输、编码和客户端重新测试，不改PL线协议：

| 验证项 | 实测结果 |
| --- | --- |
| HELLO／CAPS | session `0x29251002`，428×142、RGB565、max_pixels248、max_payload512、heartbeat250 ms |
| HEALTH | 传图前status0／flags4；传图后status0／flags2，即远端页有效且重画提示解除 |
| 完整画面 | page0／frame1，252个唯一tile，60776像素，FRAME_END收到1条DRAWN |
| BUSY恢复 | 40次BUSY均以原seq及完全相同载荷重发；总tile请求292次、成功ACK252条 |
| 画面载荷核验 | 从实际USB OUT跟踪重建121552字节RGB565；每个像素恰覆盖一次，与demo_image逐字节一致 |
| 主机传图耗时 | 约76.46 ms，包含BUSY重试；不等同实物屏幕像素的视觉检查 |
| 完整DA MIDI接收 | 本轮发送128条／384字节，JTAG受理计数从128增至256，增量128；完整固件不是回环程序，不要求MIDI TX同步增加 |
| 测试前后身份及链路 | 两次GAO各自前后均为DA；boot、原生时钟、online和HS保持正常 |
| 工具定向回归 | test_usb2_debug 16项、test_panel_display 16项全部通过 |

00:47另一次128条主机MIDI写入也由GAO确认0→128；其原始写入与后续验证分文件保留，不覆盖先前权限失败记录。本次电脑端证明完整25K的USB2枚举、MIDI接收和PL显示业务可运行，尚未测物理触摸键／编码器产生的MIDI，也未读取138K或宣称板间握手完成。

新证据根为 `~/.cache/fpga-usb2-hdmi/25k-full-da-restore-20261029_004322/`：`deployment.json`绑定原构建／离线回归、127个输入及位流；保留恢复后的GAO、权限失败、USB访问检查和首次MIDI入端结果。成功的PL及MIDI测试在 `pc_protocol_20261029_005000/`，包含完整USB原始收发跟踪、测试前后GAO CSV／身份／解码、两个回归日志及文件哈希汇总 `verification.json`。

当前25K SRAM保持完整DA。下一步保持25K不断电，将USB2接回138K USB-A，并将JTAG移到138K读取实际枚举／分类与事件计数；USB1继续供电时，USB2线必须隔离VBUS，只保留数据和GND，避免两路5V并接。现有138K E5不重新下载或写Flash。

| 同一次主机尝试后的证据 | 排查方向 |
| --- | --- |
| 原生SE0未出现，且PHY输入数据0 | 复位／收包未通过原生ULPI到达FPGA；查USB3300配置、线路及主机连接，先不改MIDI／PL |
| 原生SE0已达3 ms，UTMI未达 | wrapper线态转换路径 |
| 两路SE0已达3 ms，但状态历史仍无2／3 | bridge释放／HS状态机复位计时路径 |
| 原生NXT数据有字节，UTMI无字节 | wrapper RXACTIVE／RXVALID／数据路径 |
| UTMI有字节，地址仍0 | 继续查SETUP、CRC及EP0应答 |

这些分支用于定位数字边界，不把原生接口无事件直接等同某个焊点损坏。暂不切换USB1。需要回退观察时用DB位流及其冻结64 bit工具；需要完整业务时恢复完整DA候选，之后单独验证真实MIDI／PL和138K握手。

完整DA回退：`~/.cache/fpga-usb2-hdmi/25k-midi-debug-c12528da-20261028_175332/acceptance_20261028_182213/ao_0.fs`，SHA256 `61af877c9a7883e28e36fd28bb3fb038d978ee4f7d9b5b01629300388da4778b`。原Flash未更改，不需要Flash回写操作。

## 03:19至03:21：25K接138K的原生统计实测

用户按断电流程将JTAG移回25K并确认恢复连接；USB1供电、USB2接138K USB-A。03:19先实际读回 `GW5A-25A / 0x0001281B / C12528DA / 0x70022020`，用DA对应的D2B8／32 bit配置只读采样：原生时钟计数234，约59.904 MHz，boot stage18／done1／error0、状态5、地址0、online0。不是此前停钟情况下的空邮箱。

写前重新验证DA原清单、位流及127个冻结快照输入，DC原清单、位流及136个原始输入；保留的DC综合暂存树也逐项核对，包括清单声明的BLE ROM绝对路径替换、probe CST边界、SDC组合和诊断宏四处精确转换，全部一致。没有改动冻结清单或候选源码，也没有重新综合。DC位流SHA256仍为 `ba1c3e4a17e8b0167082a303e0172a2f17e2f09301e4ea5d85fd2d64fdb14930`。

03:21执行operation0→4→0，SRAM Program+Verify完成并独立读回 `C12528DC`；随后用D2BD／256 bit配置采集四窗。各窗前后身份均匹配DC。

| 观察量 | 03:21:31 | 03:21:35 | 03:21:39 | 03:21:43 |
| --- | --- | --- | --- | --- |
| PHY时钟计数，单位256 kHz | 234 | 235 | 234 | 235 |
| 当前PHY状态 | HS_SUSPEND(6) | HIGHSPEED(5) | HIGHSPEED(5) | HIGHSPEED(5) |
| 原生SE0最长周期／段数 | 180002／8 | 180002／18 | 180002／28 | 180002／37 |
| UTMI SE0最长周期／段数 | 180001／8 | 180001／18 | 180001／28 | 180001／37 |
| 原生有效RXCMD累计 | 13925 | 29988 | 46238 | 62684 |
| link方向NXT累计周期 | 527994 | 1187982 | 1847972 | 2441963 |
| 原生PHY接收字节累计 | 0 | 0 | 0 | 0 |
| UTMI接收字节累计 | 0 | 0 | 0 | 0 |
| 设备地址／online／control_online | 0／0／0 | 0／0／0 | 0／0／0 | 0／0／0 |

四窗boot均done1／error0、协议统计使能正常；历史状态均为0、1、2、3、5、6，线态历史为0、1、2，rxerror_seen均为false。两路SE0最长分别为标称3000.033及3000.017 μs；从第一窗至第四窗，RXCMD增加48759、link方向NXT增加1913969周期。统计lane之间不保证原子性，NXT不是USB ACK包数；本轮接收累计为0，也不把chirp线态变化误当作已收到了USB数据包。

当前定位：复位线态已穿过原生ULPI和UTMI，设备状态机也走过SEND_CHIRP_K／WAIT_CHIRP_JK并进入HS；本轮不再以“没收到复位”或“PHY时钟未起”作为阻断。缺口在后续正常USB包／枚举之前，不是已收到SETUP后才出现MIDI／PL协议不兼容。没有同期读取138K，仍需区分主机没有发出正常包，还是主机TX／物理数据传输／设备接收配置路径未把包送达；下一次主机观察聚焦CHIRP_DRAIN、HIGH_SPEED_TAIL、RECOVERY、ACTIVE、port_failure、SOF和事务活动，不继续测D+／D−直流电压或切USB1 FS。

四窗采样后立即以同一完整DA位流执行operation0→4→0并确认 `C12528DA / 0x70022020`，随后DA只读复采仍有约60 MHz、boot done1／error0、地址0／online0，当前为HS_SUSPEND(6)。25K保留完整DA，不遗留仅回环的DC探针；两块板的Flash、138K SRAM均未操作。

证据根为 `~/.cache/fpga-usb2-hdmi/25k-138k-native-probe-20261029_031948/`：`preflight.json`保留原始输入检查及暂存转换差异，`dc_source_revalidation.json`逐项核对其声明转换，`diagnostic.json`记录两次SRAM写入／校验及恢复，`da_before/`、四个`dc_capture_*/`、`da_restored/`各保留身份前后读回、原始CSV及解码。`observation.json`汇总本轮定位，`sha256.json`绑定逐文件证据；本轮不更新Flash部署身份或完整电气验收状态。
