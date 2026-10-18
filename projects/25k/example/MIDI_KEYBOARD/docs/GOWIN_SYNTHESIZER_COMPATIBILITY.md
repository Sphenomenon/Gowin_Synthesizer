# GW25K 与 Gowin Synthesizer 接口兼容性检测

检测日期：2026-10-17。结论：**当前活动源码支持 GW25K 向 138K 发送键盘 MIDI；138K 向 GW25K 输出屏幕和引导灯尚未接通。完整面板接口不兼容，需要在 138K 端增加适配。**

本次只读检查目标工程，并执行离线交叉测试；未烧录、未连接硬件、未修改目标工程。下述“通过”指对应软件检测通过，不能替代板间枚举、音频和供电实测。

## 检查对象和版本边界

本板工程：`/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD`。

目标工程：`/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer`；实际 USB Host 实现在 `migration/gw138k_audio/push2_workstation/usb_a`。本报告下文以 `USB_A/` 表示此目录。

目标 Git HEAD：`8c998bacc54d0a60c30a194a7ee54a37c2a838c0`。检测同时记录工作区实际源文件 SHA256，不以 Git 提交替代现有文件内容。生产 `USB_A/firmware.c` SHA256 为 `33dd32a74266000618e72fa52b0a144ef3b77c2c037ba6b2ee6f3c82c8794746`。

本板候选构建 UserCode `0x00003BE9`，含 PL 屏控，文件为 `builds/20261017_040922_367174/impl/pnr/midi_keyboard.fs`，SHA256 `4a92abead4898f11b5347950cca35735ef196fee8893979e58360364fb16b3e5`。本次核验构建的69项输入、回归的149项输入和位流哈希均未变化。按此前记录，板上最后烧录的是 `0x00005A52`；本次检测并未将候选部署到板上。

目标 `LATEST_WORKSTATION.json` 记录板上 full85 / `0x00000085`，但它指向的 `results/song_guide_full85_clk50_20261007_084539_884006_route1` 在当前检出中缺失。`--current-workstation` 构建入口依赖的 `results/song_guide_full83_20261006_203125_607466` 也缺失，而且该入口从冻结工程复制固件，不覆盖为活动 `firmware.c`。因此本报告**不能证明板上 0x85 与本次检测的活动源码一致，也不能声称已复现完整 138K 构建**。根 README 的旧 P28 说明未作为当前版本依据。

## 兼容性结果

| 接口/能力 | 结果 | 原因或限制 |
| --- | --- | --- |
| USB 角色 | 匹配 | 138K J18 USB-A 为 Host，本板 USB2 为 Device |
| USB 速度 | FS 下匹配 | 138K 仅 12 Mbps；本板支持回落 Full Speed，不会直连运行 480 Mbps |
| 设备识别 | 交叉测试通过 | FB9A:FB9B 进入 generic MIDI，实际124字节配置被完整扫描 |
| MIDI 端点 | 交叉测试通过 | 选中 IF1 / Bulk IN81 / MPS64，跳过 IF0 AudioControl 和 IF2 vendor |
| A–P 音符、力度、松键 | 交叉测试通过 | 默认48–63；NoteOn 力度0按 NoteOff 处理 |
| 滑条 MOD / EXPR / PITCH | 数据兼容 | CC1 / CC11 / Pitch Bend 与目标乐器控制一致 |
| Program Change | 可接收，音色语义有差异 | 138K 将128个编号归入5个 profile，并非128个独立音色 |
| MIDI 通道 | 可接收，合并处理 | 全部通道和 cable 汇入一个 instrument，无通道独立音色 |
| Channel Pressure、系统消息 | 不支持转发 | 138K忽略；目前本板正常演奏路径不依赖这些消息 |
| 138K→本板 MIDI 引导灯 | 未接通 | generic 模式没有 MIDI OUT01 发送路径 |
| 本板演奏→138K 跟奏判定 | 未接通现有 Push guide 路径 | generic 事件进入音频 FIFO，但未进入 `push2_score_guide.played_valid` |
| 138K→本板屏幕 | 不兼容 | generic 模式完全跳过屏幕；Push 协议与 PL 不同 |
| 长按 E1 设置覆盖、退出重画 | 本板已有，138K未适配 | 目标没有 PL 状态读取、manual/redraw处理和心跳 |
| 两编码器控制目标菜单 | 尚无通用双向 UI 协议 | 本板 PL 当前只实现握手、健康和像素消息；不能把规划中的 UI_ACTION 当成现有能力 |

