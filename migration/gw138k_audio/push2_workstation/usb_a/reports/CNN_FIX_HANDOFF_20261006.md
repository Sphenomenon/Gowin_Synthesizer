# CNN 吞吐窗口交接（2026-10-06，写给接手 agent）

## 一句话现状

0x82 分级缓存修复**性能达标**（TRAVLER 每窗 480s→56s，8.4×），但**出谱正确性回退**
（TRAVLER 首窗 1 项 vs 参考 36 项）。根因二选一：分级缓存路径的逻辑 bug，或新 50MHz
读路径的硅级时序失败。决定性判别实验（双配置仿真 A/B）已写好、已编译通过、
运行被超时打断——接手后第一步就是把它跑完。

## 已完成并提交（HEAD = c4ad063）

- `0687fb3` 0x81 测量镜像：管线 8 档每状态驻留计数器，B138 NN 字低 16 位 =
  `{page[1:0], cycles[24:11]}`（2048cy/LSB，0.5s 窗轮换，页 0=CQT/1=NORM/2=CONTOUR/
  3=REDUCE+NOTES/4=NOTE_OUT+ONSET/5=ONSET_OUT+GLUE/6=DP/7=OTHER）；`state=(nn>>26)&0x3f`
  解码不变。已烧板验证。工具 `tools/capture_bp_dwell.py`。
- `2402e37` 0x82 修复：`workstation_link` 参数改 `USE_ALL_DDR(0)` +
  `USE_EXTERNAL_WEIGHTS/FEATURES(1)`；管线 `g_ddr_weights` 分支换
  `basic_pitch_uart_model_loader`；新增 `USE_DDR_SIGNAL` 参数（CQT 信号留 DDR）。
  P&R BSRAM 260/340。已烧板。
- `1d888f7` 报告 `reports/CNN_STAGED_CACHE_FIX_20261005.md` + JSON；`54a1131`
  采集工具修复；`c4ad063` 回归记录（16/16 TF + playlist_hold + hotplug 全绿）。
- 未提交：`usb_a/sim/music/`（A/B 仿真 TB + runner）。

## 关键背景事实（简报有两处错，别踩）

1. 0x80/0x81 板级配置是 `USE_ALL_DDR(1'b1)`：权重/激活每个 MAC 经 `basic_pitch_nn_ddr`
   逐词走 16-bit DDR 事务（`ddr16_port` 一次 BL8 只取 1 半字），简报说的
   `basic_pitch_weight_cache`/S_LOAD_WEIGHT 路径当时**未实例化**。
2. 六头合计 16625 词（简报 16328 漏 onset_out 297），但与瓶颈无关。
3. 每帧 MAC（流式 1 输出行/层）：contour 1.977M、onset 563K、notes 138K、
   note_out 59K、reduce 53K、onset_out 26K ≈ **2.82M MAC/帧**；实测基线 2.7s/帧
   ≈ 2 事务/MAC × ~24cy/事务，模型闭合。
4. 0x82 分级路径的流式对齐已人工核对过：plane_cache 两次填充（contour
   center=stream_wave；onset center=stream_wave-8）；feature_ddr 三种装载
   (kind0=contour 5 行、kind1=notes 7 行、kind2=onset 3 行) 与消费窗吻合；
   reduce_mem 7 行环供 notes；note_post/onset_post 环供 onset_out ch0 与 DP 进料；
   各 AFTER_* 的 w≥2/5/8/9 门槛保证行号非负。
5. **0x79→0x80 血统从没重跑过 TRAVLER 36 项**（0x80 板测只做了 P10 听感）——
   回退也可能在 0x80 引入（delay-DDR 仲裁 owner 6），不一定在 0x82。

## 板上 0x82 TRAVLER 实测数据（证据在 `results/cnn_fix82_travler_ab/`）

- 每窗 56s（基线 480s）：CQT ~28s + CNN ~25s + 收尾。CNN 分项与设计预测精确吻合
  （contour ~14s/窗 ≈ 82ms/帧预测 79；WAIT_FEATURE ~3s ≈ 预测 17ms/帧；
  WAIT_WEIGHT ~1s ≈ 7.3ms/帧）→ **机器在按设计全速跑**。
- 出谱：score_count 阶跃 1,2,5,7,8,12,13,15,17（每窗 +1~4），音符值合法
  （bin 20-75），first_note=41 恒定（全局首音符）。采样率 48kHz 确认是 TRAVLER
  （用户确认过）。原始字里 5 条杂散行是 runtime 串口污染（ASCII "CPU1"），非复位。
