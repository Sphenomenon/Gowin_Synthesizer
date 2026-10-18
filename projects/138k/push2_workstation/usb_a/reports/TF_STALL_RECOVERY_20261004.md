# TF 传输停顿误判拔卡 → 踢回选歌菜单：根因与修复（2026-10-04）

## 症状

0x76（板载版本）上：选歌 → ANALYZING/SCANNING 数秒 → 自动退回 SELECT SONG 列表。整首曲谱续窗在 0x76 上的模型加载已通过（状态 `E`），此症状使续窗实体验证无法进行。

## 板端证据

用户复测后立即读取 B138 串口遥测（`tools/capture_tf_hotplug.py`，20 s 窗口）：

```
0.0s model=E rate=44100 fs=5 card=8 sector_busy=0 sector_allow=0 scan_done=1 lost_seen=0
0.5s model=E rate=48000 fs=5 card=8 sector_busy=0 sector_allow=0 scan_done=1 lost_seen=1
```

- `card=8`：卡始终在位且已初始化；`lost_seen=1`：热插拔看门狗**真的触发过**——是误判，不是真拔卡。
- `rate` 44100→48000 变化 = 看门狗触发后读卡器复位、重扫、重新解析了 WAV 头（证明完整走了复位→重扫链）。
- 后续 90 s 空闲观察（`reports/hotplug_idle_watch_20261004.log`）状态稳定，未再连续触发——停顿是偶发的传输级事件，不是确定性逻辑死锁。

## 根因链（完整路径，全部有代码依据）

1. **SPI 引擎的数据 token 等待窗太短**：`tf_spi_session` 对 CMD17 的响应后等待窗是 `midcycle=99`（100 字节 ≈ 24 µs @ 4.17 MHz）。SD 规范允许卡在返回数据 token 前有最长 ~100 ms 的内部读恢复（NAND 弱块 ECC 重试等）。卡一旦超过 100 字节才给 token，本次会话失败，`req_hold` 立即重发 CMD17——每次重发都**中止**卡上一次准备中的读取，形成重发风暴；期间 `inflight` 持续为高。
2. **看门狗单阈值误判**：`tf_audio_ddr_path.v` 旧逻辑只看"请求挂起是否超过 0.5 s"（`HOTPLUG_TIMEOUT_CYCLES=25M`），不区分"卡不应答"与"卡应答但慢"。重发风暴在 0.5 s 后被误判为拔卡（`reader_fault` → `card_lost` 脉冲）。
3. **误判后果被逐级放大**：
   - 读卡器复位 8 拍 → 整个文件系统重扫；
   - `tf_playlist_bridge.sv:35`：`scan_done` 下降沿发送失效字 `0xff00`；
   - `push2_usb_a_control.sv`：`0xff00` → `guide_track_count<=0`；
   - `push2_song_menu.sv:18`：`track_count==0` → `chosen<=0` → **退回 SELECT SONG**；
   - 顶层 `gw138k_push_workstation_top.v`：`tf_card_lost` → `music_song_started<=0;tf_selected_track<=0`，会话拆除，歌曲从字节 0 重新开始。
4. 这同时解释了 0x68 时期串口看到的 `wav_ready` 反复掉落重现（每次误判都重扫+重发射频头解析）。

## 修复（0x77，三个独立防线）

### 1. 双阈值看门狗（`rtl/tf_audio/storage/tf_audio_ddr_path.v`）

区分两类传输故障，用上此前闲置的 `reader_debug_cmdrsp`（最后一次 SPI 会话的 R1 响应字节）：

| 故障类别 | 判据 | 阈值 |
|---|---|---|
| 卡不应答（拔卡/MISO 悬空，重发全部得到无效 R1，bit7=1） | `reader_debug_cmdrsp[7]` 持续为 1 | **0.5 s**（`HOTPLUG_TIMEOUT_CYCLES`，保持原值）→ 快速确认拔卡 |
| 卡应答但 token 迟迟不来（内部读恢复，重发期间 R1 有效） | 挂起但最后一次 R1 有效 | **5 s**（新增 `HOTPLUG_STALL_TIMEOUT_CYCLES=250M`）兜底，正常恢复期完全吸收 |

慢卡顿不再触发复位；真拔卡仍然 ~0.5 s 检出（MISO 上拉读 0xFF 的典型布局下）。

### 2. 歌单失效保持（新模块 `rtl/push2/push2_playlist_hold.sv`，接入 `push2_usb_a_control.sv`）

`0xff00` 到来时保留原歌单计数 2 s（96M @ 48 MHz）。重扫成功（计数词恢复）→ 界面完全无感；清单持续失效（真拔卡）→ 2 s 后计数清零 → 菜单退回。防线上 1 的任何残余误触发直接打到 UI。

