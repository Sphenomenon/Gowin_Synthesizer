# 2026-10-20：保留功能的资源优化

后续时序修复已完成：最终 T24 保持 **234/340 BSRAM**，完整 setup/hold/recovery/removal、CDC、PLL 与功能绑定全部通过；全局 setup +0.022 ns、hold +0.160 ns。使用 `python3 build.py --resource-rework --resource-timing --user-code C1102024`。最终记录见 [时序修复报告](RESOURCE_TIMING_REPAIR_20261020.md) 和 [候选清单](../RESOURCE_TIMING_CANDIDATE.json)。下文的资源初版结果和未闭合时序表作为历史证据保留。全部候选均未烧录。

本轮按“不要砍掉功能”的最新要求实施：保留五种现有音色、A/B/C、chorus、delay、曲谱下载、CNN 扒谱、跟奏指引、TF 录音/播放、示波器与 HDMI。未采用“分析与演奏互斥”的存储复用。USB CPU 的代码/数据 RAM 保持 64 KiB。TASLP 音源迁移不属于本轮实现，现有合成器继续工作。

新增构建入口 `python3 build.py --resource-rework`，生成完整离线候选；原 `--current-workstation` 的固定输入与验收边界继续保留。候选使用显式的活动 CNN 输入清单，并恢复原有 UART 诊断 CDC 补丁。每次构建都保存输入哈希、覆盖文件清单和构建来源，不改写板上版本记录。

## 分析频率与 CNN 分块

分析前端仍将正常音频转换为 **22,050 Hz 单声道**。每个分析窗口保存 44,100 个样本，覆盖约 2 秒；在 0、250、500、750、1000、1250、1500、1750 ms 取 8 个 CQT 时刻。使用 `22050/4` 的有理步长，在各 octave 分别换算位置，避免把步长粗略取整后累计漂移。44.1/48 kHz 音频接收与正常播放路径保留。

Viterbi 新增 `COARSE_GUIDANCE`：允许只有一个分析时刻的音高进入指引，包含最后一帧；仍保留休止、同音段去重、新 onset 重复音和输出背压。旧参数默认关闭该模式，继续使用原有稳定音高过滤规则。另以 2 帧、原 256 样本步长对照 all-DDR 与未分块缓存路径，六层哈希、写出量和最终音符同样一致。现有跟奏队列容量未缩小。

特征缓存改为按频率分块：每块计算 16 列，载入 20 列（包含卷积所需的左右 halo），保留最多 7 行、32 通道。最大有效数据为 `7×20×32=4480` 个 16-bit 字，使用 **5 个 1024×16 SDP**。依次处理 contour-reduce、note-out 和 onset-out；完整中间结果仍写 DDR，声部与音频效果不与分析共享这块 RAM。

完整 8 帧验证使用真实模型权重和确定性伪随机 PCM 输入，并非带标注的比赛曲目。对照结果：六层每一轮的哈希一致，最终 4 个指引音符顺序一致，各层写出量一致。未分块为 **179,197,503** 周期，分块为 **179,927,318** 周期，分块开销 **0.4073%**。DDR 读延迟为 3 周期并包含测试中的握手等待，详见 [逐层记录](resource_rework_20261020/cnn_tiles.log)。

该周期数包含测试中的窗口采集、前端和计算调度；按 50 MHz 换算约 3.6 秒。4 Hz 表示每秒音乐的分析时刻密度，不表示每 250 ms 已完成一次实时整网推理。原 172 帧和新 8 帧的整机速度比尚未实测，不能直接把帧数比作为整机加速比。

4 Hz 会改变原模型的时间感受野和短音覆盖率。上述等价性验证证明的是“相同 4 Hz 特征输入下，分块没有改变 CNN 结果”。它不证明新分析密度与原稠密分析的识别准确率相同；比赛曲目的识别准确率和短音漏检率仍需用标注音频核验。

## 三个数据区的 SDP 映射

