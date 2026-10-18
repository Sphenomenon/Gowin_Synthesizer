# USB2 / USB3300 实板调试

USB2 的 D+/D− 连接 USB3300，FPGA 侧使用 ULPI。**2026-10-16 硬件修复后，USB2 已通过 480Mbps High Speed CDC 枚举和真实二进制回环**：主机发送并完整收回21,248字节，56个分块全部匹配，无额外字节；回环后GAO收到/回送消费计数均21,248、overflow=0，boot_error/utmi_rxerror_seen均0。此前12Mbps三线FS镜像的1848字节回环也已通过，证据按时间保留。480Mbps是协商链路速率，本轮未测实际吞吐率。

当前最后确认加载的是独立 `hs` 镜像，构建清单 [build_20261016_185336_363191.json](reports/build_20261016_185336_363191.json)，UserCode=`6E78`、GAO=`D2B0`。本轮仅使用 SRAM Program+Verify，未写 Flash；断电后需重新加载。统一结果见 [usb2_hardware_summary_20261016.json](reports/usb2_hardware_summary_20261016.json)，HS综合证据见 [usb2_hs_20261016.json](reports/usb2_hs_20261016.json)，FS修复后证据见 [usb2_postrepair_20261016.json](reports/usb2_postrepair_20261016.json)。

## 修复后实板结果（2026-10-16 18:21–18:25）

用户反馈“硬件修复了”，未报告具体短点、修法或修后电阻。重新加载固定 `measure` 镜像后，Debug线态由修前11变为01（DP高、DM低），FC45/IF00/OTG04读回正确，ready/id_ok=1、error=0；历史mask=3含00/01，它仍覆盖初始过渡，不能称为独立稳定窗口。证据：[SRAM校验](reports/sram_usb2_measure_20261016_182147_264121.json)、[GAO解码](reports/usb2_measure_status_20261016_182203_115320_core0_window0_decoded.json)。

随后 [serial SRAM校验](reports/sram_usb2_serial_20261016_182233_995777.json) 通过；主机确认唯一 `FB9A:FB9A / FPGA-USB-Serial`、12Mbps、configuration1，CDC control/data接口及串口 `/dev/cu.usbmodem1113201` 均归属于该设备。[实际回环报告](reports/usb2_postrepair_loopback_20261016_1826.json) 的1848字节包含随机前缀和00–FF二进制序列，按1/7/31/32/33/63/64字节分块共8轮，56块全部通过。该字节数是本轮验证规模，不是吞吐率测试。

回环后 [GAO解码](reports/usb2_serial_status_20261016_182529_459220_core0_window0_decoded.json) 四页=`04240004 / 450A00D2 / 145E0738 / 07380000`：stage14、init_done=1、received_seen=1、received/echo=1848、overflow=0、error=0；空闲原始DATA[2:0]=010，不反相解码DP/DM=10。**不反相DATA1已由真实枚举和回环验证，源码默认值为0。** DONE灯在serial镜像表示收到CDC数据，单凭此灯不替代主机回环结果。

此次发现macOS将设备级 `USB Product Name` 显示为 `FPGA_USB_Serial`，而真实 `kUSBProductString` 为 `FPGA-USB-Serial`。首个成功 [枚举记录](reports/usb2_postrepair_enumeration_20261016_1825.json) 和上述回环记录使用了临时显式产品名；主机工具已修复为优先精确匹配canonical字段、仅缺省时回退显示名，并同时保存两字段。[默认真实产品名复测](reports/usb2_postrepair_canonical_enumeration_20261016_1827.json) 已确认同一唯一设备及串口，旧记录保持原样。

本工程保留 PHY自检、三线CDC、串行活动、终端、RxCmd、软件复位、256值Scratch、低功耗直接线态、FS下拉及固定电压测量十个历史入口，并新增独立高速CDC入口。下文含修复前诊断历史；其中“未枚举”“尚未修复”和当前镜像等表述均以各条记录时间为准，最新状态以上文为准。原0.42Ω反馈保留，不将本轮通信成功改写为具体短点或修后电阻测量。

## 480Mbps High Speed CDC（2026-10-16 18:53–18:56）

`build_hs_gao.tcl` 使用独立 `hs/usb2_hs_top.v`，通过同步8位ULPI连接USB3300。PHY继续提供60MHz CLKOUT到L4输入；480Mbps串行收发由USB3300完成。启动逻辑先退出旧三线/低功耗状态，验证PHY ID、Scratch55/AA及FC41/IF00/OTG00，再将总线交给UTMI→ULPI wrapper及高速CDC核。它与原12Mbps三线镜像使用不同协议实现，不依赖 `SERIAL_D1_INVERT`。

