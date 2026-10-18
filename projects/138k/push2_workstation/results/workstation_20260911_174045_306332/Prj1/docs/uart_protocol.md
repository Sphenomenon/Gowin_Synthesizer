# 串口协议与合成核心基线

这是当前 `Prj1` 的可运行的32声部分时复用基线。参考设计中的 IF-EVT 是每条记录 8 × 32 bit；本工程暂用 **2 × 32 bit 的专用控制记录**，保持模块间数值链路 32 bit，但不宣称已经实现 IF-EVT、任务调度或可重编排图执行器。

本协议仅对应Prj1的115200自定义包。原工程/G1使用31,250 baud MIDI字节，音符与声部分配语义不同；独立48kHz迁移候选保留G1协议，不将本包的voice、增益或ADSR字直接传给原MIDI核心。左右Q1.31可作共同音频边界，控制值转换和舍入规则须另行显式适配。

## 时钟与接口

- FPGA 系统时钟 50 MHz，UART 115200 baud、8 数据位、无校验、1 停止位；无 RTS/CTS。
- UART 位周期四舍五入为 434 个系统时钟，实际约 115207.37 baud。
- 当前音频帧率是 **50,000,000 / 1024 = 48828.125 Hz**；音高换算必须使用实际帧率。此值不是 48000 Hz。
- `uart_control` 把物理字节流封装成 `cmd_data[31:0]`；内部 byte adapter 的数据口也零扩展至 32 bit。
- 命令第一拍 `header = {sequence[7:0], opcode[7:0], voice[7:0], flags[7:0]}`，`first=1,last=0`；第二拍为 `value[31:0]`，`first=0,last=1`。仅在 `valid && ready` 上升沿消费，背压时保持字和边界标记稳定。
- 合成器收齐两拍后，等下一个 `sample_tick` 一次性提交。回复在提交后产生，不以刚收到串口字节为成功依据。
- `sample_tick` 是与 `clk` 同域、宽一个周期的使能。正常工作相邻tick间隔1024周期；初始化期间的首个请求会保留并在状态RAM准备好后补算。
- 每个 tick 对提交前的声部状态计算一帧；32声部在226个系统周期后 `sample_valid` 拉高一个周期，`mix_sum` 保持40bit宽位混音总和。最终输出级从宽位总和施加总音量与LR平衡，生成分别饱和的左右Q1.31样本，再交给板级PT8211适配器；`sample_data` 保留饱和单声道观测值，音频主链路使用未提前饱和的 `mix_sum`。
- `active_voices[31:0]` 是位掩码，全部32位对应voice 0…31。它表示 ADSR 状态非 IDLE，包含起音、静音 sustain 和释放尾音；不能直接作为“可闻声源数”的评分证据。

## 主机请求：固定 12 字节

| 字节偏移 | 名称 | 内容 |
|---|---|---|
| 0 | Sync 0 | `A5` |
| 1 | Sync 1 | `5A` |
| 2 | Sequence | 0…255，主机递增，FPGA 原样回传 |
| 3 | Opcode | 见下表 |
| 4 | Voice | 0…31；PING/PANIC/MEMORY_STATUS/VIDEO_STATUS/VOICE_STATUS/LATENCY_STATUS/MASTER_VOLUME/LR_BALANCE使用 `FF` |
| 5 | Flags | 当前必须为 `00` |
| 6…9 | Value | 无符号 32 bit，小端序 |
| 10…11 | CRC16 | 小端序；覆盖字节 2…9 |

CRC 使用 **CRC-16/CCITT-FALSE**：多项式 `0x1021`，初值 `0xffff`，不反射，无最终异或。标准输入 `123456789` 对应 `0x29b1`。Sync 不进入 CRC。