138K 的 Program 分组为：0–7→钢琴/profile4，8–15→马林巴/profile3，40–47→弦/profile1，56–63→铜管/profile2，其余→笛/profile0。目标 Bend 使用 `{MSB,LSB[6]}` 的256档近似；本板滑条按8 bit位置左移6发送，保留了本板现有滑条分辨率。

本板接收主机 NoteOn/Off 后能点亮相应按键灯；主机需使用本板当前选中通道，以及 `48 + transpose` 起的16个音符。目标目前没有发出这些数据。若要实现“目标发引导、按对后推进曲谱”，需要同时补齐发送反馈与接收演奏的 guide 事件入口。

## 屏幕为何不能直接互通

| 项目 | 本板 PL local-v1 | 138K 当前 Push 输出 |
| --- | --- | --- |
| USB 承载 | IF2，OUT02 / IN82 | 只对 Push VID/PID 启用；屏幕 EP1 OUT |
| 帧头 | `50 4c`、version1、session、seq、length，16B | `ff cc aa 88` + 12B零 |
| 画面 | 428×142，紧凑矩形 tile | 960×160，1024像素行跨度/填充 |
| 像素 | RGB565，小端，≤248像素/tile | 交替 XOR `f3e7` / `ffe7`，每帧640×512B |
| 接收确认 | CAPS、ACK/BUSY、FRAME_END/DRAWN | 只有 USB 传输 ACK/NAK，无 PL 应答 |
| 保活 | 250ms超时；建议50–100ms HEALTH | 1000ms重发整幅 Push 图 |
| 设置覆盖 | manual/redraw 标志；恢复需整页重发 | 没有对应处理 |

从目标生产 `frame()` 捕获的实际帧头为 `ffccaa88000000000000000000000000`；交给本板生产 PL 解码器，得到 `invalid PL magic`。相同红、绿、蓝 RGB565 像素，本板字节为 `00 f8 e0 07 1f 00`，目标 XOR 公式结果为 `e7 0b 07 f8 f8 f3`。后者是根据活动 RTL 公式计算的对比，不是目标像素 RTL 的仿真结果。

目标 `DISPLAY_DATA_LAYOUT_V1.md` 描述内部 DDR ABI，并明确未增加 USB 外部协议；不能把内部显示描述符作为已实现的 PL 接口。原始 `gowin_接口.zip` 为参考规划，本板本轮落地的是明确补充的 PL local-v1，目标工程尚无此适配。

428×142×2 = 121,552B/帧。全屏60fps仅像素就需58.34496Mbps，超过当前138K Host的12Mbps。即使忽略所有 USB 和协议开销，像素上限也只有约12.34fps；实际更低。当前 PL 客户端默认62×4分块，共252块，含请求头、tile元数据和FRAME_END需要129,640B OUT/帧，尚不含心跳、应答及USB开销。应采用变化区域更新；本板本地60Hz快照与区域刷新是另一条独立路径。

## 已执行的交叉测试

