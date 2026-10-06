# CNN 正确性与解析速度排查（2026-10-06，0x83 窗口）

目标：保留 0x82 分级缓存的解析速度，恢复 TRAVLER 首窗 36 项。交接结论均视为待验证假设。

## 当前结论：确定的 DDR 地址重叠（20:29 更新）

0x80 的提交 `7437dda` 新增 delay ring，占用 `0x30000000..0x3001FFFF`；既有 Basic Pitch
回溯表仍从 `0x30000000` 开始。172 × 89 × 2 = **30616 字节**，旧回溯表的整个范围
`0x30000000..0x30007797` 被 delay ring 覆盖。owner 6 的正常写流会破坏历史指针；仲裁
tag/优先级本身的正确不能防止两个客户端分配同一片物理存储。

这也是交接的“缓存逻辑 / 硅时序”二分之外的第三种原因；孤立 CNN A/B 不包含 delay 写流，
因此可以 PASS，板上出谱仍回退。归属与“0x79→0x80 从未重跑 36 项”这一事实相吻合。

**0x83 最终候选只改 BP 地址分配**：在允许编辑的 `rtl/music/basic_pitch_ddr_map.svh` 内
将 BPTR 移到 `0x30400000` 独立 1MiB granule，LAST_BYTE 更新为 `0x304FFFFF`。
保留 NOTE=0x301 / ONSET=0x302 / ANALYSIS=0x303；父 BULK 池边界到 0x3FFFFFFF，当前
其他 RTL 无 0x304 占用。五个冻结文件不改。

Viterbi 已恢复为 full82 的原始 SHA256，撤回先前的流水候选，以使 0x83 保持 0x82 的
运算及节拍，只验证地址隔离的作用。旧构建 `song_guide_full83_20261006_195842_758915`
在布线阶段主动取消，**从未烧板**；Icarus 孤立 A/B 补充实验也随旧候选停下。

`run_bp_ddr_isolation.py` + `tb_viterbi_ddr_isolation.sv` 给出可复现实验：

- 旧 map + 父地址表定义的 delay ring 连续写流：**预期失败**，第二帧（frame=1）、
  state=0 回溯指针已被破坏，约 0.12s 即检出。
- 新 map + 同样写流：**PASS**，172 帧 × 89 状态的全部 score/backpointer 正确，
  片内与 DDR 历史出谱均 28 项；含 DDR 等待、变延迟、背压、平分与静音，约 12s。
- 证据 `results/cnn_correctness83_20261006/ddr_isolation_reproducible/`，含源码哈希及
  两种地址配置日志；这是四态 Icarus 测试，不依赖 Verilator 二态假设。

新脚本 `tools/build_full_song_83_bp_ddr_isolation.py` 沿用 full82 暂存树，SHA256 断言，
只替换音乐分配头和 UserCode=00000083。dry-run 通过，下一步完整构建与实板 36 项验收。

以下记录保留前期排查过程，时序候选已由上述地址修复取代。

## 开工状态

- 工作树 HEAD `c4ad063`，已有未跟踪交接文档和 `sim/music/`，已完整读取两份指定文档。
- 开工 JSON 记录 0x82，但 `../results/sram_20261006_163824_061544/result.json` 与
  `after.log` 证实 2026-10-06 16:38 已回烧 0x00000081；串口实读状态 E、score_count=0。
  已将权威 JSON 同步为板上 0x81，并保留 0x82 候选失败信息；下个 UserCode 保留 0x83。
- 0x81 采集于 19:43:52 启动，原始字落在
  `results/cnn_correctness83_20261006/base81/dwell_base81.log`；须由用户面板选 TRAVLER。

## 原 A/B 夹具的问题与修正

按指定命令启动后，静态检查发现以下问题，原进程中止，未据其输出下根因结论：

1. A 完成后未将 `run_a` 置 0，B 无法获 DDR 应答。
2. `{gmap, addr[19:1]}` 需要 23 位，原索引 22 位截断，CQT_SIGNAL 等区域发生别名。
3. `addr[27:20]` 丢了区域高位，DP `0x300...` 与 CNN `0x100...` 地址混叠；改用
   完整的 12 位 MiB 区域索引，覆盖 `0x100..108` 与 `0x300..303`。
4. A 的中间结果留在共享 DDR，B 非独立运行；两配置均重新清零并加载同一模型。
5. 非活动 DUT 仍能收到 pcm_end；改为仅活动 DUT 解除复位及获得输入/DDR握手。
6. PCM 激励在负边沿驱动以避开采样竞争；最后一个样本后再断言 EOF。
7. runner 原先 capture_output 吞掉心跳；改为逐行持久化输出，错误/周期超限返回失败。

新增每 streaming wave 的哈希比较（含 flush wave），以及六层写出覆盖计数，防止空跑 PASS。
仿真生成文件、日志归入被忽略的 `sim/music/gen/`，不修改真实管线的声明顺序。

## 已得到的证据

`timeout 5000 python3 sim/music/run_bp_config_ab.py`：**PASS**。
本机 Verilator 5.046 编译执行同一 TB，FRAME_LIMIT=3、WIN_LEN=2048、DDR_READ_CYCLES=1，
运行约 101.8 秒。A/B 六层哈希逐 wave 一致，出谱序列均 1 项；各层写出计数：
6336 / 792 / 8448 / 264 / 8448 / 264。