| Opcode | 命令 | Voice | Value |
|---|---|---|---|
| `00` | PING | `FF` | 0 |
| `01` | NOTE_ON | 0…31 | DDS phase step，范围 `0…7fffffff`；静音声部从零起音，仍发声的声部保持相位/电平并重新进入 ATTACK |
| `02` | NOTE_OFF | 0…31 | 0；从本声部当前包络进入 RELEASE |
| `03` | PITCH | 0…31 | 新 phase step；保持相位连续，不改变其他声部 |
| `04` | VELOCITY | 0…31 | 无符号 Q1.31 增益 `0…80000000` |
| `05` | WAVEFORM | 0…31 | 0 = triangle；1 = 50% duty pulse；2 = sine（新版位流） |
| `06` | ATTACK_STEP | 0…31 | 每帧上升的 Q1.31 步长 `0…80000000`；0 表示下一次该阶段更新到达终点 |
| `07` | DECAY_STEP | 0…31 | 每帧下降步长；0 表示下一次该阶段更新到达 sustain |
| `08` | SUSTAIN | 0…31 | 无符号 Q1.31 电平 `0…80000000` |
| `09` | RELEASE_STEP | 0…31 | 每帧下降步长；0 表示下一次该阶段更新归零 |
| `0A` | PANIC | `FF` | 0；在下一帧边界清除全部声部包络与相位 |
| `0B` | MEMORY_STATUS | `FF` | 0；只读 DDR/显示状态，回复字节 4 改为状态 flags |
| `0C` | VIDEO_STATUS | `FF` | 0…15；读取诊断快照中的一个字节，0开始新快照 |
| `0D` | VOICE_STATUS | `FF` | 0…3；读取完整32位活动掩码快照，0开始新快照 |
| `0E` | LATENCY_STATUS | `FF` | 0…63；读取64字节音频数字链路延迟快照，0开始新快照 |
| `0F` | VOICE_ONSET_STATUS | 0…31 | 0…31；读取该声部最近NOTE_ON的32字节起音快照，0开始新快照 |
| `10` | MASTER_VOLUME | `FF` | 无符号增益 `0…80000000`，0 静音，`80000000` 为100%单位增益 |
| `11` | LR_BALANCE | `FF` | 偏移二进制 `0…80000000`；0 仅左，`40000000` 居中，`80000000` 仅右 |

`phase_step = round(frequency_hz × 2^32 / Fs)`。MIDI 音高 `m` 的频率为 `440 × 2^((m-69)/12)`；小数音高允许单音滑移，例如 69.5 高于 A4 半个半音。主机只生成参数，FPGA 逐样本生成波形。硬件允许 step=0 用于数字测试；pulse 在此条件下可产生直流，正常演奏请使用非零音高。

NOTE_ON 不自动分配空闲声部；主机显式选择0…31。声部处于活动状态且包络非零时（包含 RELEASE 尾音），NOTE_ON 更新音高，保持当前包络和正常DDS相位推进，从当前电平重新进入 ATTACK，避免复用尾音槽时把波形突然截到零。未发声或包络已经为零时仍重置相位/包络，从零进入 ATTACK。所有配置独立存留至再次配置或系统复位；12字节命令及ACK格式不变。

仅对仍发声声部的这次重触发，A/D 的有效步长上限为 `0x01000000`（每样本满量程的1/128），配置为0的立即跳变也改用此步长；满量程斜坡约2.62144ms，实际时间取决于起止电平。较慢的A/D保持原步长，完成DECAY后退出此保护，配置寄存器本身不被改写。NOTE_OFF打断重触发时立即转入正常RELEASE；完全静音后的首次起音、正常释放及PANIC语义保持原样。PITCH继续只更新步进，不重启包络。

波形值 2 是本轮向后兼容扩展，采用 1024 点 Q1.31 正弦查表。首版位流只接受 0/1，收到 2 时返回 status=3；主机提示下载新版位流，不自动转换为三角波。命令包长度、其他 opcode 及值域保持不变。

## FPGA 回复：固定 8 字节

| 偏移 | 内容 |
|---|---|
| 0…1 | `A5 5A` |
| 2 | Sequence |
| 3 | Status：0 成功；1 未知 opcode；2 非法 voice；3 非法 value/flags；4 内部记录格式错误 |
| 4 | 原 opcode 为 `0B` 时是 DDR/显示状态 flags；`0C`为视频诊断字节；`0D`为完整声部快照中的一个字节；`0E`为延迟快照字节；其余命令为提交后活动掩码低8位（voice 0…7） |
| 5 | 原 opcode |
| 6…7 | 小端 CRC16，覆盖字节 2…5，算法同请求 |