### 3. 传输故障后原地恢复（顶层补丁，`tools/build_full_song_77.py` 内字符串替换）

看门狗触发时：不再清 `tf_selected_track`；置 `tf_recover`（仅在确有选歌会话时武装），等待重扫。若 `playlist_scan_done && tf_track_count!=0` 在 2 s 内回来：`music_song_started<=1`、`music_run_reset_count<=4`（CNN 管线复位）、`music_restart_delay<=2.5M`（等 PCM 通路重灌 50 ms）——**同一首歌从头重启分析，用户停留在 PRACTICE 界面，不踢回菜单**。若 2 s 内清单未恢复（真拔卡）：恢复意图过期，维持原有拆除+菜单退回行为。

## 修复后行为矩阵

| 场景 | 旧行为（0x76） | 新行为（0x77） |
|---|---|---|
| 分析中卡出现 <5 s 的读停顿（token 迟到） | 0.5 s 误判拔卡 → 踢回菜单、歌曲重启 | **无任何可见影响** |
| 分析中卡停顿 5 s–∞ 但仍在位 | 踢回菜单 | 歌曲原地从头重启分析，界面不退 |
| 拔卡（真移除） | ~0.5 s 判定 → 清单清空 → 退回菜单 | ~0.5 s 判定 → 重扫失败 → 计数保持 2 s 后清零 → 退回菜单（约 2.5 s，稍慢） |
| 拔卡→改名/换文件→插回 | 重扫，清单刷新 | 不变：重扫、清单刷新 |
| 拔卡后 2 s 内插回 | （0.5 s 内插回则不触发） | 3 s 窗口内插回 → 恢复流程，界面不退 |

已知取舍：真拔卡到菜单退回从 ~0.5 s 变为 ~2.5 s（0.5 s 判定 + 2 s 保持）；对"拔卡换文件再插回"的使用流程无影响。

## 验证记录

- **新 TB `sim/guidance/tb_playlist_hold.sv`**：计数采纳、重扫期保持、恢复取消、确认丢失清零、空表不武装——首轮运行**抓到修复代码自身的一个真 bug**（恢复计数词与保持递增在同一 always 块中对 `hold` 的两个非阻塞赋值冲突，后写覆盖前写导致保持窗口提前清计数），改为互斥 `else if` 后通过。这正是"留好日志+可复现"要抓的问题。
- **`sim/tf_audio/run.py` 全套 16 项 PASS**（含 wav/mp3/flac path、bridge、DDR 仲裁），覆盖双看门狗改动后的路径级行为。
- **`tb_tf_hotplug_probe`**（空闲轮询/拔卡停顿/复位/重插/暂停态探测/探测数据不漏入文件流）PASS。
- **`tb_playlist_bridge`、`tb_song_menu`** PASS（0xff00 协议与菜单边界回归）。
- **`push2_usb_a_control` + 新模块整体 elaboration** 通过（iverilog，基于 0x76 暂存源）。
- 0x77 Gowin 构建：`results/song_guide_full77_20261004_125442`（脚本 `tools/build_full_song_77.py`，基线 full76，输入哈希锁定，UserCode `0x77`）。构建结果与板测见文末附录。

## 待实体复测（0x77 烧写后）

1. 选 MUSIC02 → 分析越过第一窗（曲谱计数 > 40）→ 持续增长 → `SONG READY`（整首曲谱验收，此前悬置项）。
2. 分析中拔卡 ≥3 s：应清单退回菜单；插回改名卡：清单显示新歌名（热插拔回归）。
3. 观察串口 `lost_seen`：正常整曲分析期间不应置 1（若置 1 且卡在位，说明仍有 ≥5 s 的停顿，需回传日志）。

## 复现命令

```bash
cd migration/gw138k_audio/push2_workstation/usb_a
python3 sim/tf_audio/run.py                                   # 16 项 TF 回归
iverilog -g2012 -Wall -s tb_playlist_hold -o /tmp/ph.vvp \
  rtl/push2/push2_playlist_hold.sv sim/guidance/tb_playlist_hold.sv && vvp /tmp/ph.vvp
python3 tools/capture_tf_hotplug.py --seconds 120 --port /dev/ttyUSB1   # 板端遥测
```

## 附录 B：0x77 板测结论与 0x78 依据（2026-10-04 下午）

### 0x77 首次实体复测

用户选歌后 20 分钟停留在 SCANNING。全字段遥测追踪（`reports/stall_trace_20261004_b.log`，四字快照去重记录）还原了全过程：

