# 整机黑屏：DDR 训练实测（2026-10-26）

2026-10-26 上午续查已有同板正向对照：官方 B1 校准成功；E6 原网表仅补官方 PLL/DLL/CLKDIV 三项物理位置，增量 B2 的校准与 8 MiB BIST 均通过，反向回切也重复确认。完整工作站 B3 随后同样通过校准/BIST、前台帧有效、显示取数复位释放，10:40 留在 SRAM 待用户实屏确认；仍有欠载历史标志，未做 Flash。完整来源与验收边界见 [官方 DDR A/B](WORKSTATION_DDR_OFFICIAL_AB_20261026.md)。下文保留凌晨的排查过程，不再将“尚缺官方同板对照”视为当前状态。

## 范围与结论

本记录接续 [黑屏排查](WORKSTATION_HDMI_BLACK_20261025.md)。时间均为 UTC+08:00。用户“运行，你自己找问题”及后续“继续”授权临时 SRAM 诊断和 JTAG 抓取；不执行 Flash 操作或断电重启。此前 Flash 操作历史仍以 [部署记录](WORKSTATION_DEPLOYMENT_20261025.md) 为准，不能由本轮没有操作 Flash 推翻。

**实测阻塞点为 DDR 校准，而非 HDMI 彩条／TMDS 链路。** 完整工作站 E4 中 DDR PLL 锁定、校准未完成、显示取数复位未释放；时序闭合的隔离 E6／E7 同样未校准。E7 稳定停在 `READ_CALIBRATION`，DLL 锁定、写 leveling 完成，尚未完成眼图扫描和初始化。不能据此断言某根 PCB 线断路，也不能宣称 DDR 配置、模拟时序或硬件已经全部排除。

原 `C1102515` 位流、输入和审计不改写。E4 插入 GAO 后重新布局，其观测不能冒充原位流内部状态的直接读数。E5～EA 是隔离诊断，不含 HDMI／音频／USB／BLE，运行期间显示器无信号是预期现象，不是新的 HDMI 回归；不替代生产 profile，不以删除功能换取整机时序通过。

## 完整工作站 E4

以下路径以 `projects/138k/push2_workstation/usb_a/` 为根。E4 位于 `out/workstation_hdmi_jtag_20261025_c11025e4/`，UserCode `C11025E4`、GAO ID `25E4`。精确复用原 VG／CST／SDC，只插入 16 位、50 MHz、1024 样本 GAO，利用 E1 已完成的正常布线缓存增量 P&R，未重综合整机。10 月 25 日 22:44:14～23:28:27 完成，耗时 2653.449 秒。

| 身份 | SHA256 |
|---|---|
| 原整机 VG | `ad6b4b197b415bec56bbae78b8fac16a429fcb3741617299d6e65f0faff8a5ff` |
| E4 输入清单 | `ea2577e7c0c5d1bd3ca57cd65bc0414a5f310ebb4fc8606908e35953591b8cd3` |
| E4 FS | `20ef5ff76d01896d267934af1a36eb2f8e96153b80e0544062cc8deb552fe186` |
| E4 实现核验 | `2cc290977fd719ef952b8698827b83fbb1dc9d0aa6953a7bf97d2f684905e379` |
| E4 SRAM 部署结果 | `313f763235193410461e45ec9b29ea03a45d7784284ea0316cf4d5d76692d67f` |

四份原物理审计重新执行：CDC、PLL、原生路由通过；setup −0.893ns、hold +0.095ns、recovery +3.041ns、removal +0.250ns，**时序未闭合**。GAO 新增 `tck_pad_i` 20 MHz，原生严格时钟清单的拒绝保留，不改检查器掩盖。业务 BSRAM 321 与 GAO BSRAM 1 分列，物理合计 **322**。原位流 −0.568ns 的用户接受不转移为新 E4 的正式验收。

最初 watcher 对 FS 头部漏写 `0x`，后检查断言失败并非构建失败；恢复核验另存 `postcheck_recovery_20261026_01.json`。补充 `physical_inputs.json` 继承的 E2 准备哈希／时间不回写，实际 E4 输入以 `observer_input_manifest_sha256` 及原 `inputs.json` 绑定。