- 录音包 FIFO：保留 256 个 96-bit 包，包括完整序号和左右声道，拆为 3 个逻辑 32-bit SDP；原有满队列丢包计数和碰撞前递保留。
- LED 曲谱：保留 256 条 64-bit cue，含完整 32-bit 绝对采样时间和 32-bit 灯光掩码，拆为 2 个逻辑 32-bit SDP。
- 视频扫描：保留 1920 像素两行 ping-pong 缓存、双时钟、epoch/tag 校验和超时处理，重排为 4 个原生 16-bit SDP。每个 256-bit DDR 回包分四拍写入，8 个请求信用限制已发未落盘数量，回包 FIFO 使用分布式 RAM；像素端每拍仍读一个完整 RGB565 像素，输出延迟不变。

Gowin 实际布局布线会把 32-bit SDPB 拆成两个 16-bit 物理块。因此，录音 FIFO 和曲谱保留完整精度与原吞吐，实际仍分别占 6、4 块，不能把逻辑实例数当作节省。视频改为原生 16-bit 重排后，单独布局布线确认由 16 块降至 4 块。

公共包装器显式实例化 GW5A `SDPB`。16/32-bit 模式的低 ADA 位是字节写使能，分别置为 `0011` / `01111`，读地址保持字对齐。已使用本机 Gowin 官方 GW5A 原语再次验证，未只依赖行为 RAM 模型。Icarus 13 和 Verilator 的仿真分支、显式 generate 作用域均已覆盖。

录音与曲谱和不可变旧实现逐周期对照；视频使用分别回包的 DDR 队列，核对相同像素时序、颜色和同步信号。验证包含随机背压、连续回包、失响应超时，以及 100 MHz DDR / 148.5 MHz 像素的实际时钟比例，额外固定 64 个 DDR 时钟的返回延迟；共检查 37,367 个录音包、143 次满队列丢包、639 次 cue、67,200 个非黑像素和 4,208 次 DDR 请求。特征缓存还逐字验证 30,240 个值和 17,424 次变延迟 DDR 读取，覆盖三个层类型、五个银行、首尾频率和时间 halo。

## 空间混响

用固定三维房间的一阶镜像声源早反射，加四路 Hadamard FDN 晚期混响，替换旧双 comb。房间为 6×5×3 m，源位置为 (2,1.7,1.2) m，监听位置为 (3.6,3,1.3) m，双耳间距 0.18 m。六个墙面各产生左右反射，路径差换算为 12 个延迟。晚期四路长度为 1429、1789、1999、2131 个 48 kHz 样本，含低通阻尼与 7/8 反馈。

这是几何早反射加 FDN 的空间混响，采用固定房间预设；没有三维网格波动方程求解，也没有 HRTF。房间编译脚本为 `tools/generate_room_preset.py`，结果保存在 `rtl/audio/spatial_room_preset.svh/json`。

新混响保留 Q1.31 运算、饱和、clip、开关增益渐变、旁路后台状态维护和清除中断。Chorus 是独立模块，仍可与 delay、空间混响同时使用，保留全部六种效果顺序和八种开关组合。

混响单帧处理 **80 周期**；完整效果链测试最大 **105/1600 周期**。106,434 帧左右声道与独立定点参考逐位一致，包含满幅、清除、关闭渐变及干声旁路。反馈与尾声合成的加法分级藏在早反射读取时隙中，保持相同数值与 80 周期延迟；初始化计数到最长延迟 2131 后饱和。单模块实际布局布线为 102.002 MHz（目标 76.8 MHz），内部 setup/hold 均无负端点；这不替代整机检查。完整效果链以真实双时钟 delay DDR DMA 验证 12,417 帧，未出现 underrun/overflow。