内部回复字为 `{sequence,status,active_mask,opcode}`，通过独立 32 bit `rsp_data/valid/ready` 链路交给串口适配器。非法参数回复错误并保持当前声部配置。

`MEMORY_STATUS` 是本轮 DDR 位流增加的只读诊断命令。其内部回复为 `{sequence,status,memory_flags,opcode}`，8 字节包长度与 CRC 覆盖范围不变。仅在 `Status=0` 且原 opcode 为 `0B` 时解释下列状态位；普通 PING、音符和 PANIC 的返回语义保持不变。查询不会清音、重触发音符或清除故障计数。

| Bit | CLI 字段 | 为 1 时的含义 |
|---|---|---|
| 0 | `calibrated` | DDR 控制器已完成初始化/校准 |
| 1 | `bist_done` | 启动内存自检已结束 |
| 2 | `bist_failed` | 启动内存自检记录了失败 |
| 3 | `front_valid` | 前台 DDR 帧缓冲已有有效帧 |
| 4 | `fetch_fault` | 显示读行发生抓取故障，例如超时 |
| 5 | `underrun_seen` | 显示累计欠载计数非零；该位不表示当下仍在欠载 |
| 6 | `ddr_pll_locked` | DDR PLL 锁定 |
| 7 | `video_pll_locked` | 视频 PLL 锁定 |

这 8 位分别是工程内状态观察。`bist_done=1` 还需结合 `bist_failed=0` 判断自检结果，且只覆盖当前自检配置的地址范围；`video_pll_locked=1` 本身不证明显示器已经识别 1080p60。GUI 离线控制模拟不模拟 DDR，`0B` 返回未知 opcode，不会伪造校准或自检通过。旧位流同样可能不支持 `0B`，需下载包含 DDR 适配的新版位流。

`VIDEO_STATUS`（0C）使用同样的12字节请求、8字节ACK。index=0在采样边界锁存50MHz域的128位诊断，ACK字节4返回快照byte0；后续index=1…15从同一快照取值。复位后未先读0即读其他index返回status=3；voice必须FF、flags必须0，index超过15拒绝。重复读0刷新快照，查询不改变声部或清除计数。仅成功的真实ACK可解释为 `video_status_byte`；离线模拟拒绝0C。

| 快照字节 | 内容 |
|---|---|
| 0 | schema version，当前1 |
| 1 | bit0=HPD；1=视频时钟启动资格；2=像素复位已释放；3=扫描复位已释放；4=串化器仍在复位；5=完整测量窗口有效；6…7=0 |
| 2…3 | 小端16位，每10ms内的1024像素时钟块数；频率约为 `blocks × 0.1024 MHz`，量化误差约±0.1024MHz |
| 4…7 | 小端32位，像素域vblank累计帧数 |
| 8…11 | 小端32位，DDR已完成渲染帧数 |
| 12…15 | 小端32位，扫描欠载累计数 |

各源域计数注册Gray后经两级同步进入50MHz域；源域复位期间屏蔽对应计数。像素计频使用板载50MHz参考，恢复后必须完整采满10ms才有效；若像素停钟但锁定/复位标志未变化，下一个完整窗口会测得0。不同源域存在几个周期的采样延迟，整组串口快照保持固定并不表示所有源计数在同一物理时刻采样。帧数在相应域复位时归零，溢出按32bit回绕。串口工具 `video-status` 顺序读完整快照，保留原始字节；测得148.5MHz附近和帧数推进仍不能证明接收器已同步。

CLI 采用 **stop-and-wait**：一个请求写完，读到匹配 Sequence/Opcode 且 CRC 正确的回复，再发下一条。GUI 使用下述有界流水调度。12 字节请求线路时间约 1.042 ms，8 字节回复约 0.694 ms，另外有采样帧量化和少量流水线开销。配置多个参数需要多个事务；可在演奏前预置，实际 NOTE_ON 单独发送。和弦音符按顺序下发，尚未支持带时间戳的同帧多音提交。

