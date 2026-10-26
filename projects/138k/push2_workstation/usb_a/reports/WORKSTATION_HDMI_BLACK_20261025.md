# 完整工作站有信号但黑屏（2026-10-25）

2026-10-26 上午更新：[官方 DDR 同板 A/B](WORKSTATION_DDR_OFFICIAL_AB_20261026.md) 已证明原始官方逻辑可校准，补齐三个 DDR 专用资源位置后，隔离与完整工作站均通过校准/BIST。完整 B3 已于 10:40 留在 SRAM，前台帧有效、显示取数复位释放，仍有欠载历史标志，待用户确认实屏。下文为历史阶段记录，不作为最新部署状态。

2026-10-26 续查：E3 最终超时未下载，E4 缩减 GAO 后成功构建并完成 SRAM 抓取；完整工作站观测到 DDR 未校准、显示取数保持复位。隔离小工程进一步定位到 DDR `READ_CALIBRATION` 阶段，详见 [DDR 实测与候选身份](WORKSTATION_DDR_CALIBRATION_20261026.md)。下文为当时分阶段记录，不作为最新板上身份。

## 已知事实与范围

用户先确认 `C11025D5` 彩条正常出图、硬件问题已自行修复，随后要求恢复原完整工作站。19:55:05（UTC+08:00）下载并独立读回 `C1102515` 后，用户反馈“显示器现在能接收到信号，但是显示出来是黑屏”。这是完整工作站的新问题，不沿用此前“无信号”的结论，不假定用户硬件仍有故障，也不把彩条通过扩展为 DDR 或整机显示通过。

首次离线排查没有板上读取、串口控制、SRAM 下载、Flash 操作、综合或 P&R。随后用户授权的串口接收单独记录于末节，仍未再次读取 JTAG 身份；板上身份引用 19:55 的独立读回。−0.568 ns 建立裕量及其用户接受范围保持原样，本轮不以修改时钟或门禁解决黑屏。

## 实际消费的显示链路