固定上游及每文件SHA256保存在 [UPSTREAM.json](../vendor/ultraembedded_usb_hs/UPSTREAM.json)：UltraEmbedded CDC commit `d61b43fbd97fcb333fde203d7b885da315e3c2d4`（LGPL-2.1-or-later），ULPI wrapper commit `3c202963ac4b4ae50cadb44ce79c11463d3c6484`（GPL-2.0-or-later）。原始源码和许可保留；本地描述符、控制传输、STALL恢复及chirp过滤修改见 [hs/PATCHES.md](hs/PATCHES.md)。HS EP0=64字节，Bulk OUT=`01h` / IN=`82h`最大包512字节；2048字节回环FIFO为新OUT包预留至少512字节空间。

最终 [构建清单](reports/build_20261016_185336_363191.json) 的镜像SHA256=`edaa6d5df4630249dc126de835f70e0d31b174a61cc4862fa82c9a4d8dead557`，实际 `usb2_hs_cdc.tr` 的50/60MHz/TCK setup/hold违规均0，报告所列最差setup/hold slack为0.744/0.185ns。[SRAM Program+Verify](reports/sram_usb2_hs_20261016_185403_506384.json) 通过，UserCode=`6E78`、Status=`70022020`。早期183851构建有8个setup违规，184102构建早于最终控制核修补；两份历史保留且均未下载，本次仅下载185336最终镜像。

[主机枚举报告](reports/usb2_hs_enumeration_20261016_1854.json) 确认唯一 `FB9A:FB9B / GW25K-USB-HS`，`UsbLinkSpeed=480000000`、`Device Speed=2`，configuration1、CDC control/data接口及唯一串口 `/dev/cu.usbmodemGW25KHS011` 均属于同一设备。[真实回环](reports/usb2_hs_loopback_20261016_1855.json) 打开串口前再次检查同一registry ID及480Mbps，按1/31/64/511/512/513/1024字节各8轮测试，共21,248字节/56块，逐字节全部匹配，无额外数据；覆盖512字节包边界。payload SHA256=`10151b68ac0c144145ece39e65866fe93b1b97e7ab128778fadf56cd5ae856f1`。115200为CDC line coding参数，不限制USB链路速率。

[回环后GAO](reports/usb2_hs_status_20261016_185639_529325_core0_window0_decoded.json) 128条样本含3组完整一致快照，四页=`04240004 / 000D02CE / 12AE5300 / 53000000`：boot_stage=`12h`、hs_state=5、boot_done/hs_active/configured均1，hs_seen/chirp_seen均1，boot_error/utmi_rxerror_seen/overflow_seen均0；RX/echo_consumed均21,248、overflow=0。请求地址13、USB reset历史计数2；该reset计数不是错误计数。10ms PHY周期计数600046，约60.0046MHz（以板载标称50MHz参考）。GAO计数与主机本轮字节数一致。

先运行启动、控制传输和FIFO仿真，再通过安全入口构建；主机回环需要安装pyserial的Python环境。本次使用 `/private/tmp/gw25k-ble-env-20261015/bin/python`。以下从项目根目录执行，manifest须选本次成功构建生成的清单：

```sh
sh prj/usb2_device/run_hs_boot_sim.sh
sh prj/usb2_device/run_hs_control_sim.sh
iverilog -g2012 -s tb_usb2_hs_echo -o /private/tmp/gw25k_hs_echo.vvp prj/usb2_device/sim/tb_usb2_hs_echo.sv prj/usb2_device/hs/usb2_hs_echo.v
vvp /private/tmp/gw25k_hs_echo.vvp
sh prj/tools/gowin.sh prj/usb2_device/build_hs_gao.tcl
python3 prj/usb2_device/program_sram.py --image hs --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image hs --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image hs <capture.csv> --output <decoded.json>
/private/tmp/gw25k-ble-env-20261015/bin/python prj/tools/usb_check.py --vid FB9A --pid FB9B --product GW25K-USB-HS --expected-speed-mbps 480 --loopback --timeout 3 --chunk-sizes 1,31,64,511,512,513,1024 --rounds 8 --output <新报告.json>
```

启动BFM的23场景、[UTMI包级控制/描述符/ACK后地址提交及512字节回环](reports/usb2_hs_control_sim_20261016.log)、FIFO6000有序字节和背压检查均通过；主机工具16项离线检查覆盖速度缺失/冲突、误降FS和串口重查。仿真验证数字行为，480Mbps和实物数据回环结论来自上述主机报告。

高速GAO四页为：page0=PHY VID/PID；page1=UTMI模式、请求地址、reset计数及历史/当前flags；page2=boot阶段、HS状态、RX低16位计数；page3=回送消费低16位计数及overflow。READY灯表示PHY时钟存活，DONE表示boot_done且hs_active/configured、无boot_error，单凭灯不能替代数据回环。上游尚未完善IN ACK丢失重传、RX CRC回滚和suspend/resume；本轮是有限干净链路bring-up，不是USB合规、持续吞吐率或长时间可靠性测试。

## 首轮镜像

- USB3300 提供 60 MHz CLKOUT（L4 输入），FPGA 不向该脚输出时钟。
- 读取 VID/PID，要求 `0424:0004`；读取初始 Function/Interface/OTG Control。
- Scratch `16h` 写入 `55h` / `AAh` 并逐次回读。
- 配置全速 peripheral：Interface=`00h`、OTG=`00h`、Function=`45h`，再次回读核对。D+ 上拉由 PHY 终端控制。
- 不启用 Host VBUS 驱动，不驱动 USB1 的 D+/D−。
- 超时及总线抢占有界退出，保留失败阶段；复位时 STP=1、DATA 高阻，DIR 换向留空拍。

