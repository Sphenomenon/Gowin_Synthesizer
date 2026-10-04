# 最新工作站与其他会话的 BSRAM 优化汇总（2026-10-01）

## 同步与结论

本次已执行 `git fetch origin` 和 `git pull --ff-only`。远端 `main` 与本地均为 `29fd4c305537533b1467754032a2cbba7c8a87a6`（2026-09-28 的 TF DDR 整合），pull 返回 `Already up to date.`，没有新提交进入本地。远端另一分支 `codex/post-p28-product-features` 的 HEAD 为 `dbc896bce344cb6a125719ce644cda53f03004b9`（2026-09-18 的 score guidance）。9 月 30 日的 CNN/CQT 存储优化仍在另一工作树的未提交源码和本地结果中。

本次整理后的完整工作站是 `results/build_20261001_140130_744482/Prj1`，顶层 `gw138k_push_workstation_top`。重新综合成功，输入哈希未变；**SYN BSRAM 228/340，SYN 余量 112**。默认 TF profile 为 WAV，已有 TF 直读、DDR 双 bank、矢量 voice 和 P10 效果链都实际展开。当前工作站未实例化 Basic Pitch。

本次没有将独立识别顶层并入工作站，也没有把它的 43 个 BSRAM 当作工作站资源占用或节省数。已汇总其优化方法、源码哈希、实测报告来源和接入边界；后续接入识别核需要单独实现共享 DDR、UART 模型装载和分析输入，不能直接覆盖另一会话的旧工作站 builder。

## 完整工作站的资源拆分

下表来自新结果的 `Prj1/impl/gwsynthesis/Prj1_syn_rsc.xml`，只相加顶层直接子树，避免子树与叶节点重复统计。

| 顶层子树 | 功能 | SYN BSRAM |
|---|---|---:|
| `u_usb_host` | USB-A Host、VexRiscv 固件存储与 FIFO | 34 |
| `u_push` | Push 事件及屏幕链路 | 1 |
| `u_managed` | 原合成器、矢量引擎、效果链、LED 曲谱及 recorder | 109 |
| `u_tf_audio` | TF FAT/SPI 直读、capture/playback FIFO、DDR DMA、WAV 解码及 CDC | 4 |
| `u_memory` | 当前共享 DDR 控制器 | 16 |
| `u_video` | HDMI、真实输出音频分析与渲染 | 48 |
| `u_boot_memory` | AE350 启动存储 | 16 |
| **合计** | 完整顶层 | **228** |

`u_managed` 的 109 = 音频工作站 104 + visual extensions 5。工作站的 104 = 原振荡器 17 + 矢量引擎 9 + 矢量控制事件 RAM 1 + P10 效果 76 + 顶层控制 ROM 1。P10 效果的 76 = delay 64 + chorus 4 + reverb 8。这里的子表是解释 109 的内部构成，不应再次加到 228。

TF 的 4 来自 capture/playback FIFO 各 2，文件流的大缓冲已迁至两个 64 MiB 的外部 DDR bank。`u_file_reader`、SPI/FAT 状态机、`u_dma`、`g_wav.u_wav` 都在综合层级中，浅 PCM CDC 使用分布式存储。默认 WAV 不会同时展开 MP3/FLAC。TF 输出仍使用现有 DAC 接管路径；它没有并入 P10 合成效果入口。未接入的 `rtl/sampler/` 和 Basic Pitch 不计入此构建。

## 另一会话优化的实际范围

来源工作树：`/home/sphenicidition/.codex/worktrees/0979/fpga`。最终证据是该工作树的 `usb_a/reports/BASIC_PITCH_43_BSRAM_DDR_BOARD_20260930.md` 与 `results/link_build_20260930_232850_811615/Prj1`。这是独立 `basic_pitch_tf_board_top`，包含 TF WAV → 重采样 → CQT → CNN → Viterbi，不包含当前工作站的 USB、HDMI、合成器和 P10 效果链。

| 独立识别实现 | 报告阶段 | BSRAM | 优化内容 |
|---|---|---:|---|
| 前一代 DDR 特征滑窗 | P&R，另一会话报告中的对照 | 201 | 部分特征使用 DDR |
| 全 CNN DDR | P&R | 139 | 权重、偏置、sigmoid、归一化输入、激活与后验迁 DDR，比 201 少 62 |
| CNN + CQT 全 DDR | SYN | 23 | 综合层级统计，尚未计算 P&R 的物理展开 |
| CNN + CQT 全 DDR | P&R | 43 | 信号窗、重采样和 CQT 复系数再迁 DDR，比 139 少 96 |

本次读取正式 routed netlist `Prj1.vo` 独立计数确认 43 = DDR 控制器 32 + Viterbi 9 + TF 字节 FIFO 2（27 SDPB、16 SDPX9B）。业务权重、特征、后验和 CQT 大表没有物理 BSRAM 实例。模型表包含 52,239 个 16-bit 字、104,478 字节，重新计算 little-endian 表 CRC32 为 `AF01A61B`，与另一会话报告一致。这是模型/算法系数，不是音频内容；本次只读取并计算，没有导入媒体。

