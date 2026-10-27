# 独立 HDMI 实板复现与屏闪计数观察

日期：2026-10-28，UTC+08。范围仅为独立原生 UI、现有 DDR 管理、HDMI；不代表完整工作站验收。

## 无信号与恢复

- 用户反馈接入 HDMI 后无信号。00:03 独立读取器件 ID `0001081B`、UserCode `C1102515`、状态码 `00022020`，已不是前次下载的 D5 `C11027D5`。
- 这个事实能说明板上配置身份变化，不能仅据此确定发生过断电、Flash 重载、其他下载或是哪一项导致。未把它归因为 DDR 资源不足，也未修改 Flash。
- 00:04:27～00:04:35 按已有用户 SRAM 授权重新下载原 D5，独立读回 `C11027D5`；FS SHA256 `ecec68500569c14a24ff1d3558c1ebeb05403e5ba0e5e688d964fad326a5762b`。
- 下载证据：`out/hdmi_isolation_20261027_d5/sram_deployment_20261028_000427/result.json`。下载前的额外身份日志：同候选的 `no_signal_20261028_0004/identity_before.log`。
- 用户确认重新可见屏幕，内容、波形和效果卡片动态正常，但仍有屏闪。该观察不涉及实际 DAC 音频功能，独立版未实例化音频业务或其他完整工作站业务。

00:06:17 的 GAO 1024 个样本：`memory_flags=EB`，`video_flags=2F`；DDR 校准、BIST、前帧有效、DDR/video PLL lock 均为真，BIST 错误与读数/仲裁故障为假，HPD 为真，像素及扫描复位均释放，serializer 未处于复位。欠载历史标志置位，不能据此判断是否持续欠载。

采样证据：`out/hdmi_isolation_20261027_d5/no_signal_20261028_0004/status_summary.json`，CSV SHA256 `28fcb6d6ca9ca07229e1c680ebb8d653ce50873a97cd6e78bfe207f1cd1b99ea`。

## 计数观察候选 D1

身份：`custom138k-hdmi-isolation-C11028D1`，源集政策同 D5，动态输入不变。38 个实现源文件中仅探针 `rtl/display_data/workstation_hdmi_isolation.sv` 的观察寄存器打包改变；有效 CST、SDC、DDR 地址图、动态输入配置与 D5 逐字节相同。未修改 UI、扫描器或 DDR 调度。

GAO 从 16 bit 扩为 64 bit，保留原状态，并增加完整 32-bit 欠载行计数、渲染帧计数低 8 bit、垂直帧计数低 8 bit。所有值来自已有 50 MHz 域诊断寄存器，不另建业务状态。布局见 `rtl/display_data/README_HDMI_ISOLATION.md`。

- 构建输出：`out/hdmi_isolation_20261028_d1/`；`inputs.json` 记录输入哈希，`build_result.json` 记录输出哈希与工具结果。
- 综合与布局布线：239.658366 秒，工具返回 0。主设计 BSRAM 78 块、GAO 4 块，共 82 块；主设计 CLS 12,720，REG 13,135。
- FS：`impl/pnr/ao_0.fs`，SHA256 `c317ef331c78cc7adfe9000f9b4249174e491fd090853ece64716d2d32aab1c7`；GAO ID `28D1`。
- 全局最小 setup `+0.158 ns`、hold `-0.194 ns`、recovery `+2.158 ns`、removal `+0.344 ns`。严格时序仍未关闭，不是发布版本。
- 已有 DDR 配置/复位、PLL_INIT、serializer 启动和 routed CDC 检查 `errors=[]`；审计整体仍因负 hold 为失败，未绕过该结果。
- 独立功能回归 8 项通过；新增观察布局和解码的定向回归 2 项通过。实际原生队列扫描回归：稳定/换帧 0 欠载；迟到行恢复计数 3；迟到 epoch 恢复计数 7，均符合测试预期。

只读采样入口为 `reports/workstation_hdmi_flicker_20261028/capture.py`，复用既有 WINUSB/GAO recipe，不负责下载。它要求新的输出目录，并在两种既有板锁下核验下载身份、GAO 配置哈希、CSV 布局和采样后的独立身份。

## D1 SRAM 与持续欠载证据

00:16:01 起，仅 SRAM 下载 D1，并独立读回 `C11028D1`。没有 Flash 操作、断电或 SRAM 逐位回读。证据为 `out/hdmi_isolation_20261028_d1/sram_deployment_20261028_001601/result.json`。

随后三次各 1024 样本窗口均保持 DDR 校准、BIST 完成、前帧有效和视频/DDR PLL lock，故障位未置位，HPD 为真，像素/扫描/serializer 复位状态正常。窗口末计数如下；两个帧计数仅展示低 8 bit，存在正常回卷。

| 采样完成时间 | 欠载行，32 bit | 渲染帧 mod256 | 视频帧 mod256 |
|---|---:|---:|---:|
| 00:16:12.284 | 60,753 | 54 | 118 |
| 00:16:14.925 | 154,998 | 138 | 29 |
| 00:16:17.612 | 244,324 | 216 | 187 |

两个间隔欠载分别增加 94,245、89,326 行；视频帧分别前进 167、158（mod256），渲染帧分别前进 84、78。**这是持续扫描欠载，不只是启动留下的历史标志。** 它支持优先检查扫描行预取与内存服务间隔，但尚不证明唯一根因，不能把此表当作 TMDS、DDR 数据完整性或全部短暂复位均正常的证明。

原始 CSV、GAO 通信和独立身份日志位于 `out/hdmi_isolation_20261028_d1/counters_01/{1,2,3}/`，聚合证据为同目录 `result.json`。D1 画面是否与 D5 有同样视觉屏闪尚未获得用户再次确认。

## 判定边界与回退

独立工程仍能复现屏闪，说明 CNN、USB、BLE 的业务竞争不是出现屏闪的必要条件；尚不能排除显示自身访存、帧发布、DDR 运行数据错误、时钟/复位或物理输出时序。

不得把历史欠载标志、单个瞬间状态或“工具返回成功”当成故障根因。后续依据连续采样的欠载增量和帧计数推进定位。

独立 UI 回退是原 D5 `C11027D5`，路径与 SHA256 见前文；整机已知可见画面回退仍为 B3 `C11026B3`，见 `WORKSTATION_HDMI_ISOLATION_20261027.md`。二者均有已知时序/屏闪缺口。本轮不写 Flash、不做物理断电，也不宣称整机修复完成。
