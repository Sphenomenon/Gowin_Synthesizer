# CNN 正确性与解析速度排查（2026-10-06，0x83 窗口）

目标：保留 0x82 分级缓存的解析速度，恢复 TRAVLER 首窗 36 项。交接结论均视为待验证假设。

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
