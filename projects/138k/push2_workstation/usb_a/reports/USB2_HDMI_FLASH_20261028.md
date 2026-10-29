# HDMI／USB 诊断版 E5 配置 Flash 固化：2026-10-28

时间均为 UTC+8。用户明确要求“把当前固件固化进138k，我做硬件检查”，并确认“现在已经接入了”。本次范围为 138K 配置 Flash，不改写 25K。

## 固化镜像与来源

- 镜像为 `custom138k-usb2-hdmi-C11028E5`，保留 HDMI 与 USB／ULPI JTAG 诊断，不是无 HDMI 的 F5 独立自测。
- 复用原 `candidate-e5/impl/pnr/ao_0.fs`，未重新综合，也未改变 RTL、固件、引脚或约束。
- FS SHA256：`e723f82f45e5807452125f8a3bb6429ec4955bce91c7770066586fb738c66703`。
- 写前校验原构建／结构审计、输入清单身份及 122 个暂存输入哈希；配置数据为 5,158,994 字节，从 `0x000000` 写入，不覆盖 `0x600000` 起的保留分区。
- E5 原有 `timing_closed=false` 不变；这次固化不改变其诊断候选身份或电气验收字段。来源与已有回归见 [E5 组合诊断记录](USB2_HDMI_DIAGNOSTIC_20261028.md)。

## 写前备份与回退材料

全部硬件访问持有 `/tmp/gw138k_20261025.lock`。连接为 WINUSB／位置 54、FTDI `0403:6010`、USB `3-6`，FPGA ID 为 `0x0001081B`，Flash JEDEC 为 `0x0B4018`。

14:20:05～14:22:56，使用 openFPGALoader v1.0.0 完整读出 16 MiB Flash。原始备份 `flash_before_16MiB.bin` 的 SHA256 为 `b45811728115589aa719d7766e2dc7b693d4606e7e5119b599dd315dcbb96ead`。