六层最终哈希（contour / reduce / notes / note_out / onset / onset_out）：
`b3deebef / 08dd57ba / 878ffdf1 / 3f1526dd / 950b5941 / 33f3e140`。
证据与源文件/模型 SHA256：`results/cnn_correctness83_20261006/ab_3frames_pre_fix/`。

3 帧 PASS 仅说明已覆盖范围内配置等价，不能证明整窗无逻辑缺陷，更不能直接证明硅故障。
正在扩展到 12 帧、8192 PCM 窗以覆盖 7 行缓存和后验环的回卷。

## 时序与性能推断的修正

从 full82 P&R 时序报告提取的文本：
`results/cnn_correctness83_20261006/full82_timing.txt`。
全局最差 50 条 setup 路径中可见的 BP 50MHz 同钟失败，是
`u_viterbi/p_cnt -> score RAM DI`，slack -3.415 / -3.381 ns，组合数据延迟约 23.4 ns。
该报告没有列出 conv2d MAC 路径，不能从总 TNS 推定 MAC 是根因。

交接中的 MAC 流水成本“每窗 +56ms”不正确：2.82M MAC / 50MHz = **56.4ms/帧**，
172 帧约 **9.7s/窗**。在仍需实测正确性的阶段，优先评估 Viterbi 已知长路径流水，
其额外每前驱 2 周期约 54ms/172帧窗，可保留卷积吞吐。

板级验收尚未完成，当前不宣告修复或确认根因。冻结文件已记录开工 SHA256，禁止编辑。

## 已撤回的时序候选与前期回归

- Viterbi 新增 `S_DP_READ` / `S_DP_CAND` 两态：寄存前驱分数和 transition，下一拍寄存
  candidate，再执行原 best/score/backpointer 更新。保持 32 位算术、严格大于的平分选择、
  前驱顺序、输出协议。卷积、权重缓存、特征缓存、前端参数未改。
- `sim/music/tb_viterbi_dp_pipeline.sv` 的独立数学 oracle 以 172 帧 × 89 状态核对每个
  score 和 backpointer；片内/外置历史同时测试，外置 DDR 有可变应答延迟与 ready 等待，
  出谱带背压；静音、平分以及最终两路出谱序列覆盖。Icarus 四态仿真 **PASS**（28.7s）。
- playlist_hold / tf_hotplug_probe / viterbi_score / viterbi_score_ddr /
  viterbi_first_alignment **5/5 PASS**；证据 `results/cnn_correctness83_20261006/guidance/`。
- 12 帧原实现 A 已完整跑完（6 层哈希 `e1e1c8e5 / 7539c275 / c2ca22ba / 92afdeec /
  1ea6f727 / 5432e32a`，出谱 3 项）；B wave 0..10 均一致，随后撞到 400M 总周期顶。
  这是 **测试超限，不是逻辑 FAIL**；保存于 `ab_12frames_pre_fix_cycle_limit/`。
  修复后 12 帧以 800M 周期上限继续完整验证。
- 新构建脚本 `tools/build_full_song_83_bp_dp_pipeline.py` 使用 full82 暂存树，断言
  三个相关音乐 RTL 的基线 SHA256、五个冻结文件的 live/staged SHA256，并只替换
  Viterbi 与 UserCode 00000083。dry-run 已通过。

TF 音频回归 **16/16 PASS**：`out/tf_audio_20261006_195523_949026/`。
候选源码提交 `e1f50f7`，完整构建 `results/song_guide_full83_20261006_195842_758915/` 已启动。
0x81 采集至 19:59 仍 CAPTURE，尚未选歌，因此没有有效 TRAVLER 基线验收数据。

修复后的 12 帧 A/B **完整 PASS**（800M 上限，实际约 419M 周期，469.25s）：
wave 0..19 与最终六层哈希均一致；各层写出 25344 / 3168 / 33792 / 1056 / 33792 / 1056，
两路出谱序列均 3 项。最终六层哈希与修复前原 A 的完整结果也完全相同。
证据 `results/cnn_correctness83_20261006/ab_12frames_dp_pipeline/`。
继续用 Icarus 四态后端复核 3 帧夹具，以检查 Verilator 二态执行可能掩盖的未初始化值。

0x81 的 1200 秒采集已结束：全部 CAPTURE / wave=0 / score_count=0，未出现选歌计算。
这份 idle 日志只证实模型 E 与遥测活跃，**不能作为 TRAVLER 基线 PASS/FAIL**。
0x79 参考记录 `reports/fullsong_watch_20261004.log` 实际存在，包含 48kHz、count=36/69 的
解码遥测；36 项口径有历史证据，但 0x80/0x81 至今仍缺重跑验收。

Icarus 四态复核最初约 25K 周期/s；为避免非活动 DUT 每拍运行复位与组合逻辑，
仿真 TB 对非活动 DUT 停钟，`run_a` 只在公共时钟低电平且全局复位时切换。
重新启动后约 43K 周期/s。新增哈希/音符 unknown 检查，避免两路同时 X 被当成相等。
旧的约 120ms 仿真片段归档到 `ab_iverilog_partial_before_clock_gating/`，不是失败证据。
