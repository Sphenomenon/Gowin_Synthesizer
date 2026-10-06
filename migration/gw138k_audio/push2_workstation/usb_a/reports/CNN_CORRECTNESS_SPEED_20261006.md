# CNN 正确性与解析速度修复（2026-10-06，0x83）

**已确认 0x80 引入的地址冲突：delay ring 与 CNN Viterbi 回溯表同时使用 0x30000000。**
0x83 将 Basic Pitch 回溯表移到 0x30400000，保留 0x82 的分级缓存、运算与节拍。
仿真已复现旧地址覆写，并验证迁址后的隔离；TRAVLER 首窗 36 项与帧速率仍须实板验收。

## 根因证据

| 客户端 | 原物理 byte 地址范围 | 大小 |
|---|---|---:|
| 0x80 新增 P10 delay ring，DDR owner 6 | 0x30000000..0x3001FFFF | 128KiB |
| 既有 Basic Pitch 回溯表 | 0x30000000..0x30007797 | 172 × 89 × 2 = 30616 字节 |
| 0x83 Basic Pitch 回溯表 | 0x30400000..0x30407797 | 30616 字节 |

- `7437dda` 引入父地址表的 delay 分配；`rtl/music/basic_pitch_ddr_map.svh` 原有 BPTR
  分配未迁移。旧回溯表**全部处于 delay 写范围内**。
- owner/tag 路由正确只能保证事务送达，无法防止两个客户端使用同一物理范围。
- full82 暂存树 `legacy/rtl/audio/stereo_effects.sv` 每音频帧会维护未处理的效果历史；
  `serial_delay_effect_ddr.sv` 的 `wr_data_push` 不受 enabled_i 限制。
  **P10 关闭时仍有 delay 历史写流**，正常选歌也能覆写 CNN 回溯表。
- 孤立 CNN A/B 没有 delay 写流，因此逻辑等价可以 PASS，板上出谱仍回退。
  这属于交接“分级逻辑 / 硅时序”二分之外的第三种原因，且符合 0x79 正常、0x80 未重验
  36 项的血统事实。0x79 的历史证据在 `reports/fullsong_watch_20261004.log`：48kHz、
  count=36，次窗到 69。

## 最终改动与性能影响

- 仅改允许编辑的 `rtl/music/basic_pitch_ddr_map.svh`：
  `BP_DDR_BPTR_BYTE_BASE=0x30400000`，`BP_DDR_LAST_BYTE=0x304FFFFF`，并注明父池 delay 保留区。
- NOTE=0x301 / ONSET=0x302 / ANALYSIS=0x303 分配保持不变。
  全部 13 个 BP 的 1MiB 分区彼此分离并避开 delay ring，证据 `address_ranges.json`。
- DDR16 适配器将 byte 地址转原生 word 地址，新 BPTR 为 app_addr=0x0C100000，delay 为
  0x0C000000；父地址表注明两颗 4Gbit ×16 组成 1GiB，0x304 区位于有效 BULK 池内。
- **无新增 MAC/DP 周期、无新增 DDR 事务、无新 BSRAM。** 源码保持 0x82 的运算节拍；
  0x83 后续窗口实测约 57s/窗；同口径 CNN 帧循环平均 6.59 帧/s，0x82 原始日志重算
  为 6.55 帧/s，未见吞吐回退。交接中的 6.9 帧/s 是粗估值，基线约 480s/窗。
- 冻结文件的五项开工 SHA256 均未变化：delay_ddr 两文件、仲裁器、HDMI、父地址表。

## BSRAM 用量说明（2026-10-06 实板解析期间复核）

| 版本 | 路径 | P&R BSRAM | 相对 0x81 |
|---|---|---:|---:|
| 0x81 | 每个 MAC 的权重/激活逐词访问 DDR | 215/340 | — |
| 0x82 | DDR 存全量，BSRAM 缓存当前消费窗/权重 | 260/340 | +45 |
| 0x83 | 保留 0x82 缓存，只迁移回溯表地址 | 260/340 | +45 |