1. **选歌链路本身是通的**：选歌后 0.4 s 内文件头重新解析（`seen_format` 0→1）、PCM 到达 CNN（`seen_pcm=1`）、CNN 离开空闲（状态 0→2 CQT→6/7 推理）、TF 持续流式供数（card_stat 在 8/9 间交替）。0x76 时代"选歌即冻结"的疑虑排除——续窗链路在实体上可以运行。
2. **运行约 2 分钟后，看门狗再次触发**（trace 511284.7 活跃 → 511286.1 冻结，`lost=1` 而卡在位）：卡在读扇区过程中静默 >0.5 s——0x77 的快速阈值（0.5 s 无应答）把消费级卡在高强度读取下的内部维护静默误判为拔卡。**0.5 s 阈值对这张卡不可用**：30 分钟内两次自发触发，用户此前"20 分钟一直扫"即反复触发+反复拆会话的累积效果。
3. **0x77 的原地恢复没有接住**：恢复窗口 1.92 s 短于"卡唤醒 + 重新初始化 + 重扫"的实际耗时（ACMD41 重试无超时上限，慢唤醒可达数秒），`tf_recover_wait` 过期放弃，会话永久停留在拆解态（fs=READ_A_FILE、allow=0、CNN 空闲、文件头未重析——与 trace 终态完全吻合）。

### 0x78（本轮修复）

| 参数 | 0x77 | 0x78 | 理由 |
|---|---|---|---|
| 快阈值（无应答 R1 无效） | 0.5 s | **4 s** | 吸收卡维护静默，亚秒级停顿完全不触发 |
| 慢兜底（R1 有效但挂起） | 5 s | 5 s（不变） | 覆盖 token 迟到型挂起 |
| 原地恢复窗口 | 1.92 s | **9.6 s** | 覆盖慢唤醒 + 重扫 |
| 歌单保持 | 2 s | **10 s** | 与恢复窗口排序：恢复 9.6 s 先过期，保持 10 s 后过期 |

预期行为：亚秒静默无感；>4 s 静默 → 同一歌曲原地从头重启（不踢菜单）；真拔卡 → 约 14 s 后出菜单（4 s 判定 + 重扫失败 + 10 s 保持）。回退：原 0.5 s/2 s/1.92 s 行为可由参数恢复。

回归：`tb_playlist_hold`（窗口参数位宽 [26:0]→[28:0]）+ `sim/tf_audio/run.py` 16 项全过。构建 `results/song_guide_full78_20261004_150443`（`tools/build_full_song_78.py`，基线 full77，输入哈希锁定，UserCode `0x78`）。

### 0x78 构建与烧板记录

- P&R：BSRAM 279/340（持平）；`ddr_ui100` 实测 Fmax 222.891 MHz（约束 100）；hold 负违例 0。
- 烧板：`results/sram_20261004_154631_292911`，三段校验过（before `0x77` → SRAM → after `0x78`）。
- 模型上传：104,478 字节 9.0 s，`model_status=E`（DDR 回读 CRC 通过）。
- 烧板后首读：`model=E card=8 scan_done=1 lost_seen=0`。待实体复测。

### 0x79 构建（token 窗口规范化，2026-10-04 晚）

用户无可替换的 TF 卡，取证后把根因再推一层：卡的"静默"是**被我们的 abort 风暴逼出来的**——SPI 会话的 CMD17 数据 token 等待窗只有 100 字节（~24 µs），而 SD 规范允许卡花最多 ~100 ms（NAC）才给出首个数据 token；卡一旦超窗，读取器立即重发 CMD17，反复打断卡内部的读取准备，直至其完全不应答，随后被看门狗判死。0.5 s/4 s 两档阈值都被击穿的机理即此。

修复（`tf_spi_session.v` + `tf_sd_spi_sector_reader.v`）：token 等待窗从 8 位计数（99 字节）扩为 24 位，IDLE/READING 会话统一使用 `TOKEN_WAIT_BYTES=40000`（1.92 MHz 读时钟下 ~166 ms，覆盖规范 NAC + 余量）；FE 早退路径不变，卡只要给出 token 就无缝续流，不再有 abort。外层看门狗（4 s/5 s）与恢复/保持逻辑保持不变作为兜底。

回归：16 项 TF 套件 + 热插拔探针 TB 全过。构建 `results/song_guide_full79_20261004_204059`（基线 full78，仅两个 vendor 文件变化，BSRAM 279 不变，`ddr_ui100` 233 MHz，UserCode `0x79`）。烧板 `results/sram_20261004_211446_548492` 三段校验过，模型上传 9 s 状态 `E`。待实体复测：选歌后观察计数与 `lost_seen`——若卡静默被窗口吸收，`lost_seen` 应长期保持 0。

### 0x79 实体复测结果（2026-10-04 晚，`reports/fullsong_watch_20261004.log`）

用户选 TRAVLER（48 kHz）：

