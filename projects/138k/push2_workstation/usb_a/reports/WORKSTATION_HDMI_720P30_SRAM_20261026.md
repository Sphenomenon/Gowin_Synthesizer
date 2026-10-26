# 720p30 完整工作站 B7：授权 SRAM 下载记录

## 用户授权再次下载：23:20

2026-10-26 用户明确要求“你再烧一遍进去”。重新核对相同 B7 的三份清单、八项输入和位流 SHA256，未重新构建或更换候选。保持 SRAM-only，使用排他锁；下载前 23:20:49 独立读取 FPGA `0x0001081B`、UserCode `0x00000000`，不据此猜测上一次配置如何变化。23:20:49.587–23:20:57.161 执行 operation 2，返回 0 且含 `Finished.`；23:20:57.162–23:20:57.312 再次独立读取，确认 FPGA `0x0001081B`、UserCode `0xC11026B7`。

此次日志保存在 `out/workstation_video720p30_20261026_b7/sram_deployment_20261026_02/`，`result.json` SHA256 `166971b778fe59ead96121649eb1ce855eb063e05015d84bfd146e81c3857de7`。没有 Flash 操作、复位／断电操作或 B2 预初始化；身份读取不等同于 SRAM 逐位校验。本次未重复 GAO 捕获，前一次 DDR／计数观察不能冒作本次重载后的状态；等待用户直接实屏测试，色块问题尚未宣称解决，严格时序和整机验收状态不变。

## 后续实屏反馈：界面未通过

用户随后反馈：“现在接入HDMI是色块刷新，没闪烁问题。完整工作站呢？”本轮仅再次执行只读身份读取，返回 0、`Finished.`，FPGA `0x0001081B`、UserCode `0xC11026B7`、状态 `0x00022230`；没有重新下载或写 Flash。

B7 的实际编译来源选择了完整工作站顶层和 `hdmi_display`，后者连接启用分析／共享数据的 `feedback_renderer`、DDR 帧写入、扫描输出和原生 DVI provider；未发现彩条测试源选择。该来源事实不能证明实屏像素内容正确。用户确认没有之前的闪烁，但“色块刷新”不等于工作站仪表界面显示通过，仍保持 `hardware_acceptance=false`。原三次 GAO 只有状态及截断计数，不能据此验证字体、波形、FFT、XY 或实际 RGB 内容；需要实屏照片区分预期面板区域和损坏像素，再定位渲染／DDR／扫描的数据链路，不能直接认定某一级已经损坏。

时间：2026-10-26，UTC+08:00。用户在获知 B7 为 720p30、最差 setup −0.705 ns、DDR 暖启动问题未解决、尚未上板后回复“下载吧”。本次仅执行 SRAM 下载和只读 JTAG 观察，不写 Flash，不操作复位或电源，不修改严格时序门禁，不等同于发布或整机验收。

## 输入身份

完整来源、配置、离线验证及 B5／B6 增量失败回退过程见 [720p30 实施报告](WORKSTATION_HDMI_720P30_20261026.md)。本次不重新综合或布局布线，也没有切换 accepted full83／timing85 的输入。

- 候选：`workstation-native-720p30-counter-observer-20261026-b7`，UserCode `0xC11026B7`，GAO `26B7`。
- 来源：`custom138k-native-integration-20261026-video720p30-a24`，完整工作站，1280×720p30；D 模式仍为独立集成工作。
- 位流：`out/workstation_video720p30_20261026_b7/impl/pnr/ao_0.fs`，SHA256 `3a6caa58621f75d3d1ca79e2a2d2c26b7fc44b2bfccf42991b5fe65201fb21fc`。
- `inputs.json` SHA256 `de5329bf96123dbaf4c2424d953ffc8626084265c6e8be83bcee6b4d8c00b396`。
- `physical_inputs.json` SHA256 `8c65491b6ae6ce2cd6e70e7178896b0cba3bbf645af878819dd8cd600c5bb341`。
- `implementation_verification.json` SHA256 `8cae3c1564d5d8a6d582a3a5177c8cf07f223ca0b50ab1fd9d4e0376eaaa8d17`。

