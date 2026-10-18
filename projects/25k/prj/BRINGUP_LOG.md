# 实板逐步调试记录

更新：2026-10-16。器件 GW5A-LV25MG121NC1/I0，E2 输入 50 MHz，用户确认全部 BANK 为 3.3 V。测试镜像使用 SRAM 下载。

## 下载器

FT2232HL，USB 0403:6010，Gowin FT2CH 通道 0，JTAG ID 0x0001281B。已完成真实配置操作，不需要额外安装 VCP 串口驱动来进行当前 JTAG 下载。

## LCD

首轮 `lcd_bringup/impl/pnr/lcd_bringup.fs` 使用候选 NV3007 2.79 寸初始化、142×428、SPI mode 0 / 1 MHz、行列偏移均 0。内部 50 MHz 时序通过：Fmax 78.876 MHz，最差 setup slack 7.322 ns，setup/hold 违规端点均 0。

实板用户反馈：**已看到白边彩条，整体稍向上，底部几行杂色**。因此已验证 SPI 通路与首屏显示；窗口对齐尚未通过。第二轮仅试纵向偏移 +10 行，其他显示参数保持首轮值。已完成两项仿真、Gowin 构建，Fmax 78.730 MHz、最差 setup 7.298 ns、setup/hold 违规均 0。已 SRAM 下载并回读校验通过，UserCode=0xB244、Status=0x70022020；用户反馈 **基本没变，杂色在黑条下方白线的下面**。下载日志为 `lcd_bringup/sram_row10_program_20261016.log`，命令及文件 SHA256 为同名 JSON。

随后查证 NV3007 Datasheet V1.0 §5.2.4：GRAM 合法 X=0..167、Y=0..427；行 +10 配合 428 高度使终点 437 越界，不能作为有效配置继续使用。固定提交的配套 Arduino_GFX PDQgraphicstest 2.79 寸示例实际使用 142×428、列偏移 12/14、行偏移 0/0。下一候选使用旋转 0 的列 +12、行 0，并添加行坐标标记；不改模拟初始化寄存器。

**第三轮屏幕实板通过**：COL_OFFSET=12、ROW_OFFSET=0、行号标记 000..416，窗口 `2A 00 0C 00 99` / `2B 00 00 01 AB`。经新的隔离构建入口生成，Fmax 68.714 MHz、最差 setup slack 5.447 ns、setup/hold 违规均 0；SRAM Program+Verify 成功，UserCode=0x294D、Status=0x70022020。用户确认：**“正常了。都正常了”**，包括杂色、行号和上下白边。当前源码保留列 +12、行 0，图案仍为调试彩条与行号。

成功产物路径和 SHA256 在 `lcd_bringup/reports/last_build.json`，本次位于 `lcd_bringup/builds/20261016_003736_574229/impl/pnr/lcd_bringup.fs`。真实下载记录为 `lcd_bringup/sram_col12_program_20261016.log` 及同名 JSON。

## Gowin 崩溃规避

2026-10-16 00:22 的原构建在 `libgowin / Vlgreader::dupPortPin` 读取综合网表时触发 libmalloc 空闲块内存损坏（SIGTRAP）。已将 LCD 字体动态乘法寻址改为固定 case，完整逐像素仿真保持通过；改用全新英文临时目录、综合/PnR 分进程、网表专用 PnR、全局构建锁和独立产物目录。完整新入口已实际完成，未再次崩溃；新镜像已通过 SRAM 校验和屏幕实测。具体第三方工具缺陷根因未证实，没有关闭系统崩溃检测。流程和验证证据见 `tools/README.md`。

首轮执行 SRAM Program and Verify：编程完成，回读报 `Verify failed of at 0`，尽管工具退出码为 0。文件默认 `SecurityBit: ON` 禁止 SRAM 读回，故不能把此操作记为回读校验成功。读得 UserCode=0x000091EF，与文件头一致；随后独立读状态仍为 0x70026020：DONE/wakeup 为 1、CRC 错误位为 0、读回保护位为 1。屏幕真实画面进一步确认新逻辑运行。后续调试构建显式 `set_option -bit_security 0`，以便实际回读校验。

依据：本机 UG714-1.0.4E《Arora V 25K FPGA Products Programming and Configuration User Guide》§4.3/4.4、表 5-1。该手册 §3.4 要求 A 版 JTAG TCK 不低于 15 MHz，工具在首轮自动将请求的 2.5 MHz 更新为 15 MHz；后续使用 15 MHz。

## Bluetooth / Wi-Fi

RTL8723DS 的 UART / BT_DIS# 有 FPGA 连接；Wi-Fi SDIO 与 WL_DIS# 在现有底板图纸中未连接，因此 Wi-Fi 不能通过当前 FPGA 镜像调通。

BLE 原始完整镜像和大 GAO 镜像均未通过布局。已制作生成式资源适配，不改原始 vendor/固件：H5 pending RAM 同步预取、固定 MTU=23 的 GATT 回复缓存压缩、area/map2。适配版五项协议仿真通过，完整补丁 30147 字节 / 120 分片保留。精简 GAO 版真实布局通过：Logic 11854、FF 12316、BSRAM 21（ROM 16、payload 1、GAO 4），50 MHz 核心 Fmax 54.156 MHz、核心 setup/hold 违规均 0。GAO 50 MHz → JTAG 异步路径有 hold -0.606 ns，模块加密使完整 CDC 链不能验证，未盲加时序豁免；详见 `ble_bringup/reports/gao_cdc_review.md`。这限制调试核时序签核，不能把 BLE 功能实测通过说成全设计时序签核。

**实际 BLE 功能通过**：GAO 镜像实际文件名为 `ble_bringup/impl/pnr/ao_0.fs`；SRAM Program+Verify 成功，UserCode=0xEEDB、Status=0x70022020。2026-10-16 00:14 严格名称扫描找到 `RTL8723-BLE`，连接、FFF1 读取正确，三条 20 字节通知的固定内容、CRC16 和递增序号 0/1/2 均正确，通知时间相隔 500 ms。证据为 `ble_bringup/reports/ble_hardware_20261016.json`。