逐模块综合资源增量为 feature_ddr +32、weight_cache +8、plane_cache +2、
u_basic_pitch 内部缓冲 +3，总计 45；Viterbi 两版均为 6 块。full82/full83 各模块的
BSRAM 数完全一致，P&R 的 SDPB=199、SDPX9B=19、pROM=33、pROMX9=9 也完全一致。
260/340=76.47%，还剩 80 块。旧设计记录把 Viterbi 6 块列入增量，现已修正。
对比证据：`results/cnn_correctness83_20261006/bsram_comparison.json`，源为三个构建的
`impl/gwsynthesis/Prj1_syn_resource.html` 与 `impl/pnr/Prj1.rpt.txt`；综合表自身总数
与 P&R 口径不同，只用于模块增量，最终总数以 P&R 为准。

## 可复现验证与证据

证据根目录：`results/cnn_correctness83_20261006/`。

| 实验 | 结果 | 证据子目录 |
|---|---|---|
| 原 BP map + 持续 delay 写流，172 帧数学 oracle | 预期 FAIL，frame=1/state=0 的回溯指针已损坏 | ddr_isolation_reproducible/old_map.log |
| 新 BP map + 同样写流，Icarus 四态 oracle | PASS，172×89 的全部分数/指针、28 项出谱 | ddr_isolation_reproducible/new_map.log |
| 12 帧 CNN 双配置 + 真实量级 delay 写流 | PASS，逐 wave 六层哈希、六层写出数、两路出谱 3 项一致 | ab_12frames_ddr_isolation/ |
| guidance 最终版本 | playlist_hold、hotplug、三项 Viterbi 出谱 5/5 PASS | guidance_final/ |
| TF 音频 | 16/16 PASS，最终相关输入 SHA256 无变化 | out/tf_audio_20261006_195523_949026/ |
| 3 帧 CNN 双配置，Icarus 四态 + delay 写流（补充项） | 未完成，vvp 仿真时间停滞后停止 | ab_iverilog_time_stall/ |

172 帧 oracle 使用独立数学递推，逐状态检查 score/backpointer，同时运行片内与 DDR 历史。
覆盖静音、平分、可变 DDR 延迟、ready 等待和出谱背压。负对照只把 BPTR 改回旧地址，
证明测试确实能捕获该重叠；两种配置的全部输入 SHA256 一并保存。

复现命令：

```sh
python3 sim/music/run_bp_ddr_isolation.py
python3 sim/music/run_bp_config_ab.py --frames 12 --win-len 8192 --max-cycles 800000000
```

12 帧 A/B 约 328.85s，最终哈希（contour/reduce/notes/note_out/onset/onset_out）：
`e1e1c8e5 / 7539c275 / c2ca22ba / 92afdeec / 1ea6f727 / 5432e32a`。
与完全没有 delay 写流的参考相同；各层写出数：25344 / 3168 / 33792 / 1056 / 33792 / 1056。

## A/B 夹具修正与诊断边界

完整读取两份指定交接文档后按要求启动仿真，随后发现原夹具不能支持根因判断：
A→B 未切 run_a；DDR 索引应为 23 位却声明 22 位；区域解码仅用 [27:20]，使 0x300 与
0x100 混叠；B 沿用 A 的中间 DDR 结果；非活动 DUT 获得 EOF；stdout 被 runner 缓冲。
已修正以上问题、独立预载两次 DDR、负沿驱动 PCM、逐 wave 比较与写出覆盖计数。

runner 支持 Verilator 编译后端以加速同一 TB，默认本机用该后端；Icarus 后端上提声明
只生成 sim 副本，真实管线不改。非活动 DUT 仅在公共时钟低电平及复位时停钟切换，降低
Icarus 开销。仿真周期/unknown/失配显式报错，日志逐行持久化。

3 帧无竞争写流 A/B 已 PASS（六层写数 6336/792/8448/264/8448/264）；扩大 12 帧时
400M 总周期顶不足，原 A 跑完、B wave 0..10 一致后超限，**不是逻辑 FAIL**。
扩大到 800M 后完成，避免因测试上限错误转向。

前期曾根据 full82 可见的 `p_cnt→score RAM` −3.415ns 路径准备 DP 流水候选。
找到地址冲突后已恢复 Viterbi 的 full82 原始 SHA256，取消该候选的构建，**从未烧板**。
也未实施交接的 MAC 流水：其“每窗 +56ms”成本推算有误，实际约 56ms/帧、9.7s/172帧窗。
当前地址修复不增加卷积延迟；未据总 TNS 宣称硅时序是根因。

