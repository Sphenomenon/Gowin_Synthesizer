# P22 电脑键盘长按连击

2026-09-15：主机修复、Tk 检查、音频定向仿真、完整构建及 SRAM 下载/读回已完成。P22 UserCode 为 `0x00000022`，Flash 未写。板端 U15 回报仍为 0 字节；窗口在排旧缓存后进入标黄的单向演奏状态。2026-09-16 用户完成实体回归：先确认“现在电脑控制没啥问题了”，随后确认 Push、连续压力、HDMI、耳机和效果链“都正常”。P22 已完整实体验收。

## 修改及使用

根因和全路径见 [源码审计](P22_KEYBOARD_REPEAT_AUDIT.md)。现有 `ae350/scripts/keyboard_midi.py` 在首次按下后被 `pressed`/`Notes.held` 去重，原来不会发送重复 note 事件。P22 在这个入口增加每键计时器，短按一次，长按 300 ms 后每 80 ms 发送 Note Off/On；收到松键事件立即停计时器，最终 Note Off 保留原 30 ms X11 配对窗口。失焦、关闭、连接失败及原 PANIC/模式切换清理均取消新计时器。原 PANIC 同步缺口留给下一阶段。

长按的本机 held 显示不变，因此连击不重复重画琴键，避免绘图占用重复间隔。系统重复事件不创建额外计时器；阻塞后不集中补发积压点击。本机空格延音期间暂停连击，防止 CC64 延迟 Note Off 后积累声部；放开踏板恢复。保留同音高跨来源共享释放的旧语义。

本轮已启动更新后的原演奏窗口；串口就绪后用于实体检查，也可从原入口启动：

```sh
/home/sphenicidition/Documents/fpga/migration/gw138k_audio/ae350/play_keyboard.sh
```

没有增加或恢复板端 performance keyboard 页面。Push 持垫、连续压力、声部分配、MIDI 解析、HDMI、DDR、AE350、音频和效果链的生产源码未修改。

## 结果与构建

新构建：`results/build_20260915_213126_710277`。修复在电脑脚本，发布绑定必须同时检查脚本 SHA256 和位流 SHA256，不能仅凭位流认定主机脚本已经更新。

| 项目 | P22 |
|---|---:|
| setup 违例 | 0 |
| hold 违例 | 0 |
| 最差 setup slack | +0.010 ns |
| Logic | 33830 |
| Register | 25192 |
| BSRAM | 253 |
| DSP | 43.5 |

Gowin 完整综合、布局布线返回 0，输入未变化，未复用综合结果。与 P21 构建输入逐文件比较，仅 `scripts/build.tcl` 增加官方支持的 `set_option -user_code 00000022`；RTL、约束及生产固件完全一致。位流 CheckSum 仍为 `0xD14C`，UserCode 为 `0x00000022`，SHA256 为 `f88f2a1a97e629b30a381b2e84c29f08893f5a626e94eb0466dc57c535a95dbb`。

完整 `usb_a_audit.json` **未通过**，错误与 P21 完全相同：`u_managed/effect_mask_sync_0_s0/RESET`、`_1_s0/RESET`、`_2_s0/RESET` 未被 stopped-clock reset 审计覆盖。审计在这里提前结束，不能把后续完整检查写成通过。

独立音频 PLL/mailbox 审计以实际层次 `u_managed/u_audio` 运行通过，PLL_INIT 最长传播 9.743 ns。第一次调用通用 CLI 使用了旧独立音频顶层默认 `u_audio`，因此报 missing payload registers；保留该报告，正确层次报告为 `p22_audio_routed_audit_correct_hierarchy.json`。这项局部通过不覆盖完整 audit 的旧缺口。

## 定向验证

最终 `p22_keyboard_20260915_220702_621343/verification.json`：11 项真实 Tk 事件循环/模拟回调检查通过，包括短按、长按、重复 KeyDown、X11 同时间戳 Release/Press、真实快速重按、和弦、空格延音、原 PANIC 锁存、模式切换、失焦清理、断线、U15 静默时的单向状态和关闭。长按重复间隔为 80.156–80.841 ms；这只是主机定时器测试，不是实体键盘到耳机的交互延迟。

