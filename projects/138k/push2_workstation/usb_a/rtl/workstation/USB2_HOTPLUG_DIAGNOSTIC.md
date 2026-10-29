# USB2 高速热插拔独立诊断

本配置用于快速定位 25K／Push 在同一个 USB-A 口交替接入时的枚举、初始化、事件和屏幕传输问题。保留现有 VexRiscv、生产工作站固件、USB3300／ULPI、HS／FS Host、输入 owner、会话围栏、Push LED／屏幕生成及传输，不另写一套 USB 协议。

需要同时保留已验证 D5 HDMI 并在电脑上查看 JTAG 状态时，使用 [D5 HDMI＋热插拔组合诊断](USB2_HDMI_DIAGNOSTIC.md)；本页的独立 USB 配置不变。

诊断顶层只有 15 个引脚：50 MHz、UART RX／TX 和 12 个 ULPI 信号。位置来自同一锁定网表解析结果；ULPI 明确采用旁路的 `LVCMOS33`。USB CPU 仍为 48 MHz，ULPI 为 60 MHz，事件消费／反馈仍为 76.8 MHz。不包含整机音频 DSP、DDR、CNN、HDMI、BLE、TF、LCD 或 AE350，因此不等待 DDR 校准或 HDMI 进度。

事件端是一直 ready 的 18-bit 观察器，记录接收拍数、生命周期拍数、取消拍数及最后一个事件。反馈的 held-note 区域放入事件计数测试图样，其余反馈为零；它用来保留并观察原生音频→USB 快照路径，不表示真实发声或音符保持状态。Push 本机屏幕的 USB 传输仍保留，板载 HDMI 由独立显示配置调试。

## 准备与实现

从仓库根目录执行，输出路径必须不存在；修改 RTL、固件或约束时使用新的 UserCode。

```sh
OUT="$HOME/.cache/fpga-usb2-hotplug/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT-tmp"
export TMPDIR="$OUT-tmp"
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-usb2-soc --usb2-component workstation-hotplug \
  --usb2-firmware-profile workstation \
  --netlist-dir "$HOME/Documents/fpga补充文档" \
  --usb2-soc-output "$OUT" --user-code C127E205
gw_sh "$OUT/implementation.tcl"
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_usb2_hotplug "$OUT"
```

`synthesis.tcl` 只综合，`implementation.tcl` 综合后布局布线。`hotplug_inputs.json` 绑定顶层、完整输入与暂存哈希、子组件清单、锁定时钟来源、引脚和省略子系统。`component/component_inputs.json` 原样保留。审计入口检查暂存身份、引脚、时钟／PLL、原生 USB CDC、事件 FIFO、复位链、诊断复位合并别名和四类路由后时序，结果写入 `hotplug_audit.json`。

事件 FIFO 显式选择完整原生 resource-timing 配置所用的同一个注册 Gray 指针适配版本，放在独立 `support/` 路径；子组件内的旧副本和原清单不改写，也不参与编译。准备回归检查此选择及固定适配后哈希，避免只在完整工作站中修好 CDC、独立诊断仍使用旧 FIFO。

2026-10-28 的 `C127E205` 实际准备、综合和布局布线合计 **91.811 秒**；setup／hold／recovery／removal 最差裕量分别为 **0.771／0.194／9.576／0.261 ns**。来源、位流和验证范围见 [本轮报告](../../reports/USB2_HOTPLUG_DIAGNOSTIC_20261028.md)。回归和审计耗时另计。

FS 对照实验在另一新目录准备，加 `--usb2-full-speed-only`；不修改默认 HS 策略。

## 串口观察

调试 UART 为 115200、8N1，每秒约四次发送：

```text
U2 55324850 FLAGS SOF OUT_ERRORS IN_DIAG FRAMES COMMANDS MAPPED RECEIVED OWNER EVENTS LIFECYCLE CANCEL LAST_EVENT FAULT_ADDR CANCELED_REQUESTS
```

实际每个字段都是 8 位大写十六进制数，一行 16 个 word，结尾 CRLF。`55324850` 是诊断签名 `U2HP`，不是 FPGA UserCode。每一行在发送前锁存；音频侧计数与 ULPI 侧 SOF／状态分别通过原子快照到达 CPU 域。

| 字段 | 含义 |
|---|---|
| `FLAGS[0..4]` | PHY ready、failed、HS、traffic enable、transaction reset released |
| `FLAGS[5..7]` | USB PLL lock、音频 PLL lock、owner connected |
| `FLAGS[11:8]` | 现有 CPU sticky fault 位 |
| `SOF` | 原 Host 的 SOF 计数 |
| `OUT_ERRORS`～`OWNER` | 原样输出七个 telemetry word；含 IN 错误／重复／NAK／断连计数、Push 帧／命令和输入计数 |
| `EVENTS`／`LIFECYCLE`／`CANCEL` | 接受的事件拍数及其中的生命周期／取消拍数；不是连接次数 |
| `LAST_EVENT` | 最后接受的 18-bit 事件，原布局不变 |
| `FAULT_ADDR` | 原 CPU 最后故障地址 |
| `CANCELED_REQUESTS` | 原服务适配器累计取消请求数 |

## 迭代顺序

1. 先跑准备／UART 回归：`python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_hotplug_preparation.py`。
2. USB 行为用 `sim/test_workstation_usb2_hotplug.py` 的 HS／FS 交替用例；完整 Push 帧有单独用例，不需要带实际 DSP。
3. 独立诊断中修改已有 USB owner、驱动和固件，继续由原生产模块承载修复，不把业务移到诊断顶层。
4. 独立 USB 和 HDMI 各自稳定后，再合并到完整工作站，执行真实音频混合热插拔及整机验证。诊断程序不替代整机配置。

ULPI 外部 IO 延迟仍需补齐。回退本配置只需不再选择 `workstation-hotplug`；已有工作站与 HDMI 配置不切换。