CRC 错误、UART stop-bit 错误、不完整包或拥塞丢弃不会执行命令，也不会产生 ACK；适配器累加 `error_count`，此计数当前仅板内诊断输出，没有主机读取命令。包内字节间超过约 260.4 μs（30 bit 周期）无输入，解析器回到 Sync 搜索；重复的 `A5` 也可重新寻找 `A5 5A`。一条 CRC 失败包被整个丢弃，不把其内部内容执行为命令；后续完整包重新同步。

命令发布端有一条保持缓冲，回复端有一条串行化缓冲；这不是无限事件队列。无节拍连续发送可能丢包，不提供无限吞吐保证。GUI 的已验证发送间隔为至少1.5ms，最多16包在途；不等待每个ACK再发下一包，同槽NOTE_ON仍等待该槽参数确认。Sequence 只用于对应回复，不做去重；工具超时即报错，不自动重放 NOTE_ON，避免无意重触发。

`VOICE_STATUS`（0D）保持固定包长度。voice=FF、flags=0、value/index=0…3；index=0在帧起点锁存此前已完成帧的32位活动掩码并返回低字节，1…3按小端顺序读取同一快照。中途发生NOTE_ON/OFF、PANIC或自然释放不改变快照，再读0才刷新。复位后未读0即读非0、index>3或非法flags返回status=3，voice非FF返回status=2。查询不改变相位、音色或显示参数版本。

普通ACK仅包含低8位，主机不能据此清除voice8…31。新版GUI连接时探测0D；未知opcode明确降为旧四声部模式。完整状态轮询限频并让出演奏/释放操作。命令在采样帧起点锁存，逐槽更新结束后ACK和活动掩码才发布；处理中不接受新命令。32声部配置和NOTE_ON仍经UART逐条发送，尚不支持同帧同时提交多音。调度、资源和混音电平见[32声部实现](tdm32.md)。

`LATENCY_STATUS`（0E）读取64字节原子快照，index0锁存、1…63读取原副本；复位后未读0即读非0、index>63或非法flags返回status3，voice非FF返回status2。计数涵盖同步后UART起点、CRC、提交、样本、PT8211双槽及ACK，阶段有效位区别尚未完成和0周期；查询不改声音记录。当前也记录MASTER_VOLUME/LR_BALANCE：state_sample和DAC state端点为新目标版本应用后的第一帧，并不等待增益斜坡结束；两项note-only端点保持不可用。完整字段、主机单程上下界和模拟端点限制见[延迟检测](latency.md)。

## 合成与数值规则

每个声部独立保存 32 bit DDS 相位/步长、线性 ADSR 状态、电平、A/D/S/R 参数、力度与音色。默认 triangle，velocity=0.75，attack step=8,800,000，decay step=128,000，sustain=0.625，release step=440,000。在当前 Fs 下默认起音约 5 ms、全量程释放约 100 ms；默认 sustain 电平开始的释放更短。

包络使用步长饱和到达终点，没有商/余数的精确采样数分配。主机将指定时间换算为向上取整步长；ADSR 不是逐样本精确时长协议。通常零步长表示下一次阶段更新立即到达终点，活动声部重触发的A/D采用上方平滑规则。释放从当时电平下降，所以 `--release-ms` 表示全量程到零时间上界。当前修复覆盖尾音槽复用和活动声部重触发；实时修改 sustain、力度、音色，以及零时间首次起音/释放和PANIC仍可产生幅度突变，未加入通用去爆音交叉渐变。

波形和声部增益均经 FPGA 整数乘法，内部保留 65 bit 有符号乘积；输出取 `[62:31]`，即向负无穷取整的 Q1.31 量化。增益不超过 1，正满幅为 `0x7fffffff`。32声部依次在共享40bit累加器内按满幅贡献求和，**不除以32，也不除以当前活动声部数**。宽位混音先乘总体音量，再乘左右平衡增益，最后分别饱和为 L/R Q1.31，经 PT8211 舍入/饱和输出 PCM16。即使和弦混音超过满幅，降低总体音量仍可在最终饱和之前保留余量；不存在中间提前削波后的假音量补偿。

