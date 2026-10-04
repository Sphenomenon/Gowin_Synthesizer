# Basic Pitch 并入完整 workstation：实板结果（2026-10-02）

## 结论与边界

已把独立验证过的 172 帧 Basic Pitch 链路并入 `gw138k_push_workstation_top`。板上 `0x4D` 镜像完成 TF WAV 解码 → PCM → 重采样/CQT → CNN → Viterbi；模型 DDR 回读 CRC 通过，最终报告 `B138 0022131F`（MIDI 49、frame 2），六层 UART 可观测的哈希高 29 位均与独立镜像基线一致。完整运行耗时 516.6 秒。当前 SRAM 板上恢复为 `0x4D`，Flash 未写入。

**时序没有闭合。** 这是一版有实体功能证据的诊断镜像，不是可声明为所有工作站功能稳定的时序合格发布版。`0x4F` 尝试修正跨域遥测路径后，两次上板模型 DDR 回读 CRC 都进入 `F`，因此没有替代 `0x4D`。仓库源码已恢复到与 `0x4D` 的综合输入一致；重新 `--prepare-only` 对比 584 个输入，仅 `firmware/boot.elf` 链接元数据哈希不同，综合用的 `boot.mem` 与其它输入完全一致。

## 实际接入

- `build.py` 把 `rtl/music` 加入完整 workstation 工程，没有再实例化独立识别顶层或第二个 DDR 控制器。TF 解码器继续使用 owner 4，识别核使用新增 owner 5，共享现有 DDR3 controller。
- TF 解码器的 50 MHz PCM16、采样率和格式通过 `tf_workstation_audio_bridge.v` 引出。模型装载成功后 TF 从文件开头重启，识别核对解码器施加背压，逐样本完整接收 48 kHz PCM。计算阶段 TF 播放跟随识别速度变慢，识别完成后解除背压。
- 模型和 CQT 大表、信号窗、激活、后验保留在 DDR。模型区域 `0x10100000`，CQT 信号窗 `0x10800000`，未与 TF 两个 64 MiB bank 冲突。16 位写入使用 DDR byte mask；仲裁响应 tag 独立路由。
- PC UART 在模型状态到 `E` 前交给模型装载器，同时屏蔽 workstation 原 PC 命令输入，以免 `BPN1` 模型字节被解释为音频控制指令。Push/USB 控制仍有独立路径。模型装载前原 PC UART 控制暂不可用，这是当前合并的操作限制。
- debug UART 保留 workstation 原遥测，在识别报告发送期间输出 `B138` 帧；主机按帧头分辨。每页哈希在该协议中只传高 29 位，低 3 位未由这次实板遥测验证。

## 冲突、修复和失败记录

| 问题 | 证据与处理 |
|---|---|
| 两个 `uart_rx` 同名、接口不同 | 初次完整综合报 `EX3990` 找不到端口；模型接收器改名为 `basic_pitch_uart_rx` 后综合通过。 |
| 旧 PLL 位置约束引用了不存在的网名 | 首次 P&R 报 `CT1135`；依据本次综合网表改为 `pll_reset_s1`，P&R 可完成。 |
| TF/显示请求饿死模型 DDR 写入 | 板上 `0x4C` 上传 104,486 字节后状态长期停 `5`；仲裁加入 owner 5 轮转，`0x4D` 模型回读状态到 `E`。持续 TF 与持续显示请求的仲裁仿真通过。 |
| 识别完成信号只有一个周期 | 改用锁存后的 `seen_done` 解除 TF 背压，避免播放只恢复一个周期。 |
| `0x4E` / `0x4F` 的跨域遥测修改 | `0x4E` 时序报告指向音频域 `format_sync` 到 50 MHz 识别域；`0x4F` 去掉此路径后两次 DDR CRC 均失败，状态 `F`。未把该版标记为可用，源码和板子均恢复 `0x4D`。不能仅凭现有证据断言 CRC 失败的唯一原因。 |

## 验证证据

| 项目 | 结果 |
|---|---|
| 完整工作站 Gowin SYN | `234/340` BSRAM；比接入前的 `228` 增 6，新增 BSRAM 在 Viterbi。CNN/CQT 大存储未占 BSRAM。 |
| 完整工作站 Gowin P&R | `278/340` BSRAM，`153.5/298` DSP；镜像 UserCode `0x4D`，SHA-256 `46b0f0c0fd73108ba76cd3284ba4898bac82c144e2eeddedfd339bc9de279d52`。 |
| DDR 仲裁仿真 | TF、扫描、显示、CPU、识别 tag 与 mask 检查通过；持续 TF/显示请求时识别不会饿死。 |
| SRAM 下载 | 写前、下载、写后 UserCode 检查均通过；恢复记录为 `sram_20261002_000319_963132/result.json`。 |
| 模型上传 | 52,239 个 16 位字，104,478 字节，主机 CRC32 `AF01A61B`；恢复 `0x4D` 后板端回读状态 `E`。 |
| 172 帧识别 | 六层哈希高 29 位依次为 `D1FFF498`、`C603CCE8`、`1E39D540`、`56F7DA28`、`D5816B28`、`CF7EF3A8`（低 3 位被串口页号占用）；最终 `0022131F`，耗时 516.6 秒。 |

验收日志：`reports/workstation_basic_pitch_upload_4D_20261001.log`、`reports/workstation_basic_pitch_capture_4D_20261001.log`、`reports/workstation_basic_pitch_upload_4D_restored_20261002.log`。失败日志：`reports/workstation_basic_pitch_upload_20261001.log`（`0x4C` 状态 `5`）、`reports/workstation_basic_pitch_upload_4F_20261001.log` 和 `reports/workstation_basic_pitch_upload_4F_retry_20261001.log`（状态 `F`）。完整构建为 `results/build_20261001_222442_709782`，其 `workstation_memory.json`、`Prj1/impl/pnr/Prj1.rpt.txt`、`Prj1/impl/pnr/Prj1_tr_content.html` 保存原始资源与时序报告。

## 未达到的验收项

`0x4D` P&R 有 2672 个 setup 违例端点、92 个 hold 违例端点。Fmax：50 MHz 域 46.515 MHz、音频 76.8 MHz 域 60.094 MHz、DDR 100 MHz 域 73.250 MHz、USB 48 MHz 域 43.223 MHz；视频像素 148.5 MHz 域 176.696 MHz。成功的一次识别不能替代时序闭合。Push、USB、HDMI、合成器和 P10 效果在完整顶层均有综合层级，但这次没有逐项实体回归，也没有验证 MP3/FLAC profile。当前直接分析输入只支持 48 kHz WAV profile；其它采样率不声明可识别。

下一步应先缩短 TF DMA / DDR 仲裁 / 显示共享路径并完成所有时钟域的 P&R 时序闭合，再以新镜像重复模型 CRC、六层哈希、最终音符及工作站各功能实体回归。任何新镜像都不能沿用 `0x4D` 的板测结论。