- 采集没抓到 result_valid 哈希页（1-4 项排水太快，0.7s 采样错过）。

## 第一步：跑完双配置仿真 A/B（决定性，无需用户/板子）

```
cd usb_a && timeout 5000 python3 sim/music/run_bp_config_ab.py
```

- 原理：同一 TB 里 `dut_a`（USE_ALL_DDR=1，0x80/0x81 已验收数据通路）与 `dut_b`
  （0x82 参数）喂相同 LFSR PCM + 共享行为级 DDR（blob 预载 + UART loader 层次化
  强制 DONE），比对 6×32bit 层哈希与出谱序列。FRAME_LIMIT=3、WIN_LEN=2048、
  DDR 应答 1 周期。iverilog 单遍编译吃不下管线的先用后声明——runner 会自动生成
  声明上提的仿真副本到 `sim/music/gen/`（别手改 gen/）。
- **PASS** → 逻辑等价 → 问题在硅（新 50MHz BSRAM 读路径，0x82 的 clk_50m TNS
  -435ns/298 端点；0x80 是 -186/126）。修复方案：conv2d 的 MAC 操作数加一级流水
  （新增 S_REQ2 态把 w_data_i/xval 先寄存一拍再进 S_IC，3cy/MAC，每窗 +~56ms
  无关痛痒，且两配置算术不变）→ 0x83 构建 → 板上验 36 项。
- **FAIL** → 分级路径逻辑 bug。定位：把 TB 里哈希快照改成每帧一拍
  （stream_wave 变化处抓 dut_a/dut_b 的 debug_layer_hashes_o），先找第一帧分歧，
  再看 6 层哪一层先错，对照该层的装载/寻址（上文第 4 条）缩小。
- 预计 30-60 分钟（vvp ~82K cy/s；TB 内部硬顶 400M 周期，上轮撞顶是
  WIN_LEN=43844 的 capture+重采样成本，已缩到 2048）。
- 陷阱：vvp 重定向到文件时 stdout 块缓冲，心跳要等 `$fflush`（已加）或跑完才可见。

## 第二步（与第一步并行可选）：0x81 板上 A/B 基线

板子**现在是 0x81**（`sram_20261006_163824_061544`，16:38 烧录），模型已传（状态 E，
16:40）。需要用户在面板再选一次 TRAVLER：
`python3 usb_a/tools/capture_bp_dwell.py --seconds 1200 --label base81`
（原始字写到 cwd 的 `dwell_base81.log`，注意 cwd！）。预期首窗 8 分钟出 36 项。
- 36 项 → 基线干净，回退确属 0x82 → 与仿真结果互相印证。
- 不是 36 → 回退在 0x79→0x80 血统（优先查 delay-DDR owner 6 对 BP DDR 延迟/正确性的
  影响），这会改变修复方向！

## 硬约束与操作规程

- UserCode 下一个用 **0x83**；构建脚本模式：`tools/build_full_song_82_bp_staged_cache.py`
  （staged-copy + 哈希断言 + user_code 补丁），构建基线用 full81/full82 暂存树，
  构建约 55 分钟（`~/.local/bin/gw_sh`，PRJ1_FLOW=all）。
- 烧板：`python3 scripts/program_sram.py <fs> --from-code 0x00000081`（**8 位完整格式**）。
- 每次烧板后必须重传模型：`python3 usb_a/tools/upload_cnn_ddr_uart.py --port /dev/ttyUSB1`
  （等状态 E，~9s）。SRAM 重配置会清 DDR。
- 选歌 TRAVLER 是面板物理按键，只有用户能做；歌是 48kHz。
- 冻结文件（delay_ddr/、gw138k_ddr_arbiter.sv、hdmi_display.v、ddr_address_map.vh）
  不许编辑；冻结 hash 断言在构建脚本里。改动限 rtl/music/ 与 push top 音乐链路。
- 看门狗/歌单保持/原地恢复参数不许回退；TF 回归 16 项 + guidance TB 保持绿。
- 验收口径：帧速率对比 0.37 帧/s（0x82 已达成 6.9）；**TRAVLER 首窗 36 项**
  （当前缺口）；层哈希作回归参考。
- `usb_a/LATEST_WORKSTATION.json` 是跨窗口权威：开工重读、烧板即更、随提交更新。