`MASTER_VOLUME`（10）和 `LR_BALANCE`（11）要求 voice=FF、flags=0，value 范围0…80000000。非法voice返回status2，非法flags/value返回status3，并保留原目标值。增益以31位小数表示，`80000000` 精确编码1；balance为偏移二进制：`balance_word = round((balance + 1) × 2^30)`，主机 balance 范围−1…+1。居中时左右都为1；往左仅降低R，往右仅降低L。将 balance_word 记为 B，左右目标增益分别为 `min(1, 2 − B/2^30)`、`min(1, B/2^30)`。默认总音量100%、balance居中；PANIC清声部但保留输出设置，系统复位恢复默认值。

两命令在采样边界提交目标并返回普通ACK，字节4仍是活动掩码低8位。FPGA每帧将总音量和平衡各自向目标推进至多满范围1/256，完整0↔满范围最长256样本（5.24288ms），balance居中至端点最长128样本；每帧固定使用一组增益，左右声道不会取到不同时间的设置。ACK确认目标已提交，斜坡可能尚未结束。多声部叠加超过输出满幅会在最后一级饱和，主机可下调总音量；没有自动响度归一化或自动限幅器。旧位流返回未知opcode时，GUI仅禁用不支持的输出控制，不断开演奏；CLI明确返回失败。

triangle、pulse 和 sine 都由 FPGA DDS 生成，均非主机传来的预录 PCM。三角波/脉冲波没有带限处理，高音会混叠，pulse 尤其明显；正弦使用相位高 10 位查表，仍有相位截断和 Q1.31 量化误差。此实现未包括运行时任意波表装载、FM、物理建模、效果、自由图编排、MIDI 字节协议、曲谱与编码录音，后续应按参考架构扩展。

## 主机工具

安装串口依赖：`python -m pip install pyserial`。以下命令在项目目录运行，端口替换为实际 FPGA UART 端口；串口信号是板级约束选定的 FPGA RX/TX。

```powershell
python tools/instrument_cli.py --port COM26 ping
python tools/instrument_cli.py --port COM26 memory-status
python tools/instrument_cli.py --port COM26 voice-status
python tools/instrument_cli.py --port COM26 master-volume 0.5
python tools/instrument_cli.py --port COM26 lr-balance -0.5
python tools/instrument_cli.py --port COM26 lr-balance 0
python tools/instrument_cli.py --port COM26 latency-status
python tools/instrument_cli.py --port COM26 adsr 0 --attack-ms 5 --decay-ms 120 --sustain 0.625 --release-ms 100
python tools/instrument_cli.py --port COM26 note-on 0 69 --velocity 0.2 --waveform triangle
python tools/instrument_cli.py --port COM26 pitch 0 69.5
python tools/instrument_cli.py --port COM26 note-off 0
python tools/instrument_cli.py --port COM26 demo --seconds 3
python tools/instrument_cli.py --port COM26 panic
# 下载新版位流后，--waveform 可使用 sine
python tools/instrument_cli.py --port COM26 waveform 0 sine
python tools/instrument_cli.py --dry-run note-on 0 69
python tools/instrument_cli.py --dry-run memory-status
```

`--dry-run` 只打印请求包，不打开串口；`--sample-rate` 可覆盖默认 48828.125。常规 note-on 不附带 velocity/waveform 选项时只有一个请求。Demo 使用 4 个独立声部与两种音色，期间只改变 voice 1 的音高，结束发 PANIC；初始化或演奏途中失败也会尝试 PANIC，若清理同时失败则报告清理诊断并保留原始异常。普通 note-on 不会自动发 PANIC，仍需 note-off 或显式 panic 结束持音。

`memory-status` 发一条 `0B FF 00 00000000` 请求（不含 Sync/Sequence/CRC 的表示），打印原始 `memory_flags=0xNN` 与上表八个字段。它不把该状态字节打印成 `active=`。该命令只查询状态，不启动额外内存写测试。主机 `Ack.active_mask` 为兼容保留原始回复字节 4；需要诊断状态时使用 `Ack.memory_flags`，该属性仅对真实、成功的 `0B` 回复返回整数，其余情况为 `None`。

