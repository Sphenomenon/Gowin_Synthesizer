# G/H 与滑条误触诊断

## 已确认的现象

用户确认：只滑动滑条、不碰 G/H，也能稳定让电脑收到 G/H 音符；把 LAMP 调为 0、确认按键灯和滑条灯都熄灭后，误触仍存在。这排除了“只有显示高亮”的解释，也使 LED 开关噪声不足以单独解释现象。

板级软件中，U1 为 16 键触摸芯片，U2 为独立 I²C 总线上的滑条芯片，两者地址同为 `0x0d`。按键位图与滑条位置有各自的数据路径；G、H 分别来自 U1 原始通道 9、15。现有代码检查尚未提供把 U2 位置直接变成这两个音符的证据。软件路径独立不代表电极、电源、地线或两芯片采集时序不存在耦合；目前不能宣称已定位硬件根因。

## 诊断固件接口

诊断固件增加只读 `GET_TOUCH`（`0x02`）以及显式的 `SET_TOUCH_TEST`（`0x12`）。格式详见 [SCREEN_PROTOCOL.md](SCREEN_PROTOCOL.md)。接口不屏蔽 G/H、不修改灵敏度、不重新校准，也不改演奏参数。

U1 在完整成功采集结束时一起发布字 0、1、2、3，并递增字 6。字 0 为稳定滤波后的原始通道位图及 U1 状态；字 1 为 signal/reference 采集前后芯片原始触摸状态；字 2、3 为 G/H 的 signal/reference。工具在整组读取前后检查字 6，计数变化则重试，防止拼接两帧数据。字 4 是 U2 位置/状态，字 5 是实时 ready、pause、错误标志，不与 U1 帧保持原子一致。采集失败保留上一成功 U1 帧，因此还要检查帧计数是否持续前进及错误标志。

`delta = reference − signal` 是带符号整数差值，不作 uint16 回绕。CSV 同时保留原始 8 个 uint32 诊断字；不能只凭某一个差值就认定芯片已触发，需要结合前后原始 detect 位、稳定滤波后的 accepted 位及采集时序。

## 主机工具

使用系统 Python 和 `/opt/homebrew/lib/libusb-1.0.dylib`，无需 pip 包。工具认领 USB `fb9a:fb9b` 的 interface 2，用 endpoint `02/82` 收发 16 字节协议帧。请求和响应均检查 CRC、版本、opcode、sequence、status；超时或协议错误立即停止，释放 interface 和设备句柄，不自动复位设备或写配置。

在工程根目录执行：

```sh
python3 tools/touch_probe.py status
python3 tools/touch_probe.py capture --seconds 20 --period-ms 40 --output reports/touch_normal.csv
```

`status` 和 `capture` 仅执行只读请求。capture 输出 CSV 及同名 `.summary.json`，包括 UTC 时间、相对时间、协议请求序号、帧计数、全部原始字、G/H signal/reference/delta、采集前后 detect 位、accepted 位、滑条位置、ready/pause/error 标志。摘要统计样本数、G/H 检出/接受样本数和差值范围；这些是采样统计，不是每次触发边沿计数。若发生传输错误，已写入的样本仍保留，摘要记录错误，程序返回非零。运行 `--help` 不加载 libusb 或访问硬件。

## U2 采集暂停 A/B 测试

在正常状态与暂停状态分别采样，保持手的位置、滑动范围和电源条件一致。建议正常状态先记录约 5 秒无人触摸，再只滑条约 10 秒，最后恢复无人触摸。另行记录测试动作对应的时间段，CSV 不会自动推断手指动作。

```sh
python3 tools/touch_probe.py pause 1
python3 tools/touch_probe.py capture --seconds 20 --period-ms 40 --output reports/touch_u2_paused.csv
python3 tools/touch_probe.py pause 0
python3 tools/touch_probe.py status
```

`pause 1` 的协议应答只表示请求已接受。工具随后轮询字 5 的 bit 4，等待前端将 U2 LP 寄存器 12 写为 0、读回确认后才报告暂停完成；此时 slider ready 应为 0，U1 按键继续正常采集。`pause 0` 等待 LP 恢复为 1、读回确认和稳定等待完成，并且 slider ready 为 1、slider error 为 0 后才报告恢复完成。暂停仅用于隔离采集作用，手指与滑条电极仍存在物理耦合。

工具不会在 capture 结束或异常后自动改变暂停状态。测试结束显式执行 `pause 0`，并确认恢复成功。USB 控制会话重置/断开及 FPGA 复位会清除暂停请求；因此暂停与采样之间应保持 USB 连接。若这期间设备断开，重新连接后先用 status 确认实际状态。

结果判断依赖证据：

- 正常采集时 G/H 的原始 detect 与 delta 均随滑条动作变化，暂停后消失：说明 U2 主动采集与误触有相关性，需进一步检查采集同步和板级耦合。
- 暂停后仍出现同样变化：继续检查电极邻近、走线、地/电源回流和 U1 参数；不能据此断定是纯软件问题。
- 原始 detect 未变化而 accepted 或 MIDI 出现音符：继续沿稳定滤波、通道映射、事件排队与 MIDI 发送路径定位。
- 帧计数停滞或 error 非零：本次对比不能作为健康采集下的结论，先处理采集故障。

工具开发阶段仅完成离线验证：参数解析、诊断字解析、差值/标志、模拟 coherent 读取、错误 opcode/sequence/status 拒绝、CSV/JSON 输出。板上采样结果应随实际诊断固件版本和采集文件单独记录；本文尚无 A/B 实测结论。