先前测试记录原样保留：一次 X11 测试受宿主调度超出 30 ms 窗口影响；一次断线模拟器意外被串口轮询读取而报测试回调异常，该次结果不作为最终证据。最终测试关闭无关的串口轮询，并把任何 Tk 回调异常作为失败条件。

音频仿真入口为 `sim/p22/run.py`。首次编译漏传 USB 头文件路径，已修正；首次执行用固定 100 ms 判断尾音回收，笛音色满包络约 209 ms 的正常 RELEASE 尾音导致断言失败。最终判据检查每个已分配声部进入 RELEASE，再按原 `envelope_level/release_step` 算出剩余帧数并验证回收，未修改音频包络。

最终 `p22_audio_sim_214047_483818/verification.json` 通过：实际 115200 PC UART → 50 MHz 接收 → 单字节 CDC → 76.8 MHz MIDI 解码队列 → 仲裁 → 原声部分配/串行效果/PT8211。AE350 时钟全程停止；同时保留不同音高的 G1 UART 持音、Push 事件持音和压力更新。A/B/C 各 39 次和弦分配，最终 allocated/held/active 全零；总计 226550 帧、226469 帧非零、301 个控制事件、Note On/Off 各 128 次，最大同时活动 14 声部。采样间隔恒为 1600 周期，音频和 PC 健康计数零。正常三音连击下 PC FIFO 最大占用 1，未出现 PC 队列背压；不把它写成满队列压力验收。

```sh
python3 migration/gw138k_audio/ae350/scripts/check_keyboard_repeat.py --results <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/p22/run.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py --user-code 00000022
python3 migration/gw138k_audio/push2_workstation/usb_a/audit.py <新构建目录>
```

## 下载与实体边界

初次 `p22_hardware_probe_214251_384206/result.json` 未找到 SIPEED 调试器。用户随后恢复连接，重新扫描到 `0403:6010`、序列号 `2025030317`，USB location 53、sysfs `/sys/bus/usb/devices/3-5`；没有沿用旧 location 54。

下载记录：`../results/sram_20260915_215319_714349/result.json`。本次实际写前读回 P21 `0x0000D14C`，随后只执行 SRAM 操作 2，再实际读回 `0x00000022`；before/sram/after 均 passed，`fpga_flash_written:false`。

第一次启动的窗口会话 `../../results/keyboard_session_20260915_215420_294122/events.jsonl` 等待 12 秒后因未收到 C350/K138 而断开。随后单次只读 `../results/capture_20260915_215533_259858/result.json`（2 秒排旧缓存 + 5 秒捕获）收到 0 字节、0 条有效记录，CRC 错误 0。没有发送自动演奏或清音命令。当前证据无法区分 UART 物理/桥接路径与板端发送状态，不能据此判定 HDMI/音频/Push 通过或失败；P21 也有短 UART 窗口无记录的旧现象。

最终脚本 SHA256 为 `23687fd8f895466d878fbc31cc51c1974027120b88a51c5979f8c017a33ca674`。实体操作会话 `../../results/keyboard_session_20260915_221519_927988/events.jsonl` 在开口 2 秒后记录 `one_way_ready`，没有声称收到板端回报。日志包含 510 次 MIDI 发送，其中 Note On/Off 各 254 次，覆盖 18 个音高；各音高最终计数完全配对，没有残留本机持键。用户于 2026-09-16 反馈“现在电脑控制没啥问题了”，据此将电脑键盘短按、长按连击和松键停止记为实体通过。此前 `220725` 窗口随启动 shell 退出，未产生按键数据，不作为实体证据。

实体操作完成后，SIPEED `0403:6010` 调试器曾从 USB 总线消失，窗口随后记录 `[Errno 5] Input/output error`。调试器恢复后，2026-09-16 12:38 只执行 `Read Device Codes`：ID Code `0x0001081B`、UserCode `0x00000022`、Status Code `0x00026230`，确认键盘实体操作后 SRAM 中仍是 P22。该次没有执行下载或 Flash 操作；原窗口仍处于断开状态。

用户随后确认 Push 持垫、连续压力、灯光、屏幕、HDMI、耳机和 P10 串行效果链均正常。P22 完整实体验收通过；正式版本记录为 `BOARD_CURRENT_P22_KEYBOARD_REPEAT.json`。P21/P10 旧目录、位流及版本记录均保留，USB IN error 诊断仍为 null。