优化源码要点：

- `basic_pitch_pcm_pipeline.sv` 的 `USE_ALL_DDR=1`、`USE_DDR_FRONT_COEFF=1`、`USE_DDR_CQT_COEFF=1` 选择完整迁移路径；独立正式顶层设置 43,844 点窗、172 帧和 9 个八度。
- `basic_pitch_nn_ddr.sv`、`basic_pitch_feature_ddr.sv`、`basic_pitch_normlog_ddr.sv` 将参数、特征、归一化与后验改成按需 DDR 访问。
- `basic_pitch_ddr_coeff_pair.sv` 与 `basic_pitch_cqt_engine.sv` 处理 DDR 复系数。必须保留 `S_MAC_REQ` 在信号请求被接受时锁存 `mac_kre/mac_kim` 的修复，否则单独核对两条数据流都正确，MAC 配对仍可能错误。
- 模型通过 UART 装载，写入后全量 DDR 回读 CRC 通过才允许分析；每次上电/重新配置后需要重新装载。当前工作站未带这条 UART 装载协议。

另一会话报告记录了 8,184 个原始累加值逐整数一致、六层指纹和最终 `bp_report=0022131F` 一致，以及约 436 秒的完整板测。**这些是其他会话的板测证据，本次没有重做板测或运行上传。** 这条路径也不能未经吞吐量论证就描述为工作站的实时分析功能。

## 汇总时已保留和应用的内容

1. 保留当前 main 的 TF DDR 环形流优化、完整地址表、8 voice 矢量引擎和既有工作站功能；未用另一分支的旧 TF BSRAM 播放路径覆盖它。
2. 新增 `tools/workstation_memory.py`，构建成功后强制解析完整顶层的层级资源；超出 340、层级统计不一致、缺少必要功能或 TF decoder 未展开均明确失败。输出每次构建自己的 `workstation_memory.json` 和 `.md`。
3. `build.py` 在综合成功、输入未变且资源审计通过后才更新 `LATEST_BUILD.txt`；新 `LATEST_WORKSTATION.json` 明确记录 build mode、统计阶段、TF profile、CNN 是否展开和硬件验证状态。`--prepare-only` 和失败构建不再覆盖 latest。
4. 本报告和配套 JSON 汇总其他工作树的资源报告、源码与模型哈希，绑定本次完整工作站构建和回归。未修改另一会话的工作树，也未替它提交。

## 为什么不能直接合并另一个 builder

另一工作树的 `build.py` 仍接入旧的 `tf_sd_audio_pcm_player` 和初期短窗识别配置；正式 43 块优化则在独立 `build_link.py` 中。它们不是当前 `main` TF DDR builder 的等价替换。

当前 DDR arbiter 的 owner 4 已属于 TF audio；另一分支把 owner 4 分给 music。直接覆盖会破坏响应归属及现有 TF 流。它的独立顶层还拥有 DDR 控制器和 UART，直接实例化将争用现有外设。识别核只应作为新的共享 DDR requester 接入，不能再实例化一份 board top。

后续真实合并识别功能需：分配独立 owner 并保持 scanout/TF 服务；登记 NN/bulk 的子区域（模型 `0x10100000`，CQT 信号窗 `0x10800000`，以及其它特征/DP 区域）；增加带 mask 的 16-bit DDR 访问与 CDC；隔离模型 UART 装载协议与现有控制 UART；明确 48 kHz 分析输入及背压策略；保留系数锁存修复；验证并发显示/TF/识别及完整工作站 SYN/P&R。这里只汇总边界，不把待实现功能写成已接入。

## 离线验证与最新指针

新构建：`results/build_20261001_140130_744482`。Gowin exit 0、`inputs_unchanged=true`。矢量 5 个独立 TB、编译器检查、P10 的精确干声/六种顺序/clear、P27 控制全部通过；另运行 TF DMA、DDR 地址表、DDR audio 仲裁、WAV 格式与 chunk parser 共 5 项无媒体文件回归，全部通过。没有执行会生成 MP3 文件的旧全量 TF runner。

资源工具负向检查拒绝了独立识别顶层、错误的子树统计、错误的 self count、341 个 BSRAM 超预算和缺失 TF reader。完整层级的 228 统计、decoder 与时钟表解析通过。

资源是 SYN 结果；历史完整工作站 253 是 P&R，独立识别 43 也是 P&R，不能跨阶段相减。SYN 时钟估计仍有不满足约束的域，例如音频要求 76.8 MHz 而估计 49.599 MHz；**尚未闭合时序、尚未完成新版本 P&R 或实体确认**。当前 latest 是完整功能的离线综合候选，并非板上当前版本。

最新指针在上述检查完成后更新。本次未运行 programmer、SRAM/Flash 操作、UserCode 分配或 `git commit`，没有创建音频文件。

详细机器记录：`reports/WORKSTATION_BSRAM_REVIEW_20261001.json`、新构建的 `workstation_memory.json` 与 `integration_checks/verification.json`。既有矢量引擎 9 月 30 日证据保留原始构建绑定，不改写成 10 月 1 日新构建。