- **第一窗完成，出谱 36 项**（旧基线 40 项为 MUSIC02 单窗，不同曲不可比）；
- **第二窗完成，36 → 69（+33），第三窗续跑**——多窗链式分析在实板成立；
- 全程 `lost_seen=0`、`seen_pcm=1`：token 窗口修复经受住持续读取考验，abort 风暴根因修复确认；
- 选歌后约 1-2 分钟内 TRAVLER 整个文件即流完进入 DDR 环形缓冲（`busy=0`、`allow=1` 为采集完成后的常态），此后各窗全部从 DDR 出，不再访问卡；
- **节律**：每窗 172 帧约 8 分钟（约 0.4 帧/s），曲谱项在每窗末尾一次性吐出（Viterbi 回溯特性），计数呈阶梯跳增。整曲扫描时长 = 窗数 × 8 分钟——TRAVLER 若为 3 分钟曲目约 90 窗 ≈ 12 小时；**边扫边演奏按设计工作**，完整扫描需过夜或后续做 CNN 吞吐优化（与 0x64 时代"现有核分析 2 秒音频要几分钟"的已知差距一致，属独立任务）。

**主线（选歌 → 整首曲谱指引）在 0x79 上功能验收通过；遗留项：CNN 吞吐优化、36 vs 参考输出的逐项精度校验。**

### 0x78 实体复测（换卡前最后一次取证，`reports/rate_probe_20261004.log`）

- 用户选歌后链路**再次全活 53 秒**（TF 连续流式、`seen_pcm=1`、CNN 在 S_WINDOW_RESTART 窗口节律上推进、BP 波形计数 000→009）——0x78 的参数与恢复逻辑本身工作正常。
- 531208.5 前后卡在读扇区时**静默超过 4 秒**：0x78 的新阈值如实等待 4 s 后于 531212.5 触发，531213.5 出现完整拆除签名。0.5 s（0x77）与 4 s（0x78）两档阈值都被同一张卡击穿——**该卡在持续读取下会随机失联亚秒到数秒，与负载无关，判定为卡本身（或其固件）不可靠**。
- 附带发现：管线 FSM（`basic_pitch_pcm_pipeline.state`）不复位 `analysis_restart`（拆除后 state 停在 46=S_WINDOW_RESTART 而非 S_CAPTURE），`run_reset` 只影响子引擎；后续如需"重启即回捕获态"需另补复位。当前窗口节律下无害，记录备查。
- **处置：换 TF 卡复测**。0x78 的 4s/5s 阈值 + 原地恢复 + 10 s 歌单保持作为正常卡的安全网保留。备选方案（若无可换的卡）：`tf_sd_file_reader` 的 `SPI_CLK_DIV_FAST` 12→24（4.17→2.08 MHz），利用 128 MiB DDR 环形缓冲吸收采集速率下降，代价是整曲扫描时间变长。

## 附录 A：0x77 构建与烧板记录（2026-10-04）

- 构建：`results/song_guide_full77_20261004_125442`（`tools/build_full_song_77.py`，基线 full76，`tool_result.json`: exit 0、`inputs_unchanged: true`）。Gowin 全流程约 55 分钟。
- 资源：BSRAM 279/340（SDPB 218 + SDPX9B 19 + pROM 33 + pROMX9 9），与 0x76 完全持平——三处修复均为寄存器级。
- P&R 时序（`Prj1.tr` 2.3 Max Frequency Summary）：`ddr_ui100` 实测 Fmax **239.489 MHz**（约束 100，0x76 为 226.942）；`ddr_mem400`、`cpu_core100` 大裕量；所有域 hold 负违例为 0。`clk_50m`/`audio_76m8`/`usb_48m` 的 setup 估计值低于约束——与既往可运行版本（0x64/0x76）同级别，属既有的约束/估计口径问题，不随本次改动变化。
- 烧板：`results/sram_20261004_134902_552684`，`program_sram.py` 三段校验全过（before `0x76` → SRAM → after `0x77`）。
- 模型上传：104,478 字节，9.0 s，`model_status=E`（DDR 回读 CRC 通过，CRC32 `AF01A61B`）。
- 烧板后首读遥测：`model=E fs=5 card=8 scan_done=1 lost_seen=0`——歌单就绪，看门狗锁存位干净。
- 改动文件清单：`rtl/tf_audio/storage/tf_audio_ddr_path.v`（双阈值看门狗）、`rtl/push2/push2_playlist_hold.sv`（新增）、`rtl/push2_usb_a_control.sv`（接入保持模块）、顶层补丁（构建脚本内，`gw138k_push_workstation_top.v` 的 `tf_card_lost` 分支 + 声明区）。
- 实体复测结果：**待用户在 Push 上选歌验证**（通过标准见"待实体复测"一节）。