备份起始配置与原 `C1102515` FS 的 5,283,208 个编码字节逐字节一致，未仅凭 UserCode 推断备份内容。原回退文件为 `out/workstation_physical_20261025_c1102515/impl/pnr/custom_138k_integration.fs`，SHA256 为 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`；文件和原始全量备份均保留，本次未执行回退。

## 写入、独立校验与重载

使用 Gowin Programmer V1.9.12.03，目标 `GW5AST-138C`、电缆索引 5、位置 54、频率 0.9 MHz。

| 阶段 | 时间 | 操作与结果 |
| --- | --- | --- |
| 配置写入及校验 | 14:24:06～14:26:36 | `operation_index=54`，E5 FS、地址 `0x000000`；`Program and Verify Flash successfully` |
| 独立配置复验 | 14:26:36～14:27:30 | `operation_index=66`，同一 FS 与地址；`Verify Flash successfully` |
| 保留分区复读 | 14:27:30～14:28:13 | 重新读取 `0x600000` 至 Flash 末尾，共 10 MiB，与写前备份逐字节一致 |
| Flash 重载 | 14:28:13～14:28:14 | `operation_index=1`，没有 SRAM 下载 |
| 延迟身份确认 | 14:30:15、14:30:17 | 两次独立读回 `UserCode=0xC11028E5`、`Status=0x00022020`、器件 ID `0x0001081B` |

重载后的最初 12 秒仍为 `UserCode=0 / Status=0x460`，该观察窗口未等到配置完成，原记录 `failure.json` 保留。随后延迟读回确认 E5 配置完成，无需再次写 Flash 或补下 SRAM；最终 `result.json` 明确记录这一过程，不把中间态当作最终失败。

保留分区 SHA256 为 `c071f4c04a783b5fe08f2d1d705cb3e019cd52ac29154ff7b0cce5b4ec7428d7`。其中原 BPF1 模型仍为 104,510 字节、52,239 个系数，payload CRC32 `AF01A61B`，模型 SHA256 `b02e5d33473fd0e8ee10fe74125ccd0cf5bb3c2467505912dee90abe60e0bbc6`。

## 最终状态与硬件检查

当前配置 Flash 已是 E5，`flash_programmed`、`flash_program_verified`、`independent_flash_verified`、`non_configuration_region_preserved`、`flash_reload_verified` 均为 true。未进行物理断电／上电试验，留给用户随后硬件检查；没有用 SRAM 下载冒充 Flash 启动。

14:30:20 的 Flash 启动后 GAO 窗口为 1024 拍，仍全部为 `ulpi_clock_not_observed`，未识别 25K；CPU 故障为 0、USB PLL 锁定，ULPI 心跳与快照更新均为 0。因此固化完成不改变此前 ULPI 时钟链的定位结论，后续检查仍沿 U2.14 → U5.2／U5.13 → J1.92 → 核心板进行。

机器证据目录为 `$HOME/.cache/fpga-usb2-hdmi/20261028-020452-d5-hotplug/flash_e5_20261028_141840/`，包含用户授权、原始全量备份、回退身份、所有烧录／校验／重载日志、保留分区前后字节、`post_flash_GAO/` 和最终 `result.json`。输出根的 `current-flash-deployment` 与 `current-deployment` 均指向该目录；生成位流、备份和捕获文件不加入源码。

## 用户补焊后的只读复测

用户随后报告“经检查是有个地方虚焊了，现在25k已连接上”，未说明具体补焊位置。15:07:07、15:07:11、15:07:15 的三个 JTAG 窗口前后身份均为 E5，每窗 1024 拍；本轮没有重新下载 SRAM、写 Flash 或改写 25K。

三个窗口的 ULPI 心跳分别变化 646、646、649 次，参考心跳均有 40 个边沿，快照分别更新 129、129、130 次；两组 ULPI 复位释放链均为 1，PHY ready 为 1，初始化故障、时钟故障和 CPU 故障均为 0。此前“未观察到 ULPI 时钟”的阻断已消失，不继续把旧的无时钟记录当作补焊后状态。

25K 尚未完成枚举：三个窗口均无设备分类，端口依次处于 `CHIRP_STREAM(12)`、`ACTIVE(16)`、`CHIRP_STREAM(12)`，第二窗的 SOF 为 878、第三窗回到 0。第二窗主机侧 high-speed 标志为 1，仅说明主机曾进入该分支，不证明 25K 支持或完成了高速握手。下一步定位转向线态、全速回退及枚举重试，不再以供电或缺失 ULPI 时钟作为已知阻断。

原始证据为同一输出根的 `after_solder_repair_20261028_150704/observation.json` 及三个 `capture_*/`；每窗均保留实际 CSV、前后身份、解码结果和哈希。桌面只读监视器另行恢复，启动记录由输出根 `current-monitor` 指向。Flash 固化身份、备份与保留分区结论不变，没有据此修改完整电气或整机验收字段。

## 2026-10-29 02:37至02:38：25K保留USB1供电后的Host观察

接续25K的 [DA固化及接线对照](../../../../25k/example/MIDI_KEYBOARD/reports/FLASH_DA_20261029.md)。用户已将25K USB2接138K USB-A、USB1继续供电，按断电流程把JTAG移回138K并恢复供电。本轮只读，不下载SRAM、不写Flash、不请求复位或重载。

- 实际读回GW5AST-138C／0x0001081B、C11028E5、状态0x00022020；五个GAO窗口各1024点，前后身份均匹配。
- 首窗为host_disabled；其后四窗全部waiting_for_link，reference_enabled为1、PHY ready为1、init_stage为17、port_state为WAIT_ATTACH（7），raw_line_state为0，SOF为0，设备分类为空。五窗CPU、时钟与初始化故障均为0。
- 五窗ULPI心跳变化654／649／646／650／649次，参考心跳各40个边沿，快照更新128／130／130／130／130次，当前138K观察域和ULPI时钟正常。原始DIR／NXT在这些短窗内没有边沿，不扩大为窗口之间从未发生总线活动。
- 核对当前活动firmware.c与三个USB2驱动，其哈希均匹配E5冻结固件输入；精确ELF／ROM哈希也匹配。backend在启动失败后关闭Host并等待100 ms重试，首窗PC 0x46B0在该ELF中属于delay。结合后续使能窗口，不把首窗关闭态误判为主机一直未启动。
- 25K此前已在保留USB1供电、USB2接138K的接法下观测到约60 MHz及boot done，但随后为移动JTAG两板均断电。本轮没有读取25K，不能将前一轮时钟结果冒充本轮同步实测。

当前采样显示主机尚在等待物理接入宣告，未形成可据以判定协议不兼容的枚举记录。下一步不换JTAG、不改固件，保持两板通电及现有接线，使用直流电压档分别测两块板各自USB3300的U2.7（D+）与U2.8（D−）相对GND电压，对照两端数据线电平。USB3300脚号来自原始DS00001783C表3-1，25K PCB同时核对为USB2_HS_DP／USB2_HS_DM。

证据位于 `~/.cache/fpga-usb2-hdmi/138k-powered-25k-host-20261029_023758/`，含五次身份／原始CSV／解码、冻结固件身份核验、观察汇总及逐文件哈希。138K E5与25K DA Flash均未改写。

## 2026-10-29 02:57：两端D+／D−均接近0 V

用户报告138K与25K各自USB3300 U2.7（D+）、U2.8（D−）四处电压均接近0 V，未提供精确数值。随后只读复采138K E5：PHY ready为1、WAIT_ATTACH（7）、线态0、SOF 0；ULPI心跳变化654次、快照更新130次，无CPU／PHY初始化故障，不下载或复位。

这些直流读数不能单独区分高速空闲与未宣告接入，不能据此认定断线或芯片损坏。核对DA冻结源码：25K上电复位由50 MHz计数器产生，无独立外部应用复位输入；HS空闲检测后的HS_SUSPEND会恢复FS终端。下一步保留USB1供电、只从25K拔掉USB2数据线，等1秒后测25K U2.7相对GND电压，先判断无主机连接时设备端是否恢复D+上拉；JTAG留138K，不再更换或重烧。

用户测量与当前主机观察分别保存在 `~/.cache/fpga-usb2-hdmi/138k-zero-data-volts-20261029_025737/observation.json` 及原始采样中，保留定性测量范围和哈希清单。

### 数据线直流电压判据纠正

用户补充：拔掉USB2后25K D+仍接近0 V，接电脑（此前成功的接法）也接近0 V。仅凭万用表直流读数，无法可靠区分高速空闲、PHY状态或未宣告接入；前述以该读数作为主要上拉判据的排查分支停止，不据此判定芯片或线路损坏。此次电脑lsusb未出现FB9A设备，不能把此前480 Mbps成功记录写成此次已重新枚举成功。

下一步改用现成C12528DC原生统计探针，检查RXCMD、原生／UTMI SE0最长时长、NXT及PHY／UTMI字节计数。已只读核验原构建清单、GAO配置、位流头与SHA256、路由后门禁，无需重新综合；当前尚未下载。须断电把JTAG移回25K，恢复USB1供电和USB2接138K后先读取DA身份，再按既有SRAM授权载入DC诊断；DC不含完整键盘业务，诊断后恢复DA，保留DA Flash和138K E5不改写。

## 2026-10-29 03:21：25K原生统计已收到复位及chirp，但无正常收包

用户完成断电移线后，在25K端先读回完整DA，再临时以operation4载入DC到SRAM，四窗采样后恢复原完整DA并独立确认身份。原DA的127个输入、DC的136个输入及其精确暂存转换、两个原清单和位流均重新核验一致。本轮没有操作138K或两块板的Flash。

25K四窗原生时钟约60 MHz、boot done1／error0，原生SE0最长180002周期、UTMI最长180001周期，均约3 ms；SE0段数8→37，原生RXCMD13925→62684，link方向NXT527994→2441963，设备状态历史包含WAIT_RST、SEND_CHIRP_K、WAIT_CHIRP_JK、HIGHSPEED和HS_SUSPEND。但原生PHY及UTMI接收字节累计四窗均0，地址0、online0、control_online0，未出现已收到SETUP后的业务协议不兼容证据。

本次把缺口收窄到复位／chirp之后、正常USB包及枚举之前；不是复位没有到达25K。当前JTAG仍在25K，不能把其本地HS状态直接替代138K同期观测；下一轮聚焦主机CHIRP_DRAIN至ACTIVE的状态、port_failure、SOF与事务活动，区分未发包和发包未送达，不再沿用D+／D−直流电压分支。当前25K SRAM及Flash均为完整DA，138K原E5保持不变。

逐窗原始值、两次SRAM下载／校验、DA恢复及证据索引见 [25K原生统计实测](../../../../25k/example/MIDI_KEYBOARD/reports/USB2_RXCMD_DIAGNOSTIC_20261029.md#0319至032125k接138k的原生统计实测)。原始目录为 `~/.cache/fpga-usb2-hdmi/25k-138k-native-probe-20261029_031948/`，保留CSV、身份前后读回、解码和逐文件哈希。