冲激测试中，反向积分能量在 −5..−25 dB 区间拟合得到约 **0.987 秒 RT60**；湿声左右相关系数约 **0.00489**，两秒尾部末 100 ms 峰值为 241 Q1.31（导出的 16-bit WAV 中低于一个量化单位）。这提供了立体声扩散与衰减的客观检查，听感仍需在实际耳机/扬声器上核验。[双声道冲激 WAV](resource_rework_20261020/room_impulse_stereo.wav)。

另外，以相同 0.5 FS 冲激和已稳定的 25% wet 增益，直接运行旧、新两套 RTL，得到 [对比图](resource_rework_20261020/reverb_comparison.png) 和 [客观指标](resource_rework_20261020/reverb_comparison.json)。新方案更早出现与房间几何对应的反射，晚期回声分布更密；旧双 comb 的重复峰更突出。两者湿声响度并未归一化，图中的幅度差也是实际算法差异，不能仅凭更长的衰减就判定主观音质更好。

新混响用两个 16-bit 半字存储每个完整 32-bit 样本，低/高半字按时隙读写，不截断音频。另用未修改的 Gowin 原语验证 4,132 次完整 32-bit 读回，覆盖所有五个 RAM 银行、跨 511/512 边界、随机重写和清除中断。原生 16-bit 组织经 Gowin 布局布线确认需要 **20 个物理 BSRAM**；旧混响占 8 个，单独增加 12 块。此次资源节省来自 CNN 和数据区映射；空间混响用于改善效果，不把它计为节省来源。

## 复现与证据

```sh
# 完整候选：综合、布局布线、位流、资源与时序/CDC/PLL审计；不烧录
python3 build.py --resource-rework --user-code C1102004
# 本次保留的 route0 配置（默认新入口使用 route1）
python3 tools/build_resource_rework.py --flow all --route-option 0 --user-code C1102004
# 仅准备 / 仅综合
python3 build.py --resource-rework --prepare-only
python3 build.py --resource-rework --synthesis-only

python3 sim/resource_rework/run_storage_equivalence.py --vendor
python3 sim/resource_rework/run_feature_cache.py --vendor
python3 sim/resource_rework/run_coarse_guidance.py
python3 sim/resource_rework/run_banked_store.py
python3 sim/resource_rework/run_spatial_reverb.py
python3 sim/resource_rework/run_effect_chain.py
python3 sim/resource_rework/run_reverb_comparison.py
python3 sim/resource_rework/run_cnn_tiles.py
# 独立物理占用和模块内部 setup/hold；不代表整机时序
python3 sim/resource_rework/run_reverb_timing.py
python3 sim/resource_rework/run_video_timing.py
# 旧参数：all-DDR 与未分块 cache 的相同输入对照
python3 sim/music/run_bp_config_ab.py --frames 2 --win-len 2048 --ddr-latency 3
```

回归与波形数据见 [验证目录](resource_rework_20261020/)。最终候选已通过 `sim/scope_vec/run_current.py <build>` 的 18 项回归，包含其 TF 16 项子套件、旧 DDR delay 等价和 DP/delay 地址隔离。结果见 [整机验证](resource_rework_20261020/workstation_regression.json)。

原始 201 等综合数与旧 262 的布线数使用不同口径，不据此计算节省。下面的最终资源和时序结论以相同阶段的实际工具输出为准。

<!-- FINAL_RESOURCE_AUDIT_BEGIN -->

## 最终资源核对

比较基准：`timing_p27_uart_cdc_route1_20261018_142516_456857`。新候选：`resource_rework_final_route0_20261020_041042`。两者均使用完整工作站顶层。

| 同口径资源 | 旧 | 新 | 变化 |
|---|---:|---:|---:|
| SYN BSRAM | 217 | 197 | -20 |
| PNR 物理 BSRAM / 340 | 262 | 234 | -28 |
| 剩余物理 BSRAM | 78 | 106 | +28 |
| PNR Logic | 77097 | 80167 | +3070 |
| PNR Register | 43450 | 45499 | +2049 |
| PNR CLS | 54862 | 56275 | +1413 |
| PNR DSP | 157.5 | 155.5 | -2 |