1. Icarus 仿真真实 `midi_performance → usb_midi_codec`，再追加 codec 边界输入。共2,052个线上4字节包：16个通道 A–P 按下/松开，三种滑条模式的全部0–255位置，Program、48条panic，以及通道消息和系统消息边界。
2. 将上述包送入未修改的目标生产 `firmware.c`，只 mock USB与MMIO。2,052包分别经过直接转换、逐包轮询、重复DATA PID及最多64B组包。1,978包正确写入MMIO54；64个 Channel Pressure 和10个系统消息按预期被忽略。来自正常 performance 路径的1,594包全部支持。
3. 保留目标现有 transport-mock 回归，替换为本板实际124字节 FS 配置。通过128×128音符/力度组合、动态端点/MPS/alternate、描述符拒绝边界、NAK保持、重复PID及超时断线；AddressSanitizer/UndefinedBehaviorSanitizer无错误。
4. 实际 HS 配置中的 MPS512 被 FS walker 拒绝，符合目标速度限制。generic 模式调用灯光/屏幕/OUT入口后，USB OUT 次数保持0。该测试确认软件选择逻辑，不模拟 USB 枚举控制传输或 PHY 握手。
5. 本板生产 PL 工具的 HELLO、RGB tile 编解码和252块完整覆盖检查通过；目标生产 Push 帧头被明确拒绝。

原始向量、生成器/测试源哈希、目标源哈希、编译日志及执行结果均已保存。无需重新运行整板布局布线即可复现此检测；未改生产 RTL、tools、sim 或 config。

## 最小适配工作

1. **138K设备分支**：新增 GW25K 类型，按描述符发现 MIDI IN81、MIDI OUT01、vendor OUT02/IN82；保留 Push 分支。各方向各端点维护独立 DATA toggle；新设备严格遵守 FS MPS64，长PL消息按字节流分片。
2. **PL发送器**：实现 HELLO/CAPS、control/display独立seq、完整响应解析、BUSY同seq重试、FRAME_END/DRAWN。不能将USB ACK当成绘制完成。参考本板 `tools/panel_display.py`。
3. **渲染适配**：从现有乐器状态生成428×142布局或明确缩放裁剪；输出紧凑RGB565LE，移除Push行填充与XOR。先用红绿蓝向量核对颜色；使用变化区域和背压。
4. **页面与保活**：50–100ms HEALTH；读取manual/redraw标志。设置覆盖期间暂停像素，返回后整页重画。USB复位或会话失效重新HELLO。
5. **跟奏与反馈**：将generic有效NoteOn接入guide；将目标引导音符转换为本板通道/音域的标准MIDI，经OUT01发送，附完整NoteOff与panic清理。
6. **构建绑定**：恢复可追溯的full83/full85源，确保 `--current-workstation` 真正纳入新增Host固件/RTL。当前入口仅覆盖部分audio/render/scope，单改活动firmware并不能证明固件进入最终位流。

## 复现和证据

在本板工程目录执行（只生成本板兼容性目录和reports，不访问硬件）：

```sh
python3 compatibility/gowin_synthesizer/run_packet_vectors.py
python3 compatibility/gowin_synthesizer/run_compatibility.py
```

- [结构化结果](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD/reports/compatibility_gowin_synthesizer_20261017/result.json)
- [C交叉测试日志](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD/reports/compatibility_gowin_synthesizer_20261017/native_test.log)
- [RTL向量报告](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD/compatibility/gowin_synthesizer/generated/packet_vectors_report.json)
- [目标描述符选择及MIDI转换](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer/migration/gw138k_audio/push2_workstation/usb_a/firmware.c:58)
- [目标通用模式禁止OUT](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer/migration/gw138k_audio/push2_workstation/usb_a/firmware.c:167)
- [目标Push屏幕输出](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer/migration/gw138k_audio/push2_workstation/usb_a/firmware.c:235)
- [目标guide与generic事件分流](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer/migration/gw138k_audio/push2_workstation/usb_a/rtl/push2_usb_a_control.sv:119)
- [目标冻结构建入口](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/Mega_138K/Dev/Gowin_Synthesizer/migration/gw138k_audio/push2_workstation/usb_a/tools/build_current_workstation.py:59)
- [本板PL协议](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD/docs/PANEL_DISPLAY_PROTOCOL.md)
- [本板接收引导音符](/Users/zhaojiying/Library/CloudStorage/飞牛同步-云工作空间/GW_25K/example/MIDI_KEYBOARD/rtl/instrument/midi_keyboard_application.v:88)
