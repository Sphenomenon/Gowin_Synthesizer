# 工作站 BSRAM 审计（2026-10-04）

## 结论

1. **"235 → 279 飙了 44 块" 是统计口径混用，不是真实增量。** 235 是综合（SYN）阶段的 18Kb 块当量，279 是布局布线（P&R）后的物理原语数；两者单位映射不同，任何时候都不能跨阶段相减。10 月 3–4 日的热插拔 + 整首曲谱工作期间，P&R BSRAM 全程稳定在 **279/340**（0x61 到 0x76 每个 P&R 报告均为同一数值），相对 0x52 **净增 0 块**。
2. **CNN 的 DDR 管理没有与 workstation 分离。** 全设计只有一份 DDR 控制器（`u_memory`，32 个物理原语）和一份命令仲裁器（`gw138k_ddr_arbiter`）。CNN（Basic Pitch）以 owner 5（music）客户端接入，TF 音频 DMA 以 owner 4（audio）客户端接入，不存在第二套控制器或第二套仲裁。
3. 本次任务对 BSRAM 的全部实际影响：相对 10-02 LATEST 构建 **+1 个 SDPB**（`u_tf_audio/u_path/u_file_reader/name_ram`，Push 歌单显示歌名所需，10-04 选曲功能）。0x64 与 0x76 的布线网表 BSRAM 原语逐实例一致。
4. 剩余可优空间见文末"如果将来真要降 BSRAM"；**本次没有改动任何 RTL**，当前板载 0x76 与其验收状态不受影响。

## 逐版本对照（P&R 报告 `Prj1.rpt.txt` + 综合层级）

| 日期 | 构建（results/） | 功能节点 | SYN BSRAM | P&R BSRAM | 网表原语（RAM 类） |
|---|---|---|---:|---:|---:|
| 09-21 | build_20260921_210521 | CNN 接入前的完整工作站 | — | 253/340 | （无 .vo 存档） |
| 10-02 | build_20261002_172816 | Basic Pitch 并入工作站（LATEST_WORKSTATION 指针） | 234 | 278/340 | 236 |
| 10-02 | song_guide_52 | TF 播放入口接 CNN 曲谱指引（0x52 起，板上血统） | 235 | 279/340 | 237 |
| 10-03 | song_guide_hotplug61–64 | TF 热插拔 0x61→0x64 | 235 | 279/340 | 237 |
| 10-03/04 | song_guide_full65–76 | 整首曲谱续窗 0x65→0x76 | 235 | 279/340 | 237 |

会话记录里 0x61–0x64 反复出现的"综合 BSRAM 235"与整首曲谱记录里的"PNR BSRAM 279"指向同一批构建的两个阶段，把它们排成一列就产生了 +44 的错觉。P&R 的 279 = SDPB 218 + SDPX9B 19 + pROM 33 + pROMX9 9（pROM 为 AE350 启动 ROM，SYN 层级计为 u_boot_memory 16 块当量）。

## 物理原语分布（0x76 布线网表 `Prj1.vo`，全部原语类型，单一口径）

2026-10-04 修订：下表为**全部原语类型**（SDPB/SDPX9B/pROM/pROMX9）按层级前缀的完整统计，合计 279 与 P&R 报告一致。此前的版本混用了综合块当量与原语数（例如 u_memory 报 16 块当量、实为 32 个原语；合成器/视频/启动三处 pROM 未单列），曾被误读为"有 85 块下落不明"。

| 子树 | 原语数 | 明细 |
|---|---:|---|
| `u_managed/u_audio` | 122 | delay_stage 64、reverb 8、chorus 4、引擎 slot/envelope 15、u_extensions 10、合成器 pROM 25（sine_interp 6、step/音色/矢量/弯音表 19） |
| `u_video` | 58 | renderer 36（含 9 个字体 pROMX9）、scanout 16、data_reader 6 |
| `u_usb_host` | 36 | USB 端点 RAM 32 + VexRiscv 程序存储 4 |
| `u_memory/u_ddr3` | 32 | 共享 DDR3 控制器（16 SDPB + 16 SDPX9B），**全设计唯一** |
| `u_boot_memory` | 16 | AE350 启动镜像（8 pROM + 8 RAM） |
| `u_music/u_basic_pitch` | 9 | Viterbi 工作内存（prev_score/score/emission/cur_note/cur_onset/path_mem），9-30 优化后基线，权重/特征/后验在 DDR |
| `u_tf_audio/u_path` | 5 | capture/playback FIFO + 文件流 |
| `u_push/events` | 1 | Push 事件 RAM |
| **合计** | **279** | SDPB 218 + SDPX9B 19 + pROM 33 + pROMX9 9 |