00:34～00:35 SRAM 下载后独立读回 E4，00:37:11～00:37:18 三次抓取各 1024 样本，每次核实 WINUSB OPEN、全部 READ_RAM 响应以及前后 UserCode，不以工具退出码单独认定成功：

- `memory_flags=0xC0`：DDR／视频 PLL 锁定，DDR calibrated、BIST done、front valid 为 0。
- `video_flags=0x26`：像素域复位释放、串行器未保持复位，但 scanout 复位仍在。实际消费源码中显示共享链路依赖 `memory_reset_n`，校准失败阻断取数／出帧。
- HPD 为 0；只记录当时读数，不假定用户此时插着线。HPD 不门控 DDR，不能归因为训练失败。
- 渲染计数仅抓最低位，不能单由该位为 0 证明整个计数停止。

三份 `jtag_capture_20261026_0{1,2,3}/status_summary.json` SHA256 分别为 `fccf8830151600de645987844f7a23446ea60afab919a003917017f4ef3d1640`、`083ef595ee69a39dfc716bd6cee3ff706a3bf8659a1f364b07a6dd582d9ca02a`、`90346faa0d1851194869616d7ef3000f88e4992233e28ec2dad94b943308c3be`。

此前 64 位 E1／E2／E3 分别在 2400／1200／5400 秒超时，均没有 FS、没有下载。E3 的调试栈显示耗时在正常布线之后的 `gaoPathRouter`，不是 95% 日志后的导出；缩为 16 位才完成 E4。

## 精确来源隔离 E5／E6

`reports/hdmi_usb3_20261025/ddr_calibration_diagnostic.sv` 只组合原 reset、DDR platform／recovery、原厂 IP／PLL、原 BIST。九份源逐字取自实际整机 stage `out/workstation_integration_20261025_a23_v5/workstation/Prj1/`，与 `staged_input_sha256` 核对；父清单 SHA256 `88af98466644d04b5cd1b70d1e0695571530e3201abf6beb371f258d7dfb7863`。没有编辑 vendor、冻结 baseline 或业务 RTL。

复用现有 BIST 8 MiB 启动保留区，不新分配 DDR 地址。写命令／数据保持原生同拍握手；UI Gray 计数独立于校准复位，用来分辨“时钟运行”和“校准放行”。Flash 引脚闲置，U15 仅输出诊断异或，不是 UART 协议。

E5 只综合小子集，不重综合整机。P&R 58.070 秒，setup +0.630ns，但既有 `ddr_init_internal_r → wloadn_3` hold −1.331ns，**没有下载 E5**。E6 复用 E5 VG／SDC／GAO 增量 P&R，将发射寄存器放在 `R[70:80]C[150:170]`；保留接收区域、原 `set_min_delay 0.800`、50／400／100 MHz 时钟及全部原 DDR 例外，不降频、不切掉违规路径。耗时 71.091 秒。

| 项目 | E6 |
|---|---|
| 目录 | `out/workstation_ddr_calibration_20261026_c11026e6/` |
| UserCode／GAO | `C11026E6`／沿用 `26E5` |
| 输入清单 SHA256 | `5e9608e63c7ade20c677e7e648361f458d808c60efdf674e1d957a70b4d01212` |
| FS SHA256 | `443fbfbcc03ec57dd98fb5ffae4b81c58e983abbff285c0b64551940de71ee0e` |
| 实现核验 SHA256 | `dfec74ec71bfe10ec83d143d6838078d642213bf89116fa788b29cd5c76ce26c` |
| setup／hold／recovery／removal | +0.631／+0.130／+2.536／+0.253 ns |

真实路由 PLL 50→400 MHz、CLKDIV 除 4→100 MHz、诊断两级同步物理延迟和 GAO 绑定通过检查；这不是模拟眼图、整机或全部 PHY 路径签核。原始通用时钟布线警告保留。