四态全管线补充复核在前两帧 contour 哈希匹配后，vvp 持续耗 CPU 而仿真时间停止推进。
SIGINT 报告当前 time=1092227450000 ticks（约 1092.227ms，进入 reduce 附近），现场已保存。
这项测试**未完成**，没有当作 PASS 或逻辑 FAIL；未为绕过模拟器问题修改真实 RTL。
全管线等价性依据 Verilator 的完整 A/B，关键回溯数据隔离另有 Icarus 四态正负对照。

## 构建、板级状态与剩余验收

- 开工 JSON 记录 0x82，但烧录记录 `../results/sram_20261006_163824_061544/after.log`
  证实板上 0x00000081；实读模型 E、score_count=0。权威 JSON 已同步。
- 0x81 的 1200s 采集从 19:43:52 开始，全程 CAPTURE/wave=0/score_count=0，未选歌计算。
  日志 `base81/dwell_base81.log` 仅为 idle 证据，**不能判定 TRAVLER 基线 PASS/FAIL**。
- 最终修复提交 `8bc80e9`；脚本 `tools/build_full_song_83_bp_ddr_isolation.py` 沿用 full82
  暂存树与 SHA256 断言，只替换 BP 分配头和 UserCode=00000083。
- 完整构建：`results/song_guide_full83_20261006_203125_607466/`，全流程成功（49m22s），
  `tool_result.json`: exit_code=0、inputs_unchanged=true；BSRAM **260/340**、DSP 160/298。
  暂存输入与 full82 逐文件对比**恰好两文件不同**（分配头、build.tcl）。
- 已烧板：`../results/sram_20261006_212129_384333/`，完整 `--from-code 0x00000081`，
  before/SRAM/after **全部通过**，板上 UserCode=0x00000083。成功即更新权威 JSON。
- 已重传模型：104478 字节、CRC32=AF01A61B，9.0s，**状态 E（DDR 回读 CRC 通过）**。
  输出记录 `fix83/model_upload.log`。
- 时序仍未闭合：50MHz Fmax 42.932MHz、TNS −378.941ns/217 端点；audio_76m8
  TNS −4114.110ns；ddr_ui100 TNS −2552.336ns。报告 `full83_timing.txt`。
  这不是新增硬件正确性证明，仍以实体首窗和帧速率验收兜底。
- 0x83 采集已于 21:23:09 启动，1200s，cwd=`results/cnn_correctness83_20261006/fix83/`，
  原始字落在 `dwell_fix83.log`；目前 CAPTURE/wave=0/score_count=0，等待选歌。
- 物理选 TRAVLER 需要用户面板操作。验收为**首窗 36 项 + 帧速率不回退**，记录窗耗时、
  首末音符以及可捕获的哈希。未完成前不宣告板级修复验收。

## 已选解析后的实板数据（21:54 接入，首窗记录仍待补齐）

- 上一次 21:23 的 1200s 采集已在选歌前结束，全部 idle，不能用于验收。
- 用户已选解析后，21:54:12 新开 `fix83_selected/dwell_fix83_selected.log` 持续采集。
  稳态字为 48kHz/model E，接入时累计已有 69 项；随后在 t=8.9/65.9/122.7s
  分别到 103/139/171 项，即三个后续窗增加 34/36/32 项，完成间隔 57.0/56.8s。
  全局首音符 bin=73；这些完整窗末音符为 49/94/96。
- 用同一方法重算：采样 wave=10..160，排除 CAPTURE/CQT/result_valid，单段跨越至少
  100 帧，对 stream_wave 和时间作最小二乘斜率。full82 原日志 21 段平均 6.5504 帧/s，
  full83 此次 3 段平均 6.5897 帧/s；当前数据没有显示帧速率回退。
  证据 `hardware_partial.json` 保存方法、逐段范围/斜率、原始日志路径与出谱阶跃。
- 接入前的 69 项不能反推“首窗 36 项”已验收。已请用户在持续采集期间重新启动
  TRAVLER，从计数清零开始补齐首窗；`hardware_tested` 保持 false，尚未签署完整验收。