核对对象是 `out/workstation_physical_20261025_c1102515/` 所绑定的 `out/workstation_integration_20261025_a23_v5/workstation/Prj1/`，而非未经核对的活动 RTL。父清单 SHA256 为 `88af98466644d04b5cd1b70d1e0695571530e3201abf6beb371f258d7dfb7863`；FS SHA256 仍为 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`。

已校验显示装配、DDR 平台／自检、渲染、取行、运行遥测及两份既有测试共 15 份暂存输入的清单哈希。D5 所复用的八份时钟、复位、光栅、编码和串行输出依赖与该整机暂存输入逐字相同；D5 的独立彩条顶层、一次自动重启及 GAO 并不等于整机装配相同。

整机 `src/video/hdmi_display.v` 有三处需要区分的黑屏条件：

- 第 64–77 行：光栅由视频复位单独释放，但显示数据通路还等待 `memory_reset_n`；DDR 平台的该复位又等待 PHY 校准完成。因此能有视频时序而仍没有可显示的数据。
- 第 100、175–220 行：渲染、共享显示数据和取行的使能为 `bist_done && !bist_failed && !fetch_fault && !arbiter_fault`。DDR 自检未完成或锁存失败都会阻止正常出帧；不能跳过自检来掩盖问题。共享数据写入器会独立完成三次初始化写入，不能仅凭 `shared_initialized` 门控认定启动死锁。
- 第 250–263 行：数据通路尚未释放时，明确发送带 DE／同步的黑色光栅。通路释放后，`src/video/video_ddr_scanout.v` 第 112–114 行也只显示具有当前 epoch／行号标签的取行数据，缺行输出黑色；取数故障会锁存，不能把旧行当新画面重放。

以上证明代码允许“有信号但黑屏”，不证明当前板卡一定卡在其中某一处。DDR 未校准、自检失败、首帧未发布及取行故障仍需运行数据区分。没有证据要求再次调整 HDMI 引脚、极性或 CEC。

## 最小下一步：读取既有遥测

现有整机不需要重建就会发送只读运行记录：默认 `debug_uart_tx` 选择运行遥测或音乐状态，115200 8N1。目标输出为 `U15`；FTDI B 通道是否实际连到此信号不能仅凭串口设备存在认定。应在用户明确允许后，只接收串口，不发送命令、不改 DTR／RTS 来复位板卡，不接 JTAG A 通道作 UART，也不重新下载镜像。

读取至少三条 CRC16/CCITT-FALSE 校验通过、序号递增的 `A138` 记录；CRC 对八个 32-bit 字的小端字节串计算，初值 `0xFFFF`。以下字下标从零开始，来自实际消费的 `src/push2/gw138k_push_performance_uart.sv` 与 `src/video/video_runtime_diagnostics.v`：

| 字段 | 含义与排查用途 |
|---|---|
| `word[0]` | 运行报告序号；先排除旧记录或重复记录 |
| `(word[1] >> 8) & 0xFF` | `memory_flags`：bit0 校准完成，bit1 BIST 完成，bit2 BIST 失败，bit3 前台帧有效，bit4 取行／仲裁／共享数据加载故障的合并标志，bit5 曾发生欠载，bit6 DDR PLL 锁定，bit7 视频 PLL 锁定 |
| `word[2]` | 音频采样累计计数；确认显示故障没有停止采样，不将其当作最终 HDMI 图像证明 |
| `(word[4] >> 8) & 0xFF` | 视频标志：bit0 HPD，bit1 视频锁定，bit2 像素复位已释放，bit3 取行复位已释放，bit4 串行器复位仍在断言，bit5 时钟测量有效 |
| `word[4] >> 16` | 有效测量窗口内的 1024 像素时钟块数；无效窗口的零值不能认定时钟停止 |
| `word[5]` | 垂直消隐累计计数；观察光栅是否继续运行 |
| `word[6]` | 完成渲染帧累计计数；与前台有效位一起区分首帧生产和取行问题 |
| `word[7]` | 欠载累计计数；需要比较增量，非零历史值不等于当前仍在欠载 |

判别顺序是校准／DDR 复位 → BIST → 首帧发布 → 取行／欠载。HPD 在当前设计中不门控视频，不以 HPD 为零直接解释黑屏。若串口没有字节或没有有效记录，应记录观测通道缺失，不能据此认定 DDR、CPU 或像素时钟失效。届时再提出复用现有整机综合网表、插入最小 GAO 的独立候选；任何新候选下载仍须单独授权，不能把离线通过视为下载许可。

## 离线验证与限制

直接编译上述已校验暂存源，运行既有两项回归：

- `tb_ddr3_bist` 通过：正常完整双遍、自检数据错误、读响应超时和命令超时均覆盖。它使用仿真存储，不证明物理 DDR 已通过。
- `tb_video_epoch_recovery` 通过：实际取数超时后持续黑色、256 帧 epoch 回绕不泄漏旧行、欠载继续计数、共同复位后恢复取数。它验证保护行为，不证明当前故障必须靠复位解决。

生成证据位于 `out/workstation_hdmi_black_20261025_01/verification.json`，SHA256 为 `fbe0c08a8692a94d1cb9bf652933dbb3e221ed148780606c4a5cc17c2359ccf3`。其中保留源哈希、D5 八项依赖比较、完整编译／运行命令与日志。`hardware_accessed=false`、`sram_programmed=false`、`flash_accessed=false`、`root_cause_confirmed=false`。未更改任何 RTL、冻结基线、原部署证据或位流；没有交付新候选，也没有需要执行的板上回退操作。

## 授权后的串口接收（20:56–20:57）

用户回复“抓取吧”，本次仅授权读取现有串口遥测，不授权发送控制、JTAG 操作、新镜像下载或 Flash 操作。2026-10-25 20:56:58 至 20:57:20（UTC+08:00），对 `/dev/serial/by-id/usb-FTDI_Dual_RS232-HS-if01-port0`（`/dev/ttyUSB1`）按 115200 8N1 独占接收 22.025 秒，含前两秒预热；USB 属性核对为 `0403:6010`、interface `01`，没有占用 JTAG A 通道。

结果：**接收 0 字节、有效 A138 记录 0 条、其他有效记录 0 条，发送 0 字节。** 没有得到 DDR 校准、自检、渲染帧数或欠载的板上读数，黑屏根因仍未确认。不能把串口静默转换为 DDR／CPU／视频时钟故障结论，也没有必要无边界地重复同一接收。

接收使用只读 tty 文件描述符，没有 UART 写入或 DTR／RTS 控制 ioctl，没有发送复位命令。打开后与关闭前的可读 DTR／RTS 状态均为高；没有对打开瞬间或实际物理复位线路作波形测量，不能声称已观测所有边沿。原串口设置接收前为 9600，结束后恢复原设置，但保留 `HUPCL` 清零以避免关闭 tty 时主动挂断。没有综合、P&R、JTAG 访问、SRAM 下载或 Flash 操作，串口已释放。

观测通道仍有明确缺口：当前物理 CST 的 `debug_uart_tx` 是 FPGA 球位 **U15**，不是底板的 U15 器件位号。提供的底板网表中，U13 十针下载口的可见信号为 TCK／TDI／TDO／TMS，没有调试 UART TX／RX 连接证据；FTDI B 在操作系统中出现不能证明它已经接到该球位。此前 [引脚核对](CUSTOM_BOARD_PIN_AUDIT_20261021.md) 也已要求另核对 U15／V14 与核心板调试口或外接 3.3V 串口适配器，不沿用旧 NEO Dock 串口桥假设。尚未确认用户是否存在网表之外的外接 UART 线，故不将通道缺口认定为当前黑屏的软件根因。

机器证据位于 `out/workstation_hdmi_black_20261025_01/uart_capture_20261025_01/`：

- `authorization.json` SHA256：`f8bfd59245bb6ad31b588442af503fbaf4049ef2f2a8fa33c6970d5d2e61f0ad`，绑定本次授权及上次完整工作站 SRAM 独立读回证据。
- `result.json` SHA256：`c039ad6fcb991bd72f002f146bf2e5f548ced0f13d5d1edebc0c740152f9affc`，保存观测起止时间、串口设置、字节／记录计数、线状态读取和限制。`board_identity_read_this_capture=false`、`sram_programmed=false`、`flash_accessed=false`、`root_cause_confirmed=false`。
- `a138.log` 为空，SHA256：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；没有保存 PCM 音频流。

后续可选两条路径：用户确认 U15 至 UART 接收端的实际连接后再次被动接收，或另行授权下载整机最小 GAO 观测候选。后一条优先复用已校验综合网表、仅运行后端实现，不全量重综合；新 SRAM 候选须有独立身份、输入／输出哈希和独立下载后读回。下节仅完成离线准备，没有执行后端或下载。

## 接屏状态确认与整机 GAO 离线准备

用户说明上述串口接收时没有插 HDMI，随后在接屏状态下明确反馈“当前是有信号但黑屏”。这是有线连接下的黑屏复现，不是新的位流验收；串口输出并不依赖 HPD，不能把此前零字节归因于没有插 HDMI，也未因此重复空串口接收。

新增临时实验入口 `hdmi_usb3_20261025/prepare_workstation_jtag.py`，只准备明确绑定 `C1102515` 的整机观测配置，不替换 D5 彩条入口或任何生产 profile。输出目录为 `out/workstation_hdmi_jtag_20261025_c11025e1/`，预留独立 UserCode `C11025E1`，GAO 配置 ID 为 `0x25E1`；这些身份只存在于准备文件，未写入板卡，也没有独立硬件 ID 读取。

- 原物理输入清单 SHA256、七项输入及回退 FS 全部重校验，缺失或变化立即失败。复用原 `ad6b4b197b415bec56bbae78b8fac16a429fcb3741617299d6e65f0faff8a5ff` 网表，不复制完整工程或添加另一套业务 RTL。
- CST、SDC 逐字不变。Tcl 只通过两个唯一锚点增加 GAO、改变 UserCode，保留 `run pnr` 和原后端选项；无 `run all`、`run syn`、`open_project` 或下载命令。这是网表复用，不称为工具原生增量综合。
- 单核、50 MHz `clk_50m_d`、1024 点、64 个观测位：公共复位、八位同步内存状态、六位同步视频标志、16 位像素时钟块测量、vblank／渲染／欠载各低八位、实际 UART TX、音频同步标志、已同步音频 Gray 计数低四位及 UART 状态机。所有观测点在实际综合网表中逐声明／位范围核对，不用 RTL 名称猜测已经被优化掉的网络。
- 这些是既有观测通路的信号，没有反馈到音频或显示使能。低位计数有回绕，且一次约 20 微秒的窗口不能证明 60 Hz 出帧在增长；应在后续获准下载后进行间隔捕获，Gray 低位不得当二进制样本总数使用。
- 新增三项准备回归与原 D5 两项回归共五项通过：绑定原网表／约束、仅后端 Tcl、64 位 GAO 配置、输出防覆盖、父身份变化拒绝、时钟／观测位缺失拒绝。没有改动既有 D5 准备文件。

准备清单 `inputs.json` SHA256 为 `311aab1a5c1403e7ab46cdd7bf7ae23b394052b5aa1bb514e11e7cc01a4be918`，绑定新准备脚本和五项实际输入的哈希。此刻 `implementation_started=false`、`implementation_verified=false`、`deployment_authorized=false`、`hardware_tested=false`、`sram_programmed=false`、`flash_programmed=false`、`release_ready=false`；未运行 Gowin 后端、未产生新 FS，物理资源／时序／CDC／PLL 与最终 GAO 路由均尚未验证。原候选 −0.568 ns 的接受范围不自动转移到新观测候选。

当前板卡仍以原完整工作站的上次读回记录为准。后续实现、SRAM 切换和实际 JTAG 捕获须区分阶段，下载仍需单独授权；不写 Flash，不因离线准备成功自动操作板卡。回退保留原 `C1102515` FS，只有获准才可重新下载。该探针定位故障后退役，不成为长期工作站生产入口。

## 继续执行授权与后端重用（2026-10-25 晚间）

用户随后明确要求“运行，你自己找问题”，授权继续运行后端、下载临时 SRAM 观测候选并通过 JTAG 抓取内部状态；不授权 Flash 操作、断电重启或替换生产配置。以下记录接续前节的离线准备状态，不将旧准备清单中的 `implementation_started=false` 原地改写为新的执行证据。

重新扫描唯一的 WINUSB／位置 54 下载器并独立执行 programmer operation 0，读得器件 `0x0001081B`、UserCode `C1102515`、Status `0x00022020`，操作成功。结果保存在 E1 目录的 `sram_deployment_20261025_01/before_identity.json`；这不是 DDR 校准、PLL 锁定或 SRAM 逐位校验。该阶段未执行 operation 2，未改变板上位流。

| 观测候选 | 输入策略 | 本轮后端结果 |
|---|---|---|
| `C11025E1` | 原整机综合网表及 CST／SDC 不变，添加 64 位 GAO | 21:26:55 开始，22:06:55 到达 2400 秒上限；日志到达布线结束及 95% 时序分析，未导出 FS，不能下载 |
| `C11025E2` | 同一网表／约束／GAO，显式 `inc_pnr` 重用原 `C1102515` 的 `.p/.pr` | 21:45:58 开始，22:05:58 到达 1200 秒上限；停在布线阶段，未导出 FS，不能下载 |
| `C11025E3` | 同一网表／约束／GAO，显式 `inc_pnr` 重用 E1 已写出的布线缓存 | 22:12:17 开始，独立新目录运行，执行上限 5400 秒；完成与否以其 `build_result.json` 和实际导出物为准 |

E1、E2 均被各自启动器在上限后终止，仅终止对应进程组，保留失败日志和缓存。没有将 95% 进度或已有 `.pr` 当作成功实现。E2 的第一次准备因脚本漏导入 `shutil` 失败，在启动 Gowin 之前已修正；失败与恢复另记 `preparation_attempt_01.json`。本轮三条路径均复用原 `ad6b4b197b415bec56bbae78b8fac16a429fcb3741617299d6e65f0faff8a5ff` 网表，实际日志明确跳过整机 RTL 综合；GAO 插入器自己的小规模综合不等于重综合整机。

E2／E3 只在各自忽略输出目录进行有唯一锚点、源哈希校验的 Tcl 适配：改变 UserCode，并在唯一 `run pnr` 之前设置 `set_option -inc_pnr [file join $root reference.p]`。E3 从 E2 仅再替换唯一 UserCode 锚点；参考 `.p/.pr` 单独复制并纳入哈希，`.p` 来自 E1，SHA256 为 `3018a4ef626236d59a0a2b47472e20d78571b0d452d72bd2b9ab19c584b880f8`。不能把中断导出时保存的缓存当成已经完成的时序报告；E3 仍须重新产生并审计完整物理结果。E2 的实际 `impl/pnr/cmd.do` 已确认消费 `-inc_pnr`，E3 另行检查。这是增量布局布线，不称为原生增量综合。没有新增长期编号构建器或改写生产入口；故障定位后退役该实验。

各候选都有独立 `inputs.json`、补充 `physical_inputs.json`、授权记录及日志。输入清单 SHA256：E1 `311aab1a5c1403e7ab46cdd7bf7ae23b394052b5aa1bb514e11e7cc01a4be918`；E2 `3657d5cab6ae06406fee4c9ed1976a8963f9433369ee70f450c4835c04bba568`；E3 `b254a9dd8eca8b4bcd7bb797ec396d2ad1e058a2ec5b7c0ea43f177ad7c15b73`。新候选保持 GAO 配置 ID `0x25E1`，不把该配置值混同于新 UserCode 或硬件独立读回。CST／SDC、时钟频率、hold 修复、业务功能均未因实验被放宽或删除。

新增 `hdmi_usb3_20261025/decode_workstation_jtag.py` 对 64 位 CSV 的信号顺序、1024 点、连续索引及二进制取值进行严格验证，输出状态位和截断计数。两项解码回归通过，包含错误表头、非二进制和截断数据拒绝；另外五项准备回归通过。它仅为离线解码器，不能自行证明实时 READ_RAM 成功、当前位流身份、DDR 状态或黑屏根因。后续实测须保留 WINUSB 打开及 READ_RAM 的肯定应答、捕获前后独立 UserCode、CSV 和间隔捕获结果；旧 D5 彩条捕获不充当整机观测。

### 等待后端期间的补充仿真

针对实际消费的 stage，`tb_ddr_recovery_guard` 通过。旧 `tb_ddr_framebuffer` 首次自动库编译遗漏 `.sv` RAM 模型，显式补齐模型后在写请求保持断言失败；这个历史独立测试没有消费当前 HDMI 包装层已有的 `renderer_ready && shared_initialized && !write_req` 防护，也不包含当前的 P5 元数据协议，不能直接当作整机故障复现。未修改该旧测试、冻结 RTL 或现有包装层。另以既有 `sim/p11/tb_display_write_path.sv` 驱动实际 stage 的共享读写器和帧写入器，通过 365 次共享写入、365 次一致性回读、129600 次像素 beat 和 P5 提交；模型耗时 1609710 个 UI 周期，约 16.097 ms，确认元数据等待期间不会开始下一张 raster。它仍使用测试中的旧仲裁器与行为存储，不证明本次物理实现的 DDR PHY 或新队列正确。

此外，stage 的 `tb_video_runtime_diagnostics` 在每像素周期连续注入 vblank、压力跨越计数低半字回绕时触发 `pixel frame Gray changed more than one bit`，并非全套回归通过。该计数器仅用于观测，正常 vblank 并不连续每像素周期有效；尚无证据将此压力断言认定为本次启动黑屏根因，也没有因此改动计数器或掩盖失败。原始失败、缺依赖修正与集成测试通过分别保留于 `out/workstation_hdmi_black_20261025_01/extra_pipeline_regression_20261025_01/`、`extra_pipeline_regression_20261025_02/` 和 `integrated_write_regression_20261025_01/`。