E6 于 00:53:43～00:53:50 从 E4 切入 SRAM 并独立读回；部署结果 SHA256 `af85b3bc713288129bd2517ff47a1608b9eec05d21fffb8a410d9393af799470`。第一次抓取因旧 GAO 死 socket 在预检失败，空目录保留；确认无监听者后只清理本用户死 socket。有效抓取为序列 03／04：

- 状态均 `0x03`：全局复位释放、PLL 锁定，calibrated／BIST 为 0。
- 原始 `controller_rst_n=1`、`controller_reset=0`、`qualified_lock=1`、`pll_stop_3=1`。
- 每次 1024 样本 UI Gray 各位跳变合计 2046，确认 UI 时钟运行，不等于校准成功。
- 两份摘要 SHA256：`e1373e3a60bfd3b2d182dd81f2161cc485b3427fc82a985ad1f94d10179a0982`、`84ac3d386ca5484322182b7be3b7abedbc4b975a886a4502924d3c73d5dbab38`。

## 初始化状态 E7

E7 保持 E6 VG／CST／SDC，只把 GAO 改为状态 8 位、init 状态机 20 位、训练标志 4 位。新名字先核对 E6 实际路由网表声明。P&R 59.618 秒，无 RTL 重综合；四项时序与 E6 相同且非负。原始跨域信号仅解释稳定平台，不承诺瞬态状态原子性。

- 目录 `out/workstation_ddr_calibration_20261026_c11026e7/`，UserCode `C11026E7`、GAO `26E7`。
- 输入清单 SHA256 `3f59276aa9176208939b339058aa84e9b3f40696010620d2b89db670227eb99d`；FS SHA256 `d44dcb2c1a605f6872ada63979384a2c1ad82f36f38bcae69143ebe0b2e306b3`。
- 实现核验 SHA256 `855838d81421f8bb42557ae0421cf729c88486f8e6d9ef1fa91464a971d3ead4`；部署结果 SHA256 `4e3cd8a4d557baf44cc4b0909f1c6beeebeba730c58f8c82b3478b9d372f36ce`。
- 01:06:04～01:06:11 从 E6 SRAM 切至 E7，独立确认身份。两次 1024 样本均稳定 `READ_CALIBRATION=1`，其余 19 个 init 状态为 0；`dll_lock=1`、`wrlvl_complete_Z=1`、`init_rmove_done_r=1`、`eye_calib_done_r=0`。
- 摘要 SHA256：`f0413536125afdf4f2a0eb1d40ec83f21a17b706c9c53aacdd1659c6966eb6f6`、`4901bab3dca5ee39146b004d9eb7c945f676504acb146fd88bbe46dc8e38f3ad`。

## 字节通道 E8 与读回资格 EA

E8 精确复用 E7 的 VG／CST／SDC，只换 32 位 GAO 通道探针；增量 P&R 65.976 秒。四项 STA 与 E6 相同，实际 PLL／CLKDIV、诊断 CDC、GAO 绑定均通过。01:10:49～01:10:57 SRAM 切入并独立读回 `C11026E8`，随后两次抓取中四个 `read_cal_done` 均为 0，四个 `rburst_cnt_check` 为 0；`phy_rdbk_data_valid` 和 `readback_check_*_8` 有跳变，不能仅看首尾均为 0 就称没有任何活动，也不能将本地 valid 跳变当作 DDR 数据正确。

| E8 身份 | SHA256 |
|---|---|
| 输入清单 | `65f0a9667433daf0077da14ced9efaa32c71acfb40a3e578760224fda4935daa` |
| FS | `88a918ba057154f6b6e71edd8fe75411998384e36314daef28a837a761fa7c86` |
| 实现核验 | `ffbc37a98acd655aed65d6f5a4e4123454a63a70ee432c44157761a8c6d005d1` |
| SRAM 部署 | `0132f296ed9de017e353ad592de2713be78d7d703931d143a9f31adf3f293bb0` |
| 抓取 01 | `73c242f4fb4dd53d45a298a6af80bded26e38ccbe8505aef7af3af18a383bbb5` |
| 抓取 02 | `8e2dd9e97032de15c0a5a04045eb1bb80900ba48ae597b4bf3f8a0ffcb04082e` |