GAO 采样成功导出 128 条状态：H5 linked、initialized、connected，error=0、patch fragments=120、HCI commands=132、ROM version=2。采样时尚未开启通知，故 subscribed=0 与时间顺序一致。原始 CSV 为 `ble_bringup/reports/ble_status_20261016_001418_174723_core0_window0.csv`；该数据用于状态快照，不用 CSV 时间轴推导 UART 波形。

下载 BLE 前的严格名称 `RTL8723-BLE` 基线扫描未发现设备。早期 `ble_before_download.json` 曾误匹配附近通用 FFF0 设备，**不是本板测试结果**；脚本已改为严格名称匹配。

## USB1

直接 FPGA 全速设备接口：D+ L6、D− K6。外部 D+ 1.5 kΩ 到 3.3 V 的上拉是否实装，用户回答不确定。FS 设备需要该连接检测上拉，FPGA 内部弱上拉不能代替。

独立被动观测镜像已生成，尚未下载；集成观测逻辑已在 BLE GAO 镜像中采样。DP/DM 明确为输入、PULL_MODE=NONE；实际 128 条样本均为 00（SE0），activity_seen=0、se0_long_seen=1。没有外部上拉起效的证据；也不能仅据此区分缺上拉、供电或接线问题。LCD 工程未使用这两脚，工具默认是输入加弱上拉，故不能用 LCD 镜像下的线态判断外部上拉存在。当前没有 USB 枚举成功证据。用户选择先继续屏幕调试，暂不做万用表测量。

## USB2

**2026-10-16 18:56 USB2已通过480Mbps High Speed CDC枚举及21,248字节真实回环。** 新增同步ULPI高速镜像 `185336_363191 / User6E78 / GAO D2B0`，主机唯一目标 `FB9A:FB9B / GW25K-USB-HS` 的链路速率为480Mbps，56块跨512字节包边界的二进制回环全部匹配，无额外字节。回环后GAO hs_active/configured均1、RX/echo_consumed均21,248、overflow=0、boot_error/utmi_rxerror_seen均0。此前12Mbps三线FS镜像的1848字节回环及GAO计数也已通过，详见文末两阶段实测条目。当前最后确认加载hs SRAM镜像，仅SRAM Program+Verify，未写Flash；480Mbps是协商链路速率，本轮未测实际吞吐率。统一证据见 [实测记录](usb2_device/reports/usb2_hardware_summary_20261016.json)，FS历史见 [修复后报告](usb2_device/reports/usb2_postrepair_20261016.json)。

## 复现

以下按时间保留历史过程。修复前的“未枚举”“尚未修复”和镜像状态均以对应记录时间为准；USB2最新结果见上文及文末FS/HS实测条目。

### USB1 主动设备尝试（2026-10-16 01:01–01:18）

用户要求“直接尝试USB，先不管硬件连接问题”。新增独立 `usb1_device` CDC字节回环工程，保留原LCD/BLE镜像。固定上游核心并本地生成地址过滤适配；线级仿真通过设备描述符、SET_ADDRESS状态ACK后生效、旧/外地址静默、256二进制字节回环与FIFO溢出计数；官方PLLA模型验证50→60 MHz及失锁复位。上述是仿真结果，不是实板USB通过。

普通USB镜像已SRAM Program+Verify成功，UserCode=1630、Status=70022020；50/60MHz时序通过（含仅复位同步链入口removal的窄豁免）。macOS严格VID/PID/产品名查询无设备，完整USB前后列表13设备无增减，未打开其他串口。

为继续软件诊断，完成真正综合后GAO的分进程构建：使用 `.gao` 在PnR插入一次分析器，独立综合阶段保留观测寄存器；启用单份合并SDC，避免Gowin只启用最后一份SDC。安全入口核对实际启用的GAO输入、XML ID、PnR `-gao`/精确 `-gao_crc` 和每份FS头，禁止RTL GAO重复注入；未退回先前易崩溃的同进程run-all。旧BLE `.rao` 新隔离入口仍未迁移，不能声称已通过此新流程。

当前USB诊断镜像 `usb1_device/builds/20261016_011545_836351/impl/pnr/ao_0.fs`，SHA256 `bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253`；SRAMverify通过，UserCode=4322、Status=70022020。50/60MHz与工具自动20MHz TCK setup/hold违规0，观察器flags仅豁免首级同步D端点。

两次128点实板采样（01:17:11/01:17:51）均为 `0001FFFF0000D0B4/D0B5`：PLL=1、reset60n=1、attach intent=1、USB bus-reset released=0、DP/DM=00、连续SE0计数FFFF、transition历史计数1、received=0。50MHz快心跳逐点交替；主机仍无枚举。**定位在USB总线复位释放之前**，尚无实际描述符传输或CDC回环证据；不据此单独断言硬件根因。本轮按用户要求暂不检查硬件连接。详细统一结果见 `usb1_device/reports/usb_hardware_summary_20261016.json`。

```sh
sh prj/tools/gowin.sh prj/lcd_bringup/build.tcl
sh prj/tools/gowin.sh prj/ble_bringup/build_gao.tcl
sh prj/tools/gowin.sh prj/usb1_bringup/build.tcl
```