所有 ULPI 信号按当前实板 BANK=3.3V 配置为 LVCMOS33。DATA[7:0] 球号依次为 `{G1,G2,K4,J4,K2,K1,L1,L2}`，DIR=J1、NXT=J2、STP=L3。

## 构建与实测

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_gao.tcl
python3 prj/usb2_device/program_sram.py --image probe --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image probe --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image probe <capture.csv>
```

构建沿用英文隔离目录、综合/PnR 分进程、网表专用 PnR 和全局锁，避免先前 Gowin 崩溃路径。下载仅用成功 manifest 指定并核对 SHA256 的新镜像，SRAM Program+Verify；解析文本错误、UserCode 与 Status，不只判断退出码。没有 Flash 操作。

GAO 使用独立 ID `D2A6`，综合后插入一次。50MHz 观察器独立于 PHY 时钟，24 位 Gray 计数器跨域后每 10ms 统计一次，正常约 `600000`，停钟后归零。128 位结果通过握手邮箱传输，完整快照只在 page0 起始提交。

64位采样格式：63:32=页内容；31:12=10ms PHY 周期计数；11:8=stage低4位；7:4={done,id_ok,scratch_ok,error}；3=clock_alive；2:1=page；0=50MHz逐拍心跳。每页8拍，完整页轮转32拍。

| page | 32 位内容（高位在左） |
|---|---|
| 0 | VID16 / PID16 |
| 1 | Function8 / Interface8 / OTG8 / last_read8 |
| 2 | stage8 / flags8 / RxCmd计数16 |
| 3 | RxData计数16 / DATA8 / 保留5 / DIR / NXT / STP |

成功 stage=`12h`。失败 stage 高3位是原因，低5位是脚本步骤；原因1=超时，2=抢占次数耗尽，3=读事务异常，4=ID不符，5=Scratch不符，6=配置回读不符，7=写数据时被抢占。RxCmd/RxData 计数表示 ULPI 字节，不能当作 USB 包数。没有 PHY 时钟时，邮箱结果保持初值，不能据此推断真实 DIR/NXT 电平。

## 依据

- 原图信号：[原理图信息汇总.md](../../原理图信息汇总.md) §5.2。
- USB3300 官方 DS00001783C §6.1.2、6.1.3、6.1.5、6.1.9。
- `probe` 镜像仅验证 ULPI PHY，不包含 USB EP0/CDC；后续 `serial` 镜像的协议与实测结果见下文。

2026-10-16 01:38 实板首测通过：SRAM verify成功，UserCode=`ED53`、Status=`70022020`；VID=`0424`、PID=`0004`，Scratch两组回读通过，Function=`45`、Interface/OTG=`00`，stage=`12`、error=0。10ms测得600047拍，约60.0047MHz（以板载标称50MHz为参考）。GAO128点50MHz心跳正常、完整三轮快照一致。实测报告：[usb2_probe_hardware_20261016.json](reports/usb2_probe_hardware_20261016.json)。

## 三线全速 CDC 镜像

`build_serial_gao.tcl` 是独立入口，显式选择 `rtl/usb2_serial_top.v`，不会同时编译同名 probe 顶层。GAO ID 为 `D2A7`。这一路工作在 **12Mbps Full Speed**；USB3300 支持高速并不等于本镜像提供480Mbps。

初始化再次检查ID与Scratch，按 FC41/OTG00/IF08 配置并回读；等待原协议核的两秒挂载请求，再配置/回读 FC45，最后写 IF0A 进入三线模式并保持60MHz。让出整总线，DIR高后连续16拍守护，再转交 DATA0=TX_ENABLE、DATA1=差分数据、DATA2=SE0。串行期间 STP=0，DIR不再控制三线方向。初始化端口使用显式输入/数据输出/OE，顶层每脚只有一个三态驱动，避免多驱动综合把DIR合入数据路径。

复用固定版本 LGPL-2.1 上游FS bit/packet/transaction/CDC，`generate_serial_core.py` 校验源哈希并生成独立显式收发端口及地址过滤适配，不修改USB1或vendor。完整顶层仿真覆盖 ULPI 初始化、DATA0/1/2 半双工行为模型、描述符/地址/配置/class 请求、ACK 后地址提交和地址隔离、异常 SETUP、256 二进制字节准确回环、空 IN NAK、1024 字节 FIFO 溢出计数及 USB 复位。脚本运行 D1 正/反极性 × 普通/活动记录布局共四个组合；仿真通过不等于实板 PHY 适配、枚举或回环通过。

```sh
sh prj/usb2_device/run_serial_integration_sim.sh
sh prj/tools/gowin.sh prj/usb2_device/build_serial_gao.tcl
python3 prj/usb2_device/program_sram.py --image serial --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image serial --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image serial <capture.csv>
```

串行GAO复用四页结构，内容定义不同：page0=PHY VID/PID；page1=FC/IF/OTG配置影子与line_flags；page2=stage、{pre_serial_phy_status4,{init_done,USB reset released,received_seen,error_or_overflow}}、received_count；page3=echo_queued_count与overflow_count。stage14表示初始化守护完成。IF0A只能显示写入影子，串行运行后不做ULPI回读；flags中的USB reset released也不等于SET_CONFIGURATION已完成。

line_flags={attach_request,init_done,usb_oe,dp_rx,dn_rx,DATA2,DATA1,DATA0}。进入三线模式前等待 100µs，再分别读取 Debug `15h` / Status `13h`；`pre_serial_phy_status4={SessEnd,SessValid,Linestate[1:0]}`。`SERIAL_D1_INVERT` 仅对 TX/RX 的 DATA1 同时异或，不改变 DATA0/TX_ENABLE、DATA2/SE0 或 STP。当前默认值0已由修复后真实枚举及1848字节回环验证；旧默认1只保留为历史对照，不能以解码后的 J 电平替代实际通信证据。模式 guard 16 拍等适配依据见[规范审查](../../docs/USB2_SERIAL_REVIEW.md)。


2026-10-16 09:38–09:52 实板对照：D1 不反相镜像 [093824 构建清单](reports/build_20261016_093824_666534.json) 和 D1 反相镜像 [095100 构建清单](reports/build_20261016_095100_930160.json) 均已 SRAM Program+Verify，50/60MHz/TCK setup/hold 违规均为 0。两次采样均 init_done=1、received=0、error=0，进入三线模式前 PHY 报告 `SE1=11 / SessValid=1 / SessEnd=0`；三线原始 DATA[2:0] 都为 `000`，极性变化仅使解码由 K 变为 J。两次主机严格查询 `FB9A:FB9A / FPGA-USB-Serial` 均找到 0 个目标，因此没有打开串口，也未执行真实数据回环。原始采样和主机检查路径保存在统一报告中。

## 串行活动记录镜像

`build_activity_gao.tcl` 在隔离构建目录启用 `SERIAL_ACTIVITY_DIAG=1`，GAO ID=`D2A8`。page0/1/2 与 serial 相同；page3 为 `{raw_transition_count16,event_flags8,raw_seen_mask8}`，其中 event_flags=`{5'b0,tx_seen,reset_asserted_seen,reset_released_seen}`。仅在 init_done 后记录原始 DATA[2:0]，首样本不计跳变、计数饱和、历史不受 USB reset 清空。普通 serial 与 activity 的 DONE 灯均表示 `received_seen`。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_activity_gao.tcl
python3 prj/usb2_device/program_sram.py --image activity --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image activity --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image activity <capture.csv>
```

2026-10-16 09:56–09:58 两次实板采样只见 `000 / 100`（mask=`11h`），跳变计数从 78 增至 474，DATA1 未记录到 1；`tx_seen=0`、received=0。协议解码记录到 reset asserted/released 历史，不能据此确认发生了主机物理复位。主机端口 `0x1114000` 连接计数从 8 增至 13，未见地址或枚举失败计数增量；连接变化本身不证明描述符传输。

## 同步 ULPI 终端对照诊断

`build_termination_gao.tcl` 使用独立顶层，不进入三线模式、不运行 EP0/CDC，GAO ID=`D2A9`。依次完成 ID/Scratch 自检、IF08 写读，再执行四个终端阶段；每阶段先 FC41，再写 OTG 和目标 FC，均回读确认。每阶段采集 16 对 Debug `15h` / Status `13h`。早期短窗口为等待 10ms、采样间隔 1ms；当前顶层长窗口为等待 100ms、间隔 10ms。

| 阶段 | FC / OTG | 终端配置 | 短、长窗口实测线态 |
|---|---|---|---|
| 0 | 41 / 06 | 关闭上拉，双下拉 | 仅 `00`（SE0） |
| 1 | 45 / 00 | FS D+ 上拉 | 仅 `11`（SE1） |
| 2 | 46 / 00 | LS D− 上拉 | 仅 `11`（SE1） |
| 3 | 41 / 06 | 关闭上拉，双下拉 | 仅 `00`（SE0） |

全部阶段 SessValid=1、SessEnd=0。FS/LS 上拉均出现 SE1，短、长窗口一致；此现象已在同步 ULPI 模式中复现，不能仅归因于 CDC 协议或三线 DATA1 极性，也不足以认定具体硬件根因。

四页格式为 page0=VID16/PID16；page1=FC8/IF8/OTG8/`{5'b0,DIR,NXT,STP}`；page2=stage8/error_code4/`{done,id_ok,0,error}`/line_seen_masks16；page3=phase_last_status16/RxCmd8/RxData8。mask 每阶段一个 nibble，bit n 表示见过线态 n；last_status 每阶段 nibble 为 `{SessEnd,SessValid,Linestate[1:0]}`。RxCmd/RxData 是采集时的全局 ULPI 字节观测总数，摘要饱和至 255，不能当作 USB 包数。stage60 后阶段历史已冻结，但 S_DONE 仍允许这些全局计数继续增加，因此它们不是四阶段独占计数或诊断完成瞬间的冻结值。

```sh
sh prj/usb2_device/run_termination_sim.sh
sh prj/tools/gowin.sh prj/usb2_device/build_termination_gao.tcl
python3 prj/usb2_device/program_sram.py --image termination --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image termination --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image termination <capture.csv>
```

10:07 长窗口 termination 镜像 SHA256=`e00493cc51feef32014eb25abd2c42f5db5794168aa00d317ca62fd6af0a3668`，SRAM Program+Verify 成功，UserCode=`108B`、Status=`70022020`。50/60MHz/TCK setup/hold 违规均为 0，最差 setup slack=`0.316ns`。采样 [100805 解码报告](reports/usb2_termination_status_20261016_100805_026410_core0_window0_decoded.json) 的四页为 `04240004 / 41080600 / 600C1881 / 47740500`：stage=`60h`、done=1、id_ok=1、error=0、mask=`1881h`、last_status=`4774h`、RxCmd=5、RxData=0。短窗口 [100633 解码报告](reports/usb2_termination_status_20261016_100633_876073_core0_window0_decoded.json) 仅 RxCmd=4，其余上述状态一致。

完成后保持 FC41/IF08/OTG06，DONE 灯用于表示此次诊断完成。它不表示主机枚举或 CDC 数据收发成功。全部测试仅使用 SRAM，未写 Flash。


## RxCmd 线态交叉核对

`build_rxcmd_gao.tcl` 复用相同的四个同步 ULPI 终端阶段和 100ms/10ms 长窗口，在隔离目录中启用顶层 `RXCMD_DIAG=1`，GAO ID=`D2AA`。该参数只选择观测布局：page0 改为四阶段最后一个非寄存器响应 RxCmd 字节（阶段 0 在最低字节），page3 改为 `{phase_rxcmd_seen_masks16,RxCmd8,RxData8}`；page1/2 保持终端镜像含义。RxCmd 历史从各阶段 x0 配置步骤开始记录，覆盖中间 FC41 detach、目标配置、settle 和 gap，排除寄存器响应与换向拍；它不限于目标终端稳定后的 Debug15 采样窗口。某阶段 mask=0 表示未记录到事件，不能当作 SE0。全局计数还包括其他合格周期，不等于阶段事件数或 USB 包数。last byte 没有事件时间戳或新鲜度标记；阶段 2 的 RxCmd `00/11` 包含配置过渡，不能据此称稳定 LS 状态反复出现 SE0。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_rxcmd_gao.tcl
python3 prj/usb2_device/program_sram.py --image rxcmd --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image rxcmd --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image rxcmd <capture.csv>
```

2026-10-16 10:13 实板镜像 SHA256=`ced020dbd427cb7c24d35bdb9c7a0d10728a130229b6050b4b7cea828924ee1b`，SRAM Program+Verify 成功，UserCode=`6F85`、Status=`70022020`；50/60MHz/TCK setup/hold 违规均为 0，最差 setup slack=`0.070ns`。采样 [101332 解码报告](reports/usb2_rxcmd_status_20261016_101332_293787_core0_window0_decoded.json) 四页为 `4C4F4F00 / 41080600 / 600C1881 / 19800500`：Debug15 轮询仍仅见 `00 / 11 / 11 / 00`；RxCmd 的阶段 mask=`1980h`，阶段 0 无事件、阶段 1 仅 `11`、阶段 2 见 `00/11`（包括切换过渡）、阶段 3 仅 `00`。各阶段最后字节依次为 `00 / 4F / 4F / 4C`，RxData=0。

独立 RxCmd 事件与 Debug15 轮询交叉印证了上拉阶段的 SE1，尚未证明具体硬件故障。该 rxcmd 镜像在结束后保持 FC41/IF08/OTG06，DONE 表示诊断完成，没有运行 CDC 设备协议。


## PHY 软件复位对照

`build_reset_gao.tcl` 在隔离目录中启用 `RXCMD_DIAG=1 / PHY_SOFT_RESET=1`，GAO ID=`D2AB`，观测布局与 rxcmd 相同。ID/Scratch/IF08 检查后，先写 Function Control=`61h`，等待 60000 个 60MHz 周期（约 1ms），再读取并要求为 `41h`，确认 transceiver Reset 位已清零，随后进入相同四阶段终端对照。失败会保留阶段和错误，因此 stage=`60h`、error=0 也表明此前复位回读检查通过。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_reset_gao.tcl
python3 prj/usb2_device/program_sram.py --image reset --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image reset --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image reset <capture.csv>
```

2026-10-16 10:17 实板镜像 SHA256=`0f22228f58ecde921e3a0532e6509ebddeb5ce7a1b9eb243d05c7f357590e3e1`，SRAM Program+Verify 成功，UserCode=`9545`、Status=`70022020`；50/60MHz/TCK setup/hold 违规均为 0，最差 setup slack=`0.001ns`。采样 [101700 解码报告](reports/usb2_reset_status_20261016_101700_453622_core0_window0_decoded.json) 四页为 `4C4F4F00 / 41080600 / 600C1981 / 19800900`：done=1、id_ok=1、error=0，Debug15 的阶段线态分别为 `[00] / [11] / [00,11] / [00]`，mask=`1981h`。与未复位对照相比，LS 阶段在 settle 结束后的 16 次 Debug15 读取中额外记录到 SE0，这是独立于包含配置过渡的 RxCmd 历史的观察；FS/LS 阶段仍均未见正常的单线高 `01/10`。

非请求 RxCmd 的阶段 mask 仍为 `1980h`，最后字节仍为 `00 / 4F / 4F / 4C`；采集时全局 RxCmd=9、RxData=0；阶段历史在 stage60 后冻结，全局计数在 S_DONE 中仍可能增长，这些值不是完成瞬间的冻结计数。软件复位没有恢复本次观测窗口内的正常终端线态；该结果未确定具体硬件根因，也没有主机枚举或 CDC 回环成功证据。该 reset 镜像最终保持 FC41/IF08/OTG06，DONE 表示诊断完成。

最新 [termination_sim_20261016_101558.json](reports/termination_sim_20261016_101558.json) 记录未复位 15 场景、启用复位 17 场景及官方 primitive pad 模型均通过；[serial_protocol_sim_20261016_101213.json](reports/serial_protocol_sim_20261016_101213.json) 记录串行四组合与初始化/协议仿真通过。这些报告仅用于 RTL/模型验证，不能替代上述实板结果。


## USB3300 驱动审查与 256 值 Scratch 总线自检

本轮按 USB3300 手册分别核对同步 ULPI 寄存器事务和三线 FS 模式适配，未发现足以确定本次异常由驱动违规造成的证据。三线模式的 16 拍 guard 是否覆盖实物最坏模式切换延迟、DATA1 极性仍未完成实物验证，因此不能据此宣称驱动与真实三线链路已全面通过。

`build_buscheck_gao.tcl` 在隔离目录启用 `RXCMD_DIAG=1 / PHY_SOFT_RESET=1 / FULL_SCRATCH_TEST=1`，GAO ID=`D2AC`。ID 检查后，向 Scratch `16h` 依次写入 `00h..FFh`，每次立即读取并比较，共 256 个值；全部通过后继续原有 55/AA、IF08、FC61 软件复位及四阶段长窗口终端对照。page0 改为 `{7'b0,scratch_verified_count9,first_mismatch_expected8,first_mismatch_actual8}`，page1/2/3 与 rxcmd 布局相同。首次不匹配会记录期望/实读字节并报错；无不匹配时这两个字段保持初始 0，不能解释为最后一个 FF 测试的读数。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_buscheck_gao.tcl
python3 prj/usb2_device/program_sram.py --image buscheck --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image buscheck --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image buscheck <capture.csv>
```

2026-10-16 10:36 实板镜像 SHA256=`85cd88587f65f9e8e3f648febcc33dee377647af2704c3efd21453d7d2372461`，SRAM Program+Verify 成功，UserCode=`4032`、Status=`70022020`；50/60MHz/TCK setup/hold 违规均为 0，最差 setup slack=`0.348ns`。采样 [103646 解码报告](reports/usb2_buscheck_status_20261016_103646_478172_core0_window0_decoded.json) 四页为 `01000000 / 41080600 / 600C1891 / 10900800`：Scratch count=256，首错期望/实读字段均为初始0；stage=`60h`、done=1、id_ok=1、error=0。因此这次数字寄存器通路的 256 值逐次写读已实板通过，不能将其扩大为三线收发、模拟信号质量或 USB 枚举通过。

本次 settle 后的 Debug15 四阶段分别为 `[00] / [00,11] / [11] / [00]`，mask=`1891h`；FS/LS 阶段仍均未见正常单线高 `01/10`。包含配置过渡的 RxCmd 阶段 mask=`1090h`，依次为无事件、`[00,11]`、无事件、`[00]`；无事件不能当作 SE0。采集时全局 RxCmd=8、RxData=0；阶段历史在 stage60 后冻结，全局计数仍可能在 S_DONE 增加，不能当作四阶段独占总数或诊断完成瞬间的冻结值。

[buscheck_sim_20261016_103606.json](reports/buscheck_sim_20261016_103606.json) 记录 `FULL_SCRATCH_TEST=0/1 × PHY_SOFT_RESET=0/1` 四组合，场景数分别为 15/19/17/21（合计72），官方 primitive pad 检查也通过；该仿真报告保留独立源哈希，不覆盖旧报告。该 buscheck 镜像最终为 FC41/IF08/OTG06，DONE=诊断完成，不运行 CDC；尚无真实主机枚举或 CDC 回环成功证据。


详细逐项手册核对与限制见 [独立驱动审查报告](../../docs/USB3300_DRIVER_AUDIT_20261016.md)。


## 低功耗 DATA[1:0] 直接线态对照

`build_lowpower_gao.tcl` 使用独立镜像与 GAO ID=`D2AD`，按 USB3300 DS00001783C §6.1.9 / Table 6-6 的低功耗直接 LineState 输出做对照。四阶段仍为双下拉、FS 上拉、LS 上拉、双下拉；每阶段配置并读回寄存器后进入低功耗，独立 50MHz 域确认 CLKOUT 已停止且 DIR=1，再同步采样 DATA[1:0]。本版等待稳定10ms后采16次，间隔1ms；每阶段以 STP 唤醒，再核对恢复后的 FC / IF。这个路径不经过 Debug15 或 RxCmd 线态解码。

本镜像采用独立的 50MHz 状态布局，CLKOUT 停止期间仍能采集。page0=VID16/PID16；page1=FC8/IF8/OTG8/error_code4/保留4；page2=direct_line_masks16/phase_flags16；page3=四阶段采样数（阶段0在最低字节）。低32位含 stage[15:8]、flags[7:3]、page[2:1]与心跳，不含 PHY 频率测量。每阶段 flags nibble 分别记录采样有效、停钟确认、唤醒完成、醒后寄存器回读验证；这些标志表示流程验证，不表示期望的 USB 线态通过。零 mask 表示无采样，不能当作 SE0。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_lowpower_gao.tcl
python3 prj/usb2_device/program_sram.py --image lowpower --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image lowpower --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image lowpower <capture.csv>
```

2026-10-16 10:50 镜像 SHA256=`51fa21675314cdc0c05eb4c5078099293acc077e04b39c4e084ba6c0b77b62a0`，SRAM Program+Verify 成功，UserCode=`1585`、Status=`70022020`；50/60MHz/TCK setup/hold 违规均0，最差 setup slack=`0.320ns`。采样 [105008 解码报告](reports/usb2_lowpower_status_20261016_105008_081620_core0_window0_decoded.json) 四页为 `04240004 / 41000600 / 1881FFFF / 10101010`，stage60、done=1、id_ok=1、error=0、error_code=0。四阶段每阶段16次直接采样，flags=`FFFFh` 表示每阶段停钟、采样、唤醒与醒后回读都完成；直接线态分别只见 `00 / 11 / 11 / 00`，与此前终端对照一致，FS/LS均未见正常单线高01/10。

独立直接采样降低了现象仅由 Debug15 / RxCmd 读取或解析错误造成的可能性；它仍不能排除所有驱动问题，也不能确定短路或 PHY 损坏。诊断流程完成不等于真实三线传输、主机枚举或 CDC 回环通过。本镜像最终为 `FC41 / IF00 / OTG06`，关闭设备上拉，DONE=诊断完成；此前 buscheck 证据保留。


低功耗仿真报告 [lowpower_sim_20261016_105200.json](reports/lowpower_sim_20261016_105200.json) 记录 `FS_OTG_CTRL=00/04` 两组合各17场景（共34），官方 primitive pad 与停钟期间快照检查通过。该报告验证数字序列与观察器，不模拟 USB 模拟负载或电阻行为；两种配置的实板结果分别保存在下列对照记录中，不能由仿真报告替代。


## FS D− 下拉的低功耗对照

第二轮 `build_lowpower_pd_gao.tcl` 使用独立 GAO ID=`D2AE`，只将 FS 阶段 `FS_OTG_CTRL` 从00改为04。USB3300 Table 6-8 允许在 DP 上拉时启用 DM 的15kΩ下拉：本阶段醒时 FC45、低功耗 FC05、醒后验证 FC45，IF00、OTG04；LS 阶段保持 OTG00，最终仍恢复双下拉的 FC41/IF00/OTG06。采样、停钟确认、唤醒及回读流程与第一轮相同。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_lowpower_pd_gao.tcl
python3 prj/usb2_device/program_sram.py --image lowpower_pd --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image lowpower_pd --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image lowpower_pd <capture.csv>
```

2026-10-16 10:54 镜像 SHA256=`b43b7a719e1bfbd28f1402388efb2bcc1a18474d17c01cf551813260897f2b74`，SRAM Program+Verify成功，UserCode=`42D5`、Status=`70022020`；50/60MHz/TCK setup/hold违规均0，最差setup=`0.128ns`。采样 [105426 解码报告](reports/usb2_lowpower_pd_status_20261016_105426_066407_core0_window0_decoded.json) 四页仍为 `04240004 / 41000600 / 1881FFFF / 10101010`，stage60、done/id_ok=1、error=0、error_code=0；各阶段16次，flagsFFFF，直接线态仍为00/11/11/00。FC/IF/OTG字段是最后一次寄存器读回影子，不是低功耗时的即时寄存器采样。

FS 阶段按手册启用 DM 下拉后，接收器直接读数仍为11，本次对照没有使 DM 的读数变为0。这不能单独确定短路、PHY 损坏或主机下拉是否存在；正常单线高01/10仍未出现，也没有主机枚举或CDC回环通过证据。两轮真实低功耗记录均保留；该 `lowpower_pd` 镜像最终 FC41/IF00/OTG06，DONE=诊断完成。


[综合后 SDC 对象核查](reports/lowpower_constraint_objects_20261016.json) 确认26个pin patterns均匹配、Gray源与首级各16位。该检查只确认约束对象存在；时序通过依据仍为本次实际 .tr 报告。两次低功耗采集各3轮完整四页快照一致。


## 固定 FS 电压测量状态

用户已确认 USB2 供电并有万用表。C15/C13/C11 三路直流检查的回复为“没问题都”，没有提供具体电压，记录保留为定性反馈。设计/PCB 核对确认数字 VDD18 缺少要求的4.7µF电容是设计偏差，但它与原始线态11之间的因果关系尚未确定。

`build_measure_gao.tcl` 使用独立 GAO=`D2AF`，初始化检查 ID、Scratch55/AA及 FC45/IF00/OTG04 回读后，持续轮询 Debug15，不进入低功耗、不自动关闭上拉。该固定配置避免四阶段切换，供 R7 的 D+、R8 的 D− 对 GND 直流测量使用；用户随后回复两路“都在2.6V附近跳动”，详见本节追加记录。

```sh
sh prj/tools/gowin.sh prj/usb2_device/build_measure_gao.tcl
python3 prj/usb2_device/program_sram.py --image measure --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image measure --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image measure <capture.csv>
```

2026-10-16 11:07 镜像 SHA256=`e68f7a5ae74924116a32e0a4513b73701327e2e03026ec6c119eeef63679f148`，SRAM Program+Verify通过，UserCode=`B07F`、Status=`70022020`；50/60MHz/TCK setup/hold违规均0，最差setup=`0.115ns`。采样 [110729 解码报告](reports/usb2_measure_status_20261016_110729_115936_core0_window0_decoded.json) 四页=`04240004 / 45000400 / 03905388 / 00000000`，stage=`20h`、ready=1、id_ok=1、error=0、clock_alive=1。最近 Debug=`03h`（线态11），历史 mask=`9h`（见过00/11），读数计数21384；mask从首次 Debug 读取开始累计、没有额外 settle 窗口，不能将其当作稳定状态采样范围。

本镜像 page0=VID/PID；page1=FC/IF/OTG/error；page2=`{Debug8,line_seen_mask4,read_count20}`，20位计数饱和；page3保留0。低32位记录stage/flags/page/心跳，不是PHY频率。独立50MHz快照保持整页一致，Debug计数与最后读数继续更新。DONE/ready仅表示ID/Scratch/配置及至少一次Debug读成功。

[measure_sim_20261016_110548.json](reports/measure_sim_20261016_110548.json) 记录10个独立场景、官方primitive pad检查与10401轮完整状态快照检查通过；模型验证数字行为，不能代替待测的D+/D−电压或实际枚举。该measure镜像在有电且仍加载时保持FS上拉，未写Flash；此前detach诊断与两轮低功耗证据保留。


用户随后在固定 FC45/IF00/OTG04 的测量状态下回复：R7（D+）与 R8（D−）“都在2.6V附近跳动”。这是万用表的近似定性读数，没有给出精确变化范围或波形。它支持实际两条线都处于高电平附近，说明现象不能只用 Debug 解码假象解释；仍不能单独确定短路或 PHY 损坏。

已请求拔掉所有USB及下载器、断电后测 R7–R8 电阻；用户随后回复0.42Ω，具体结果见下节。最后成功镜像/采样关联仍为上面的measure记录；请求断电检查之后，实际当前供电状态及SRAM镜像是否保留尚未复核，不能把“measure正在运行”作为当前已确认状态。此前C15/C13/C11仍只有“没问题都”的定性反馈，无具体电压。


## 修复前历史：DP–DM 低阻电气故障

用户针对“移除全部USB和下载器、确认断电后测 R7–R8 电阻”的请求回复“0.42欧”。[万用表原始记录](reports/usb2_multimeter_20261016.json) 保留该用户反馈；表笔电阻、反向测量和独立仪表核验均未知，不能将0.42Ω写成扣除表笔后的精确板上电阻。

该读数足以确认 DP–DM 存在接近短路的低阻连接，是阻止正常USB差分信号的直接电气故障；它也与两线约2.6V及PHY原始11相符。具体位置尚未确定，不能据此认定USB3300芯片损坏，更没有修复或重新枚举成功的证据。数字VDD18缺4.7µF仍是另一项已确认设计偏差，不能替代对这条低阻通路的定位。

下一步物理隔离计划为放大检查USB2数据焊点、R7/R8及U2.7/8；若仍无可见桥接，可在完全断电时抬起R7一端，分别测两个R7 PCB焊盘到R8公共DM网络的电阻，区分连接器侧与PHY侧。该隔离/返修尚未执行，尚未修复。最后成功SRAM/GAO关联仍为measure `110634_656420 / D2AF / UserB07F`；当前供电及SRAM保留状态仍未复核。