为避免 50 MHz 采样漏掉单个 UI 周期信号，E9 计划用原 UI 100 MHz 采样，但 GAO 不支持直接捕获 `ddr_cke` 输出脚，处理网表时报错。E9 保留失败证据，**没有下载**，没有在同一身份下替换输入重试。EA 使用内部已声明的 `cke_en`、`mux_reset_n`，其余保持相同 VG／CST／SDC 和 E8 增量参考；仅新 GAO，未重综合 RTL。两者是控制器内部信号，不是 DDR 引脚的电气测量。

EA 位于 `out/workstation_ddr_calibration_20261026_c11026ea/`，UserCode `C11026EA`、GAO `26EA`，32 位、UI 100 MHz、1024 样本。P&R 65.131 秒；setup +0.631ns、hold +0.130ns、recovery +1.511ns、removal +0.253ns，保留原时钟／例外。01:19:02～01:19:09 从 E8 SRAM 切入并独立确认身份，01:19:09／01:19:12 两次成功抓取：

- `mux_reset_n=1`、`cke_en=1`、`READ_CALIBRATION=1` 均保持整个采样窗；读校准子状态进入 `READ_CAL_RBURST_CHECK`，不是静态停钟。
- 四个 DQS 原语实际输出 `RBURST` 及其 `rburst_reg` 均为 0；四个 `rvalid_cnt_check` 为 0。读完成所需的 burst／valid 资格没有成立。
- 寄存的 `readback_check[3:0]` 有跳变，不能将其中某次为 1 宣称为读校准成功。每通道只抽样一个数据位且均为 0，**不足以推出整个 256 位数据全部为零**。
- 实际路由网表确认 RBURST 来自四个 DQS 原语，而不是软件自行生成的状态副本；记录见 `source_reference_comparison_20261026_01.json`。这仍不等于用示波器确认外部 DQS 波形。

| EA 身份 | SHA256 |
|---|---|
| 输入清单 | `59e461ed785c015fff0e76a92dbdf5b8d8f4cc359a991830348b6d013283f815` |
| FS | `35ad300bb457bd41b9e6e8cfa9871e88768f6dab6aa5d9eaeee6d95cbfd834dd` |
| 实现核验 | `4ee1f19c4289a94b0d0551ecf4464bb4c147e9e63af70f180e82f82ade888fe4` |
| SRAM 部署 | `850ad85dcbdd6427f5aa80a3ef5bf3cb356f602bb5aeaa18f1e8d37fc9094aeb` |
| 抓取 01 | `4fa776655b3288ba38501b0da0785090e11173d148bf3477e25885dbef0660db` |
| 抓取 02 | `562629b43403e1ff97ce00e5e7f3afc51a74019dc8c74e2a12e40db882ba3875` |

补充来源核对：选用四份 vendor `.v` 与仓库锁定历史参考逐字相同；全部 DDR `IO_LOC`／`IO_PORT` 与 accepted core 约束相同。本地外部官方示例目录已经不存在，不能把锁定参考字节比较写成重新获取官方最新工程。平台固定 32-bit、400 MHz CK／100 MHz UI；载板配置本身仍假定同款 30354 核心板和电压设置，载板网表不提供核心板内部 DDR 走线或当前实装颗粒证据。

### 随后的公开官方来源交叉核对

01:26 之后另行只读获取 `sipeed/TangMega-138K-example`，固定提交 `06e7d8b118d345915ab6f257b7c22226f81575cd`（提交日期 2026-08-20），不切换当前 profile、不下载官方预编译位流。首次 raw 下载无进展，停止本任务的下载进程并保留失败记录；改用 GitHub API 获取九份小文件，逐份验证 Git blob 身份。文件与清单保存在 `out/workstation_hdmi_black_20261025_01/official_ddr_reference_20261026_02/`。