工具为 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA`。构建依赖已配置的许可证服务器。下载使用 `Programmer/bin/programmer_cli --device GW5A-25A --operation_index 4 --fsFile <已检查的绝对路径> --cable-index 1 --channel 0 --frequency 15MHz`；必须同时检查文本结果，不能只检查进程退出码。

### USB2 PHY 首轮主动自检（2026-10-16 01:38）

用户将测试线移至USB2。USB2 D+/D−接USB3300，FPGA是ULPI，不能只将USB1核换CST。新增独立`usb2_device`，保留原USB1/LCD/BLE镜像。核对原epro2/PDF，DATA[7:0]={G1,G2,K4,J4,K2,K1,L1,L2}、CLK=L4、STP=L3、DIR=J1、NXT=J2，按用户确认的BANK3.3V配置。60MHz由PHY输出。

ULPI probe通过12个PHY模型场景：正确ID与55/AA回读、NXT延迟、RxCmd抢占、换向保护、错误ID/回读/短读和有界超时。50MHz独立观察器通过缺钟/停钟/60MHz计数、35011个心跳及1093轮完整一致快照。首构建有DIR→STP组合路径setup=-2.412ns，未下载；去掉非必要STP DIR门控后重新构建，50/60/TCK setup与hold违规均0。未放宽ULPI输入输出时序要求。

新镜像`usb2_device/builds/20261016_013729_422944/impl/pnr/ao_0.fs`，SHA256=`aa294286d5ce4ac7308319fcf03663c25f64225e3cf811b20f30a861608fcab8`，SRAM Program+Verify通过，UserCode=ED53、Status=70022020，GAO ID=D2A6。实际读取VID=0424、PID=0004，Scratch两组55/AA通过，FC=45/IF=00/OTG=00配置读回正确，stage12、error0；10ms测得600047个PHY边沿（以板载标称50MHz为参考约60.0047MHz）。128点观测含3组完整一致四页快照，50MHz心跳逐拍交替。

此阶段**只证明PHY与ULPI寄存器链路工作**，没有USB EP0/CDC设备协议，不能把RxCmd计数71当USB包数或称主机枚举通过。结果见`usb2_device/reports/usb2_probe_hardware_20261016.json`。接下来评估USB3300三线FS模式复用现有协议核，继续实际枚举/回环测试，不要求用户先做硬件测量。


### USB2 三线全速 CDC 与活动记录（2026-10-16 09:38–09:58）

按用户“硬件问题不大，继续测试”的要求，通过固件、寄存器与 GAO 继续诊断，不以硬件测量作为测试前提。串行初始化新增注册输出数据和注册驱动准备信号，保留原始 DIR 立即释放及换向空拍；17 个初始化模型场景和逐拍输出等价检查通过。完整 CDC 集成仿真已覆盖 D1 正/反极性 × 普通/活动记录布局共四组合，包括描述符、地址提交/隔离、配置/class、异常 SETUP、256 字节回环、NAK、FIFO 溢出和 reset；这些结果不能替代实板枚举或数据回环。

D1 不反相镜像构建 `usb2_device/reports/build_20261016_093824_666534.json`，SHA256=`2f340250e04118951c7f5d541cb918af1c6170b8c5a1afde9f6ef96d1975a62c`，SRAM verify 通过，UserCode=`3FC2`；反相镜像构建 `build_20261016_095100_930160.json`，SHA256=`962b84ece5d0d30a42e4f1bdeea5b7f924112b4bfba08ea781398d38a9d82ab3`，SRAM verify 通过，UserCode=`BFBC`。两者 Status=`70022020`，50/60MHz/TCK setup/hold 违规均为 0；最差 setup 分别 `0.371ns / 0.667ns`。时序未通过的旧构建已被下载门禁拦住，未下载。

100µs 等待后、进入三线模式前读取 Debug15/Status13，两次 PHY 状态均为 SE1=`11`、SessValid=1、SessEnd=0。两次三线 DATA[2:0] 原始值都为 `000`，不反相时解码 K、反相时解码 J；init_done=1、received=0、error=0。macOS 严格 `FB9A:FB9A / FPGA-USB-Serial` 查询均无目标，故未打开串口或执行真实回环。`SERIAL_D1_INVERT=1` 目前仅为对照候选，尚未证明正确物理极性。证据为 `usb2_serial_status_20261016_093918_854937_core0_window0.csv`、`usb2_serial_status_20261016_095142_465326_core0_window0.csv` 及 `usb2_serial_host_20261016_0942.json`、`usb2_serial_host_inverse_20261016_0952.json`。

独立 activity 镜像 GAO=`D2A8`，构建 `build_20261016_095603_986495.json`，SHA256=`5d6b7795cd22974419a913e0724c7c1de8d0da2a6caccc67e2026a50dd2b0a4d`，SRAM verify 通过，UserCode=`3AE9`、Status=`70022020`，最差 setup=`0.124ns`，setup/hold 违规均 0。09:56:51 与 09:58:14 两次采样只记录到 DATA[2:0]=`000 / 100`，mask=`11h`，跳变计数分别 78/474；tx_seen=0、received=0。采样只在 init_done 后统计，历史不被 USB reset 清空。reset asserted/released 是协议解码事件，不能据此确定主机物理复位。主机端口 `0x1114000` 连接计数从 8 增至 13、status 从 0 变为 512，无地址/枚举失败计数增量；这仅表示连接变化，不能证明描述符传输。

### USB2 同步 ULPI 终端对照（2026-10-16 10:06–10:08）

为在三线模式前核对 PHY 线态，新增独立 termination 镜像（GAO=`D2A9`），不运行 CDC、不进入三线模式。依次自检 VID/PID 与 Scratch、配置并回读 IF08，四阶段均逐项回读 FC/OTG：双下拉 FC41/OTG06 → FS D+ 上拉 FC45/OTG00 → LS D− 上拉 FC46/OTG00 → 双下拉 FC41/OTG06。每阶段读取 16 对 Debug15/Status13；短窗口为等待 10ms、间隔 1ms，长窗口为等待 100ms、间隔 10ms。15 个状态机模型场景通过；官方 GW5A IOBUF/LUT2 模型核对八个 DATA 引脚的输出、高阻、DIR 立即释放及恢复空拍通过。为满足 DIR→OEN 时序，每 pad 保留独立 LUT2/IOBUF，未放宽原时序约束。

短窗口构建 `build_20261016_100552_875557.json`，SHA256=`4d1dad10a642b495383d222ff399823d814565d180fc738ce436628851392db6`，SRAM verify 成功，UserCode=`03A3`；长窗口构建 `build_20261016_100723_028045.json`，SHA256=`e00493cc51feef32014eb25abd2c42f5db5794168aa00d317ca62fd6af0a3668`，SRAM verify 成功，UserCode=`108B`。两者 Status=`70022020`，50/60MHz/TCK setup/hold 违规均 0，最差 setup 分别 `0.261ns / 0.316ns`。

两次 128 点采样结果一致：VID/PID=`0424:0004`，stage=`60h`、done=1、id_ok=1、error=0、error_code=0，line_seen_masks=`1881h`、phase_last_status=`4774h`。四阶段 16 次采样分别只见 `00 / 11 / 11 / 00`，全部 SessValid=1、SessEnd=0；短/长窗口 RxCmd=4/5、RxData=0，计数是 ULPI 字节观测，不能当 USB 包数。原始数据为 `usb2_termination_status_20261016_100633_876073_core0_window0.csv` 和 `usb2_termination_status_20261016_100805_026410_core0_window0.csv`，同名 `_decoded.json` 保存解码。

FS/LS 上拉均呈 SE1，延长窗口后仍复现。这将异常范围缩小到同步 ULPI 下的 PHY 线态，不能只归因于 CDC 协议或三线 DATA1 极性；尚未证明具体硬件根因。**USB2 尚未枚举，没有真实 CDC 回环成功证据。** 截至本条记录，板上为长窗口 termination 镜像 `100723_028045`，结束后保持 `FC41 / IF08 / OTG06`（关闭上拉、双下拉、同步 ULPI Idle）；本镜像 **DONE 灯表示诊断完成**，不表示收到 USB 数据。以上操作仅为 SRAM 下载，未写 Flash。统一证据见 `usb2_device/reports/usb2_hardware_summary_20261016.json`。


### USB2 RxCmd 线态交叉核对（2026-10-16 10:13）

在相同四阶段终端脚本和 100ms 等待 / 10ms 采样间隔下，新增 `rxcmd` 观测布局；顶层 `RXCMD_DIAG` 参数仅切换 page0/page3 格式，不改变终端阶段。GAO=`D2AA`，构建 `usb2_device/reports/build_20261016_101244_771058.json`，镜像 SHA256=`ced020dbd427cb7c24d35bdb9c7a0d10728a130229b6050b4b7cea828924ee1b`；SRAM Program+Verify 成功，UserCode=`6F85`、Status=`70022020`。50/60MHz/TCK setup/hold 违规均为 0，最差 setup=`0.070ns`。

原始采样 `usb2_rxcmd_status_20261016_101332_293787_core0_window0.csv` 四页为 `4C4F4F00 / 41080600 / 600C1881 / 19800500`。stage60、done=1、id_ok=1、error=0，Debug15 轮询的四阶段 mask 仍为1881（仅 `00/11/11/00`）。非请求 RxCmd 历史从各阶段 x0 配置步骤开始，覆盖中间 FC41 detach、目标配置、settle 和 gap，并排除寄存器响应和换向拍；不是只限目标终端稳定后窗口。phase0 无事件，phase1 只见11，phase2见00/11（包括切换过渡），phase3只见00；最后字节依阶段为 `00 / 4F / 4F / 4C`，mask=`1980h`，RxCmd 汇总5、RxData0。无事件 mask=0 不能解释成 SE0，全局汇总不等于 USB 包数。最后字节无事件时间戳或新鲜度标记；phase2 的 RxCmd 混合历史不证明稳定 LS 反复出现 SE0。

RxCmd 与 Debug15 轮询交叉印证上拉阶段 SE1，未据此认定具体硬件故障。此条记录后板上为 `rxcmd` 镜像 `101244_771058`；结束配置仍为 `FC41 / IF08 / OTG06`，DONE=诊断完成，不运行 CDC。下载与采集记录、实测字段已追加至统一报告，历史 termination/serial 证据保留。


### USB2 PHY 软件复位对照（2026-10-16 10:17）

新增独立 `reset` 镜像，`RXCMD_DIAG=1 / PHY_SOFT_RESET=1`，GAO=`D2AB`，沿用 RxCmd 观测布局。在 ID/Scratch/IF08 检查后写 FC61，等待 60000 个 60MHz 周期（约 1ms），回读要求 FC41、Reset 位清零，再执行相同四阶段长窗口终端脚本；成功 stage60 表明上述复位检查通过。

构建 `usb2_device/reports/build_20261016_101616_160185.json`，SHA256=`0f22228f58ecde921e3a0532e6509ebddeb5ce7a1b9eb243d05c7f357590e3e1`；SRAM Program+Verify 通过，UserCode=`9545`、Status=`70022020`。50/60MHz/TCK setup/hold 违规均为0，最差 setup=`0.001ns`，按实际 `usb2_reset_probe.tr` 记录。

原始采样 `usb2_reset_status_20261016_101700_453622_core0_window0.csv` 四页为 `4C4F4F00 / 41080600 / 600C1981 / 19800900`：stage60、done=1、id_ok=1、error=0；Debug15 的四阶段分别见 `[00] / [11] / [00,11] / [00]`，mask=`1981h`。LS 上拉阶段在 settle 后的16次 Debug15 读取中相较未复位对照额外出现 SE0，这与包含配置过渡的 RxCmd 历史应分开解释，不能称复位后所有 LS 样本仅11；但 FS/LS 均未记录到正常的单线高01/10。RxCmd 的四阶段 mask 仍为1980，最后字节仍为00/4F/4F/4C，采集时全局 RxCmd=9、RxData=0，计数仍为 ULPI 字节而非 USB 包。stage60 后阶段历史冻结，但 S_DONE 仍保持 link_active，全局计数可能继续增加，因此9/0不是四阶段独占总数或完成瞬间的冻结计数。

本次软件复位未恢复观测窗口内的正常终端线态，具体原因尚未证实；USB2 尚无主机枚举或真实 CDC 回环成功证据。**截至此条记录，板上为 reset 镜像 `101616_160185`，最终 FC41/IF08/OTG06，DONE=诊断完成**，不运行 CDC。仅 SRAM 下载，未写 Flash。

复核仿真报告 `usb2_device/reports/termination_sim_20261016_101558.json`：未启用复位15场景、启用复位17场景、官方 primitive pad 模型均PASS；串行完整四组合与初始化/协议仿真见 `serial_protocol_sim_20261016_101213.json`。旧仿真报告保留，这些模型结果不等于实板枚举成功。统一报告已追加软件复位证据、时序、采集字段与当前加载身份。


### USB3300 驱动审查与 256 值 Scratch 总线自检（2026-10-16 10:36）

用户要求检查 USB3300 驱动。本轮按手册对同步 ULPI 寄存器事务和三线 FS 适配做两路独立审查，未发现足以确定本次异常由驱动违规造成的证据；三线16拍 guard 是否覆盖实物最坏切换延迟、DATA1 极性尚未实物验证，不能据此宣称整个驱动/三线链路已通过。

新增 `buscheck` 镜像，`RXCMD_DIAG=1 / PHY_SOFT_RESET=1 / FULL_SCRATCH_TEST=1`，GAO=`D2AC`。ID 检查后在 Scratch16 依次写读00..FF共256值，再执行55/AA、IF08、FC61软件复位及四阶段长窗口终端脚本。page0=`{7'b0,count9,first_mismatch_expected8,first_mismatch_actual8}`，首次失败保留期望/实读，无失败时这两字段保持初始0，不能当作最后一次FF回读结果。

构建 `usb2_device/reports/build_20261016_103555_918776.json`，SHA256=`85cd88587f65f9e8e3f648febcc33dee377647af2704c3efd21453d7d2372461`；SRAM Program+Verify通过，UserCode=`4032`、Status=`70022020`。实际 `usb2_buscheck_probe.tr` 的50/60MHz/TCK setup/hold违规均0，最差setup=`0.348ns`。

采样 `usb2_buscheck_status_20261016_103646_478172_core0_window0.csv` 四页=`01000000 / 41080600 / 600C1891 / 10900800`，Scratch count256、首错字段初始0、stage60、done=1、id_ok=1、error=0。数字寄存器链路256值逐次写读实板通过；这不验证三线收发、模拟信号质量或USB枚举。settle后Debug15四阶段为 `[00] / [00,11] / [11] / [00]`，mask1891，FS/LS仍未见正常单线高01/10。包含配置过渡的RxCmd历史mask1090，phase0无事件、phase1见00/11、phase2无事件、phase3见00；零mask不是SE0。采集时全局RxCmd8/RxData0，完成后仍可能增长；phase历史在stage60后冻结，全局计数不能当四阶段独占或完成瞬间冻结值。

新仿真 `usb2_device/reports/buscheck_sim_20261016_103606.json` 包含FULL0/1×reset0/1四组合15/19/17/21共72场景以及官方primitive pad检查，全PASS，旧报告未覆盖。**截至此条记录，板上为buscheck镜像 `103555_918776`，最终FC41/IF08/OTG06，DONE=诊断完成**。仍没有真实主机枚举或CDC回环通过证据，未写Flash。统一报告已保存镜像身份、Scratch逐值结果、线态、时序和限制。


详细逐项手册核对与限制见 [USB3300 驱动审查报告](../docs/USB3300_DRIVER_AUDIT_20261016.md)。


### USB2 低功耗 DATA[1:0] 直接线态对照（2026-10-16 10:50）

新增独立 `lowpower` 镜像（GAO=`D2AD`），按 DS00001783C §6.1.9 / Table 6-6 的低功耗直接 LineState 输出做对照。四阶段双下拉/FS上拉/LS上拉/双下拉，每阶段配置回读后进入低功耗；独立50MHz域确认CLKOUT停止、DIR=1，等待10ms后同步读取DATA[1:0]共16次、间隔1ms，再以STP唤醒并验证醒后FC/IF。这一路不使用Debug15或RxCmd线态解析，观察器也不依赖停掉的PHY时钟。

构建 `usb2_device/reports/build_20261016_104925_911273.json`，SHA256=`51fa21675314cdc0c05eb4c5078099293acc077e04b39c4e084ba6c0b77b62a0`；SRAM Program+Verify通过，UserCode=`1585`、Status=`70022020`。实际 `usb2_lowpower_diag.tr` 的50/60MHz/TCK setup/hold违规均0，最差setup=`0.320ns`。

采样 `usb2_lowpower_status_20261016_105008_081620_core0_window0.csv` 四页=`04240004 / 41000600 / 1881FFFF / 10101010`：VID/PID0424:0004，stage60、done/id_ok=1、error=0、error_code=0。四阶段各16次直接采样，只见00/11/11/00；flagsFFFF表明每阶段采样、停钟确认、唤醒及醒后FC/IF回读均通过。这些flags说明诊断流程完成，不是正常USB线态或枚举通过。低功耗镜像低32位为stage/flags/page/心跳，不是PHY频率计数。

直接采样与此前终端对照一致，降低了仅由Debug15/RxCmd读取或解析错误解释现象的可能性；仍不能排除全部驱动问题，不能据此确定D+/D−短路或PHY损坏。没有真实主机枚举或CDC回环成功证据。**截至此条记录，板上为lowpower镜像 `104925_911273`，最终FC41/IF00/OTG06，DONE=诊断完成**。此前buscheck等历史记录保留；仍仅SRAM下载，未写Flash。


低功耗仿真报告 [lowpower_sim_20261016_105200.json](usb2_device/reports/lowpower_sim_20261016_105200.json) 记录 `FS_OTG_CTRL=00/04` 两组合各17场景（共34），官方 primitive pad 与停钟期间快照检查通过。该报告验证数字序列与观察器，不模拟 USB 模拟负载或电阻行为；两种配置的实板结果分别保存在低功耗对照记录中，不能由仿真报告替代。


### USB2 FS D− 下拉的低功耗实板对照（2026-10-16 10:54）

第二轮 `lowpower_pd` 镜像仅将FS阶段FS_OTG_CTRL从00改为04，GAO=`D2AE`。USB3300 Table6-8允许DP上拉同时启用DM15kΩ下拉；FS阶段为醒时FC45/低功耗FC05/醒后验证FC45、IF00/OTG04，LS仍OTG00。其他停钟、采样、唤醒、读回流程与第一轮相同，最终detach仍FC41/IF00/OTG06。

构建 `usb2_device/reports/build_20261016_105341_951862.json`，SHA256=`b43b7a719e1bfbd28f1402388efb2bcc1a18474d17c01cf551813260897f2b74`；SRAM Program+Verify通过，UserCode=`42D5`、Status=`70022020`。实际 `usb2_lowpower_pd_diag.tr` 的50/60MHz/TCK setup/hold违规均0，最差setup=`0.128ns`。

采样 `usb2_lowpower_pd_status_20261016_105426_066407_core0_window0.csv` 四页仍为04240004/41000600/1881FFFF/10101010，stage60、done/id_ok=1、error/error_code=0；4阶段各16次、flagsFFFF，直接线态仍00/11/11/00。最后FC/IF/OTG字段是读回影子而非睡眠期间即时读数。FS按手册启用DM下拉后直接接收器仍读11，没有使本次DM读数变0；这不能单独认定短路、PHY损坏或主机下拉是否存在，尚无正常单线高01/10及真实枚举/CDC回环通过证据。

`lowpower_sim_20261016_105200.json` 的FS_OTG_CTRL00/04各17场景共34及pad/停钟快照检查均PASS，两种配置现均有独立实板记录，仿真仍不能模拟USB模拟负载/电阻行为。**截至此条记录，板上为lowpower_pd镜像 `105341_951862`，最终FC41/IF00/OTG06，DONE=诊断完成**。两轮低功耗、buscheck等历史均保留，仅SRAM下载，未写Flash。


[低功耗综合后 SDC 对象核查](usb2_device/reports/lowpower_constraint_objects_20261016.json) 确认26个pin patterns均匹配、Gray源与首级各16位。该检查只确认约束对象存在；时序通过依据仍为本次实际 .tr 报告。两次低功耗采集各3轮完整四页快照一致。


### USB2 固定 FS 电压测量镜像（2026-10-16 11:07）

用户已确认USB2供电并有万用表；C15/C13/C11三路直流检查回复“没问题都”，未给出具体数值，不将该反馈转换成任何电压读数。设计/PCB核对确认数字VDD18缺4.7µF是确定设计偏差，但尚不能将原始11线态归因于该偏差。

新增 `measure` 固定FS镜像，GAO=`D2AF`。初始化验证ID、Scratch55/AA和FC45/IF00/OTG04后持续轮询Debug15，不进入低功耗、不detach、不运行CDC；D+上拉和D−下拉持续有效，供万用表测量。已请求R7 D+和R8 D−对GND的具体电压，截至本条尚未回复。

构建 `usb2_device/reports/build_20261016_110634_656420.json`，SHA256=`e68f7a5ae74924116a32e0a4513b73701327e2e03026ec6c119eeef63679f148`；SRAM Program+Verify通过，UserCode=`B07F`、Status=`70022020`。实际 `usb2_measure.tr` 的50/60MHz/TCK setup/hold违规均0，最差setup=`0.115ns`。

采样 `usb2_measure_status_20261016_110729_115936_core0_window0.csv` 四页04240004/45000400/03905388/00000000，stage20h、ready/id_ok=1、error=0、clock_alive=1。Debug最近03h（原始11），历史mask9含00/11，read_count21384；此mask从首个Debug读取开始且无额外settle，不能当稳定窗口mask。page2为Debug8/mask4/count20，计数饱和；FC/IF/OTG为最后读回值。当前DONE表示配置及至少一次Debug读取成功，不能写成正常线态或枚举成功。

仿真 `usb2_device/reports/measure_sim_20261016_110548.json`：10个独立场景、官方pad模型和10401轮完整快照检查全部PASS，不能代替电压实测或USB通信。**截至此条，板上为measure镜像 `110634_656420`，持续FC45/IF00/OTG04，不自动detach，DONE=配置/Debug读取ready**。旧lowpower_pd/lowpower/buscheck历史保留，仍仅SRAM下载，未写Flash。


### USB2 万用表观察与断电电阻检查待回复

用户在固定measure FC45/IF00/OTG04条件下回复：R7（D+）/R8（D−）“都在2.6V附近跳动”。记录为用户万用表近似定性读数，未提供精确范围或波形；它支持实际两线均高，降低“仅Debug解码假象”的解释空间，但不能直接确证短路或坏PHY。前一轮C15/C13/C11三路直流检查仍仅有“没问题都”，没有可记录的数值。

已请求用户拔掉全部USB及下载器、断电测R7–R8电阻，尚未收到结果。本记录不进行硬件操作。最后一次已验证的SRAM加载及GAO采样仍为measure `110634_656420 / D2AF / UserB07F`；由于随后已请求断电测试，实际当前供电与SRAM保留状态未经复核，不能断言它此刻仍运行。


### USB2 断电 DP–DM 低阻连接确认（0.42Ω）

用户针对移除全部USB/下载器并断电后的R7–R8电阻请求回复“0.42欧”，原始用户反馈保存在 [usb2_multimeter_20261016.json](usb2_device/reports/usb2_multimeter_20261016.json)。这是未扣除表笔电阻的用户读数，表笔电阻、反向测量与独立仪表/探点验证均未知，不伪造补偿值。

0.42Ω足以确认DP–DM之间存在近似短路的低阻连接，是直接电气故障；结合此前两线约2.6V及PHY原始11，已不能将现象仅归于Debug解析或CDC协议。短接物理位置未定，不能认定USB3300芯片坏，也未声称修复/重枚举成功。数字VDD18缺4.7µF是独立已确认设计偏差，尚不是这条低阻连接的已证原因。

计划先放大检查USB2、R7/R8、U2.7/8；必要时完全断电抬R7一端，用两个R7 PCB焊盘分别对R8公共DM网络测量来分隔连接器侧和PHY侧。该计划尚未执行、尚未修复。本记录不进行硬件操作，最后成功measure `110634_656420 / D2AF / UserB07F`关联保留，实际当前供电及SRAM镜像仍未经复核。

### USB2 硬件修复后 FS CDC 实测通过（2026-10-16 18:21–18:25）

用户反馈“硬件修复了，测试”。未提供具体短点、返修方法或修后电阻，原断电0.42Ω反馈按修复前历史保留。重新加载measure `110634_656420`，SRAM Program+Verify通过（UserB07F、Status70022020），见 [下载报告](usb2_device/reports/sram_usb2_measure_20261016_182147_264121.json)。[18:22:03 GAO](usb2_device/reports/usb2_measure_status_20261016_182203_115320_core0_window0_decoded.json) 四页04240004/45000400/0130304A/00000000，stage20h、ready/id_ok=1、error=0；Debug最近01h（DP高、DM低），mask3见00/01，read_count12362。该mask包含初始过渡，不是独立稳定窗口。

随后加载不反相serial `093824_666534`，SHA256=`2f340250e04118951c7f5d541cb918af1c6170b8c5a1afde9f6ef96d1975a62c`，SRAM Program+Verify通过（User3FC2、Status70022020），见 [下载报告](usb2_device/reports/sram_usb2_serial_20261016_182233_995777.json)。主机确认唯一FB9A:FB9A设备、12Mbps、configuration1、CDC control/data接口和唯一 `/dev/cu.usbmodem1113201` 均属同一目标，见 [枚举报告](usb2_device/reports/usb2_postrepair_enumeration_20261016_1825.json)。

[真实二进制回环](usb2_device/reports/usb2_postrepair_loopback_20261016_1826.json) 发送/收回均1848字节，8轮1/7/31/32/33/63/64字节分块（共56块）全部逐字节匹配，无额外数据。payload包含随机前缀及00–FF序列，SHA256=`e25decd5d7f178829f3e8bca33f4a9337ff0387b9efb6095876ae1ec33f3194f`。115200只是CDC line coding参数，本轮不测吞吐率。

[回环后GAO](usb2_device/reports/usb2_serial_status_20261016_182529_459220_core0_window0_decoded.json) 四页04240004/450A00D2/145E0738/07380000，三组完整快照一致：stage14、init_done=1、received_seen=1、received/echo均1848、overflow=0、error=0，原始DATA[2:0]=010、解码DP/DM=10。SERIAL_D1_INVERT=0已由实际枚举及回环验证，源码默认值统一为0；反相1为旧对照历史。

首次主机工具漏识别原因是macOS将设备级USB Product Name改为`FPGA_USB_Serial`，真实kUSBProductString仍为`FPGA-USB-Serial`。成功枚举/回环原始报告使用临时显式显示名；随后修复工具优先精确匹配canonical字段、缺省才回退显示名，并同时保存两字段。真实差异回归及全部9项离线检查通过；[默认真实产品名复测](usb2_device/reports/usb2_postrepair_canonical_enumeration_20261016_1827.json) 确认同一registry ID4295057606及串口，旧原始报告不改写。

当前最后确认运行的是不反相serial093824镜像；仅SRAM，断电后需重新加载。本轮通过范围是12Mbps Full Speed CDC及1848字节有限分块回环，不表示480Mbps High Speed、连续大流量、长时间可靠性或原设计数字VDD18电容偏差已验证。综合证据见 [修复后报告](usb2_device/reports/usb2_postrepair_20261016.json)。


### USB2 480Mbps High Speed CDC 实测通过（2026-10-16 18:53–18:56）

用户要求“走480M试试”。新增独立 `usb2_device/build_hs_gao.tcl` 与 `hs/usb2_hs_top.v`，USB3300提供60MHz CLKOUT，FPGA通过同步8位ULPI使用UltraEmbedded CDC HS核及UTMI→ULPI wrapper。启动逻辑退出旧三线/低功耗状态、验证PHY ID/Scratch/FC41/IF00/OTG00后交出总线；512字节bulk包配合2048字节FIFO的整包空间预留。固定CDC commit `d61b43fbd97fcb333fde203d7b885da315e3c2d4`（LGPL-2.1-or-later）和ULPI commit `3c202963ac4b4ae50cadb44ce79c11463d3c6484`（GPL-2.0-or-later）的源码、许可及SHA均保留，派生修改见 [PATCHES](usb2_device/hs/PATCHES.md)。

最终 [185336构建](usb2_device/reports/build_20261016_185336_363191.json) SHA256=`edaa6d5df4630249dc126de835f70e0d31b174a61cc4862fa82c9a4d8dead557`，实际50/60MHz/TCK setup/hold违规0/0；[SRAM Program+Verify](usb2_device/reports/sram_usb2_hs_20261016_185403_506384.json) 通过，UserCode=`6E78`、Status=`70022020`、GAO=`D2B0`。183851构建因8个setup违规未下载；184102构建虽时序通过，但早于最终控制核修补，亦未下载。最终使用185336镜像，未写Flash。

[主机枚举](usb2_device/reports/usb2_hs_enumeration_20261016_1854.json) 确认唯一 `FB9A:FB9B / GW25K-USB-HS`，`UsbLinkSpeed=480000000`、`Device Speed=2`，configuration1、CDC control/data接口及 `/dev/cu.usbmodemGW25KHS011` 的归属一致。[真实二进制回环](usb2_device/reports/usb2_hs_loopback_20261016_1855.json) 在打开串口前再次核对同一registry ID和480Mbps，1/31/64/511/512/513/1024字节各8轮，共56块、21,248字节发送/收回全部匹配，无额外字节；payload SHA256=`10151b68ac0c144145ece39e65866fe93b1b97e7ab128778fadf56cd5ae856f1`。该测试覆盖512字节bulk包边界；480Mbps是链路速率，115200是CDC line coding，本轮不测实际吞吐率。

启动BFM23场景、UTMI包级描述符/控制传输/STALL恢复/ACK后地址提交及512字节回环、FIFO6000有序字节/整包预留/背压、主机工具16项离线检查均通过。复现入口和主机命令见 [USB2 README](usb2_device/README.md)。这些仿真不替代实板证据；上游IN ACK丢失重传、RX CRC回滚及suspend/resume仍不完善，本轮不宣称USB合规或长时间可靠性通过。


[18:56:39回环后GAO](usb2_device/reports/usb2_hs_status_20261016_185639_529325_core0_window0_decoded.json) 采集128条、3组完整一致四页：`04240004 / 000D02CE / 12AE5300 / 53000000`。boot_stage=`12h`、hs_state=5、boot_done/hs_active/configured与hs_seen/chirp_seen均1；boot_error/utmi_rxerror_seen/overflow_seen均0，RX/echo_consumed均21,248、overflow=0，与主机本轮数据量一致。请求地址13、reset历史计数2；该reset计数不等于错误。PHY每10ms约600046拍（以标称50MHz参考）。当前最后确认HS SRAM镜像运行，断电需重载；独立综合证据见 [USB2 HS报告](usb2_device/reports/usb2_hs_20261016.json)。FS/修复前原始记录保持不变。


### USB1 补上拉后 FS CDC 实测通过（2026-10-16 21:34–21:38）

用户要求硬件更改后继续测试 USB1，并确认“补上上拉了”。未提供电阻阻值或具体接法，不将该反馈记为已确认 1.5 kΩ。复核现有 USB1 GAO 镜像与当前参与构建的源码、约束、上游 RTL 一致，复用 `usb1_device/builds/20261016_011545_836351/impl/pnr/ao_0.fs`，SHA256=`bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253`、GAO=`AA53`，既有实际时序报告 setup/hold 违规均 0。本轮没有修改 RTL、重新构建或写 Flash。

[21:34 首次 SRAM Program+Verify](usb1_device/reports/usb1_postchange_program_20261016_213448_176010.json)通过，UserCode=`4322`、Status=`70022020`。USB1 已从更改前持续 SE0 变为 FS_J，PLL、复位和 attach intent 正常，但 Mac 当时保留旧 `Primer 25K MIDI / 1209:0001` 枚举。随后物理拔插使板子掉电重启，UserCode 变为 `944E`，MIDI registry ID 从 `4295068716` 变为 `4295068985`，说明 Flash 启动镜像替代了目标 SRAM 镜像；该时点全零 GAO 属于错镜像无效捕获，不作为 USB1 协议或线态证据。

[21:38 重新加载](usb1_device/reports/usb1_postchange_reload_20261016_213803_924838.json)目标镜像后，SRAM Program+Verify 再次通过，UserCode=`4322`、Status=`70022020`。等待核心启动后，在保持板子供电的情况下，精确匹配唯一 `1209:0001 / location=0x01113200 / registry ID=4295068985`，通过 IOKit `USBDeviceOpen` 与 `USBDeviceReEnumerate(options=0)`触发设备级重新枚举；[调用报告](usb1_device/reports/usb1_postchange_reload_20261016_213803_924838_host_reenumerate.json)两步均返回成功，没有复位上级 Hub 或切断电源。常接上拉未由内部 attach intent 控制，重新加载 SRAM 本身不能保证主机看到断开，因此使用主机重新枚举更新旧描述符缓存。

[主机枚举与真实回环报告](usb1_device/reports/usb1_postchange_hostreset_loopback_20261016_2138.json)确认唯一 `FB9A:FB9A / FPGA-USB-Serial`，registry ID=`4295069140`、location=`0x01113200`、configuration=1、CDC control/data 类 2/10，唯一串口 `/dev/cu.usbmodem1113201`。目标自身 `UsbLinkSpeed=12000000` 与 `Device Speed=1` 均确认 12 Mbps，打开串口前再次核对同一目标及速度。1/7/31/32/33/63/64 字节分块各 8 轮，共 56 块、发送/收回各 1848 字节全部逐字节一致，无额外数据，payload SHA256=`45366e8626cf4b69da2713d8647ba35567a42bebb583486a7cd7b17387ed033b`。12 Mbps 是链路速率，115200 是 CDC line coding 参数，本轮未测持续吞吐率或长期可靠性。

[回环后 GAO](usb1_device/reports/usb1_postchange_pass_status_20261016_2138_decoded.json)128 点均为 FS_J，PLL 锁定、60 MHz 复位释放、USB 总线复位释放、attach intent、received sticky 均为 1；overflow 与 SE1 long sticky 均为 0，当前连续 SE0 计数为 0。SE0 long sticky=1 是已观察到总线复位的历史，不表示当前故障。该 50 MHz 观察器布局没有字节计数，不将线态变化计数或 sticky 标志解释成 1848 字节；数据量与正确性由主机报告证明。

**USB1 本轮 12 Mbps Full-Speed CDC 枚举及 1848 字节有限分块回环通过。** 截至最后验证，运行 USB1 GAO SRAM 镜像，断电需重载；更改前失败历史和错镜像记录保留。综合证据见 [USB1 硬件更改后报告](usb1_device/reports/usb1_postchange_20261016.json)。