## CNN 的 DDR 访问路径（为什么它不是"分离的管理"）

- 仲裁与控制器：`usb_a/rtl/display_data/gw138k_ddr_arbiter.sv`（owner 0–5：BIST/显示、扫描、CPU、writer、audio=TF、music=CNN）+ `u_memory` 内唯一 DDR3 IP。
- CNN 客户端：`usb_a/rtl/music/basic_pitch_workstation_link.sv` —— 50 MHz 分析域发出 16 位内存请求 → `music_async_fifo` 跨时钟 → `basic_pitch_ddr_command_buffer`（0x76 加的单项寄存器缓冲，切断 FIFO 读指针被仲裁 ready 回馈的组合环）→ `basic_pitch_ddr16_port` 发起 256 位 DDR 突发 → 读响应经第二个异步 FIFO 返回。
- TF 客户端：`usb_a/rtl/tf_audio/tf_audio_ddr_path.v`（DMA 环形流）→ `usb_a/rtl/display_data/tf_audio_ddr_command_buffer.sv`（0x66 加的同类寄存器缓冲，切断 TF DMA 计数路径的组合穿越）。
- 两个 command buffer 都是**寄存器级时序修复，不占 BSRAM**；各自位于不同客户端到同一仲裁器的路上，不是重复的"DDR 管理"。
- CNN 模型权重（104,478 字节）经 UART 上传至 DDR、回读 CRC 校验后才允许分析，不占任何片上 BSRAM。

## 本次任务 BSRAM 层面的真实变化

`build_20261002_172816`（236 原语）与 `song_guide_full76`（237 原语）逐层级对比，唯一差异：

```
0 -> 1  u_tf_audio/u_path/u_file_reader/name_ram
```

即歌单菜单的歌名存储（`tf_sd_file_reader.v` 的文件名缓存），是 10-03/04 "Push 屏幕显示歌曲清单/选曲" 功能的必要代价。热插拔轮询、续窗队列、两个 command buffer 均未新增 BSRAM。

## 口径修复（本次落地的动作）

- `tools/workstation_memory.py`：
  - 新增 P&R 解析（`pnr_resources`），审计输出同时给出 SYN 与 P&R 两个数字及原语分解，`pnr_bsram` 超出 340 会硬失败；
  - 注记明确"SYN 与 P&R 单位映射不同，只能同阶段比较"；
  - REQUIRED 清单更新：`scope_dac_selection` 从 `u_scope_output`（0x52 起的血统中已不存在）改为 `u_tf_dac`（TF DAC 接管路径），与其余 15 项一起在 0x76 上验证通过。
- 新增 `tools/bsram_hierarchy_audit.py`：可复现本报告的全部数字（P&R 表 + 网表原语按层级计数 + SYN 顶层树）。
- 机器数据：`reports/WORKSTATION_BSRAM_AUDIT_20261004.json`（5 个关键构建的完整记录）。
- 0x76 构建目录已生成 `workstation_memory.json/.md`：`results/song_guide_full76_20261004_041101/`。

## 如果将来真要降 BSRAM（本次未做）

- `u_managed/u_audio` 的 97 块里，P10 **delay_stage 独占 64 块**，是全场最大单项。把延迟线迁到 DDR（类似 TF 环形流）理论可回收 ~60 块，但会改变 P10 效果的时序/延迟特性并挤占 DDR 带宽，需要单独的吞吐与音质论证，属于独立特性改造。
- `u_music/u_basic_pitch` 的 9 块是 9-30 CNN/CQT 全 DDR 优化后的剩余 Viterbi 工作集，已属该算法的最小驻留。
- 预算现状：340 − 279 = 61 块余量，不构成任何当前约束。

## 复现

```bash
cd migration/gw138k_audio/push2_workstation/usb_a
python3 tools/bsram_hierarchy_audit.py \
  results/build_20261002_172816_464963 \
  results/song_guide_52_20261002_232739_631505 \
  results/song_guide_hotplug64_20261003 \
  results/song_guide_full76_20261004_041101 \
  --out /tmp/bsram_check.json
python3 tools/workstation_memory.py results/song_guide_full76_20261004_041101 --mode full
```