- 当前加密 DDR IP 保留原 CRLF，官方仓库为 LF；**仅在内存中为比较归一化换行**后，Git blob SHA1 精确等于官方 `128520da4a8b780dea685f833e8055154b3ff901`。因此不是原始字节完全相同，但没有其他内容差异；未改 vendor 字节或原输入哈希。
- 三份 PLL／PLL_INIT 与官方文件的差异仅为历史已声明的模块名前缀及适配说明行；逐字符比较确认逻辑和参数不变，包括动态模拟参数搜索、PLL reset 和 CLKOUT2／ENCLK2 连接。
- 官方实际使用的 66 项 DDR 球位及 66 项电气属性均一致。官方 CST 额外遗留 `ddr_addr[15]` 的 R1 约束，但官方 top 自身也是 `[15-1:0]`，仅有 A0～A14；这是未使用约束，不能据此给当前 15 位接口硬加 A15。
- 官方顶层也无需 UART 命令才启动校准；用户流量在初始化完成前不参与训练。未找到当前第一方封装漏接训练触发或 PLL 控制的证据；这仍不是官方位流的独立实板对照。

交叉比较机器证据 `comparison.json` SHA256 `82b11a5f5013d7ad97cb76c9789edbe340ee33fa4ecbcd3e072f442f6582fdce`。上述只读网络比较期间，板上一直保持已恢复的完整工作站 `C1102515`。

**下一判别边界是 DDR 的真实读返回／DQS 接收条件。** 现有观察不能区分颗粒／电压／时钟到达／读门控相位等原因，不能据此盲改 HDMI 线序、放宽 STA、绑高 calibrated 或强行跳过 BIST。若继续定位，需同一核心板的独立官方 DDR 读写对照，或真实 DDR CK／DQS／供电测量；此前彩条正常没有使用 DDR，不能代替这一对照。尚未修复黑屏，不宣称硬件故障已经确认。

## 验证与退出

`verify_ddr_jtag.py` 核验输入、原路由解析器、四类 STA、PLL／CLKDIV、诊断 CDC 和 GAO。`capture_ddr_jtag.py` 本身不烧录，要求前后身份、WINUSB OPEN／全部 RAM 读取成功、CSV 位宽／顺序／1024 样本一致。WINUSB 适配仅在 GDB 中临时改宿主进程，不改 vendor 程序或 FPGA 字节；工具、recipe、包解析 helper 均校验哈希。

针对性回归：原生握手／BIST、无校准但时钟独立可观测两项；两种抓取布局解码、未知 schema 在板卡访问前拒绝三项；原完整工作站探针准备三项、64 位解码两项、原 HDMI 探针两项、accepted 输入边界十项，合计 **22 项通过**。命令、日志和脚本哈希见 `out/workstation_hdmi_black_20261025_01/ddr_regressions_20261026_01/results.json`。行为模型不代替真实 PHY。生成物、位流、波形和抓取留在忽略的 `out/`，不加入源码。

诊断结束须恢复完整工作站。回退为原 `out/workstation_physical_20261025_c1102515/impl/pnr/custom_138k_integration.fs`，SHA256 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`；重新核对、只 SRAM 下载、独立读回，不操作 Flash。后续必要修正须查明训练原因，经离线／物理及实板检查后以新候选身份进入原生装配，不能改冻结 IP、跳过校准或强行放行显示。

**已完成恢复：2026-10-26 01:22:22～01:22:30。** 从 EA 切回原完整工作站 `C1102515`，下载前核对原 FS、物理清单、七项输入及原 stage 父清单；SRAM 操作 2 成功，随后独立操作 0 读回 ID `0x0001081B`、UserCode `0xC1102515`、Status `0x00022230`。当前板上不是隔离诊断。没有 SRAM 逐位读回，没有本轮 Flash 操作／断电，原 setup −0.568ns 和未发布状态保留；恢复不是黑屏修复或功能验收。证据 `out/workstation_deployment_20261025_c1102515/sram_restore_20261026_01/result.json`，SHA256 `81f23d0894693813f2c5ba8690f1b570cec0a4b142ae7077342196231c6eb784`。