下载前复核上述清单、位流及清单内全部八项输入哈希，包括业务 VG、物理约束、父级来源／综合审计和 GAO 配置。结构／资源检查通过；严格时序仍未闭合，setup −0.705 ns、hold +0.141 ns、recovery +2.928 ns、removal +0.250 ns。此次用户授权只用于该已披露候选的诊断性 SRAM 部署，不改变原离线清单或其 `release_ready=false` 状态。

## 实际操作

使用 `/tmp/gw138k_20261025.lock` 排他锁，设备 `GW5AST-138C`、cable-index 5、location 54、0.9 MHz。下载前后分别执行 programmer operation 0，下载仅使用 operation 2 和上述精确 FS。

| 阶段 | 时间 | 实测结果 |
|---|---|---|
| 下载前独立身份读取 | 22:54:23.905–22:54:24.096 | FPGA `0x0001081B`，UserCode `0xC1102515`；并非推定的旧 B3 |
| B7 SRAM 下载 | 22:54:24.096–22:54:32.136 | 返回 0，日志包含 `Finished.` |
| 下载后独立身份读取 | 22:54:32.136–22:54:32.286 | FPGA `0x0001081B`，UserCode `0xC11026B7` |

本次直接加载 B7，**未使用 B2 DDR 预初始化**。下载后 UserCode 读取不是 SRAM 全位流逐位回读，不应称为逐位校验。原位流、离线清单和历史记录均未改写。

操作日志与命令、时间、返回码位于 `out/workstation_video720p30_20261026_b7/sram_deployment_20261026_01/`。其中 `result.json` SHA256 `0d0da1b7f154f0c88703281d4288a3dc3a503531b3c5c9c585e603bd8bf62cab`；观察汇总 `final_status.json` SHA256 `31dffe43871d058fe09d65db34a9c283c605880d43036eba47577bf827087b13`。

## 只读板上观察

使用既有 `reports/hdmi_usb3_20261025/capture_ddr_jtag.py`，未修改捕获脚本或厂商程序。22:55:02–22:55:09 完成三次捕获，GAO OPEN／READ_RAM 成功；每次均在捕获前后独立核对 B7 身份。原始捕获位于候选目录的 `jtag_capture_20261026_01`、`02`、`03`。

| 捕获 | DDR 校准 | 视频 PLL 锁定 | 取数／仲裁／共享加载故障 | vblank 低 2 位 | 完成渲染帧低 2 位 | 欠载低 8 位 |
|---|---|---|---|---|---|---|
| 01 | 是 | 是 | 否 | 0 | 0 | 0 |
| 02 | 是 | 是 | 否 | 3 | 2 | 0 |
| 03 | 是 | 是 | 否 | 3 | 3 | 0 |

三次均已释放复位。`status_summary.json` SHA256 依次为 `700762d431599ac42cd1584896ca2b3d93a4ada2082f4c71be2f42f1c5364689`、`4a4bce9bf01587c69e61c3272c41f5c5319ee63828f4e19d1371aacaa224bee0`、`0582255ddbe29c78687f29b9343f52846fcd706214f9ef1ff99c33d53e5900a1`。

相邻观察中 vblank／渲染计数有变化，表明这些计数在推进；每次窗口为 1024 个 50 MHz 采样点，不是刷新率测量。低位计数存在回卷，跨时钟快照不是原子一致的；三次欠载低 8 位均为零，不能据此证明绝对累计欠载为零或长时间稳定。该观察配置不直接给出完整 BIST 标志，不能冒称完整 BIST 已验证。

## 剩余验证与回退

本次直接加载的 DDR 校准成功，不等于暖启动通用问题已修复；未断电验证，也没有 Flash 部署。720p 实屏图像、闪烁改善、长时间运行、音频及 Push／25K／BLE 的完整整机验收仍待完成。当前记录为授权 SRAM 部署与有限只读观察，不是 `hardware_acceptance` 或 `release_ready`。

需要回退时，保留既有 B3 位流 `out/official_ddr_ab_20261026_01/c11026b3/impl/pnr/ao_0.fs`，SHA256 `a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c`；回退仍需单独授权。既有 B3 暖启动依赖和闪烁限制沿用原记录，本次没有执行回退。