物理 BSRAM 净减少 **28 块（10.69%）**。下面按互不重叠的叶节点核对，既不重复累加父子层级，也不以综合网表数代替物理数。

| 物理 BSRAM 子系统 | 旧 | 新 | 变化 |
|---|---:|---:|---:|
| CNN feature cache | 32 | 5 | -27 |
| Viterbi | 9 | 8 | -1 |
| Recorder packets | 6 | 6 | +0 |
| LED score cues | 4 | 4 | +0 |
| Video scanout | 16 | 4 | -12 |
| Reverb | 8 | 20 | +12 |
| Chorus | 4 | 4 | +0 |
| Other retained RAM | 183 | 183 | +0 |

完整工具报告、物理网表和文件哈希见 [资源对照 JSON](resource_rework_20261020/resource_comparison.json)。所有本轮构建均未烧录；资源节省不等于时序闭合或板上验收。

## 完整布线的时序边界

| 时钟 | 目标 MHz | 实际 Fmax MHz | setup 负端点 | hold 负端点 |
|---|---:|---:|---:|---:|
| clk_50m | 50 | 50.066 | 0 | 0 |
| audio_76m8 | 76.8 | 69.383 | 302 | 0 |
| ddr_mem400 | 400 | 2598.78 | 0 | 0 |
| ddr_ui100 | 100 | 212.368 | 491 | 0 |
| video_pixel148 | 148.5 | 145.333 | 12 | 0 |
| cpu_bus50 | 50 | 73.076 | 0 | 0 |
| cpu_core100 | 100 | 1020.54 | 0 | 0 |
| usb_48m | 48 | 45.207 | 3 | 0 |

完整 SYN/P&R/位流生成通过，物理网表和资源表一致，输入哈希无漂移。CDC、PLL 初始化审计通过。**整机时序尚未闭合**，本候选最差详细裕量为 **-1.392 ns**。单模块 Fmax 通过和功能仿真通过都不代表完整工作站已可稳定上板。

资源交换的代价需要保留：除 RAM 外，Logic、寄存器和 CLS 增加，DSP 减少。此轮保留完整功能与样本精度，没有通过删除音源、降低复音、压缩音频精度或让分析/演奏互斥来换 RAM。

旧 P27 基准自身也未闭合，最差裕量为 −0.018 ns；它和新候选均不能当作时序验收完成。路由选项会改变时序，最终以候选自己的完整报告为准。

证据：[功能/数值验证](resource_rework_20261020/verification.json)、[时序审计](resource_rework_20261020/workstation_timing.json)、[CDC](resource_rework_20261020/workstation_cdc.json)、[PLL](resource_rework_20261020/pll_init_audit.json)。本轮未烧录。

<!-- FINAL_RESOURCE_AUDIT_END -->

## 两种路由的完整对照

| 路由 | 最差裕量 ns | audio MHz / 76.8 | USB MHz / 48 | video MHz / 148.5 | setup 负端点总数 |
|---|---:|---:|---:|---:|---:|
| 0 | -1.392 | 69.383 | 45.207 | 145.333 | 808 |
| 1 | -1.573 | 68.520 | 47.472 | 142.008 | 444 |

两套工具流程均完整结束，均为 234/340 物理 BSRAM、hold 负端点为 0，CDC／PLL 通过。它们的 RTL 相同，只有路由 Tcl 选项不同；原有时钟目标未放宽。候选清单保留 route0，因为最差裕量和音频／视频 Fmax 较好；route1 的总负端点较少，USB Fmax 较好，全部证据一并归档。**两者都未闭合时序，均未烧录或切换板上版本。**

对照见 [路由审计 JSON](resource_rework_20261020/routing_comparison.json)。RAM、Logic、寄存器等数值为完整候选与 P27 的净差，不能把整机 Logic 增量单独归因于某个模块。