可视化入口为 `python tools/instrument_gui.py --port COM26`。GUI 与 CLI 共用 `tools/instrument_backend/` 协议、换算和串口事务。GUI 的 `ControlWorker` 保证只有一个串口所有者线程；默认事务超时 350 ms，约每300ms查询完整活动掩码（旧固件用PING），待发命令上限512。连续修改同类参数时合并尚未发送的旧值，NOTE_OFF 优先并取消同槽排队 NOTE_ON，PANIC 清队列后优先发送。已经在途的事务在返回或超时后才让出串口。

GUI连接先PING、PANIC并探测完整声部状态能力，再同步当前总音量和LR平衡。输出命令分别收到成功ACK或旧位流未知命令回复后允许演奏；未知命令只禁用相应输出滑块。断开、关闭和通信失败时清空队列并尽力 PANIC，清理失败不会覆盖最初错误。无自动重连、无事务自动重试、无失败音符重放。后台事件 ACK 包含 `sequence`、`opcode`、`status`、`status_text`、`active_mask`、`rtt_ms`、完整八字节十六进制 `header` 及 `simulated` 标记。离线模式只提供控制状态模拟 ACK，不能解释为真实 FPGA 时延或音频遥测。详见 [GUI 使用说明](gui_control.md)。

## 自动检查范围

- `sim/tb_voice_bank_tdm.sv`：1061帧共享/旧并行实现的混音和全部状态逐位比较，覆盖32声部、三波形、ADSR、重触发、31号、命令锁存、PANIC、暖复位及225拍deadline。
- `sim/tb_synth_32voices.sv`：32声部引擎、满幅混音、完整声部快照、ACK背压、1024周期实际音频节拍及启动欠载检查。
- `sim/tb_synth_engine.sv`：显式配置四声部保留旧测试向量，帧边界提交、四声部活跃、单声部相位连续变调、独立释放/力度、ADSR 端点、非法命令拒绝、满幅混音和回复背压；另外检查 `0B` 状态查询、非法 Voice/Value、背压期间状态快照稳定及查询后 PING/声部语义不变。
- `sim/tb_uart_control.sv`：在真实 UART 仿真串行线上输入完整包、坏 CRC 和残缺包，验证恢复、32 bit 记录边界、FPGA 合成非零音频与 UART ACK CRC；把合成器接到 `pt8211_tx` 后从物理串行引脚独立解码，对左右 16 bit 槽逐个核对 Q1.31 量化参考值，同时检查单音变调、PANIC 后归零与无 underrun。测试分频加速，不作为板级时延报告。
- `sim/test_instrument_cli.py`：12 项检查覆盖 CRC 标准向量、包布局、音高/增益/包络边界、Demo 失败清理，以及 DDR 状态逐位解码、只读请求、输出字段、模拟状态拒绝和 PING 向后兼容。
- `sim/test_instrument_backend.py`：用 fake transport 检查 ACK 重同步/匹配、握手失败、有界队列、参数合并、释放与 PANIC 优先、关闭与原始错误保留，不打开真实串口。
- `sim/test_output_controls.py`：检查总音量/LR转换和CLI包、离线值域/复位默认、连接清音后同步、旧固件拒绝兼容，以及全局滑块合并时保留起音前的命令顺序；覆盖已预留但未发送、实际已发送和已在途三种情况，释放仍优先，不额外等待ACK。`sim/test_instrument_ui.py` 同时覆盖当前值ACK确认、重连位置、居中、PANIC补发、滑块意图计时与最小窗口布局；`sim/test_latency_diagnostics.py` 检查两个全局命令的首帧端点。
- `sim/tb_sine_rom.sv`、`sim/tb_sine_voices.sv`：检查全部 ROM 点及四声部正弦的独立相位、变调、混音和 PANIC，覆盖新 waveform=2。

这些是 RTL/协议仿真证据；板上耳机实际音频、模拟链路延迟和听感仍需硬件验证。

## 逐声部起音记录（0F）

32个声部独立保留最近NOTE_ON的触发→有效PCM贡献、触发→DAC帧完成周期数。松键、参数调整和其他声部命令不会覆盖已完成结果。索引0等待观测器原子读取；其余索引须匹配快照voice，非法voice=status2，非法flags/index/无快照/voice不匹配=status3。回复诊断字节不作为活动掩码。32字节布局、取消/重触发/静音标志见[声部起音检测](voice_onset.md)。0E保持原有64字节协议。
