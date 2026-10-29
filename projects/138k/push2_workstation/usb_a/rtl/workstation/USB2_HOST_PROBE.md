# 138K Host／25K Device 独立探针

用途是直接调试 138K USB2 与 25K USB2 的复位、chirp、枚举和通信。138K 为 Host，25K 保持已有完整设备固件；这不是直连电脑的 USB Device 回环探针。

## 来源与范围

- 复用 `tools/workstation_usb2_hotplug.py` 的原生 `workstation_usb2_hotplug_top`、USB CPU、生产工作站枚举固件和输入适配器。不复制整机工程，不切换 accepted profile。
- 不包含 HDMI、DDR、DSP、CNN 或 BLE；音频域仅保留事件受理计数，不表示真实声音输出。
- 球位仍由锁定网表推导，旁路 ULPI 使用 LVCMOS33，C18 显式 `PULL_MODE=NONE`。
- 时钟保持 50 MHz 参考、60 MHz ULPI、48 MHz USB CPU 和 76.8 MHz 事件消费域。USB3300 输入／输出延迟与原生 CDC 约束合并为一个实际使用的 SDC，不降低 ULPI 频率或屏蔽整域。
- 构建只生成新候选，不下载 SRAM 或 Flash。用户授权的 SRAM 下载必须另存写前设备身份、位流哈希、编程验证和写后独立身份；不操作 25K，也不写 Flash。

## 原生链路时序修复

Host 控制器使用提前一拍的包尾提示生成寄存器 STP；最后一个字节仍按原有 NXT 握手接收，不在 ULPI 数据流中插入流水气泡。MAC 的字面量／负载选择、发送有效状态，以及端口的正常通信／chirp 状态在状态迁移时注册，避免多级状态译码直达引脚。NOPID chirp 结束最多多一个 ULPI 周期。

STP 寄存器使用汇总故障信号异步置位，保留时钟停止、初始化失败、端口失败和 MAC 故障时拉高 STP 的保护；正常 STP 直接由寄存器驱动。默认底层链路模式保留原有接口时序，原生 Host 控制器显式启用寄存器模式。这些变化不修改 USB 线协议、18 位事件布局或 accepted 整机来源。

## 使用

在 `projects/138k/push2_workstation/usb_a/` 中运行：

```sh
python3 -m tools.workstation_usb2_host_probe prepare \
  --netlist-dir /path/to/locked-netlists \
  --output /path/to/new-candidate --user-code C11029A3
python3 -m tools.workstation_usb2_host_probe build /path/to/new-candidate
python3 -m tools.workstation_usb2_host_probe capture /path/to/new-candidate \
  --output /path/to/new-capture
```

`host_probe_inputs.json` 绑定原生准备清单、GAO、实际运行脚本和合并时序约束；原生清单保留冻结来源和逐文件输入哈希。`host_probe_audit.json` 保留实际路由时序、PLL、CDC、复位和球位检查。路由时序不闭合时构建返回失败，不部署失败候选。

GAO core0 在 ULPI 域采集端口状态历史、失败历史、Function Control、收发及 SOF 峰值；core1 在 CPU 域采集真实 owner 分类、事件计数、错误和毫秒计数。两核分别前后一致，不声称跨核原子采样。端口峰值是自全局复位以来单次尝试的最大值，不是多次尝试之和。

设备 chirp、HS active 和 SOF 表示不同阶段；只看到这些值不宣称枚举完成。CPU 侧必须实际提交 connected／generic MIDI／GW25K，且无 CPU fault，才记为识别 25K；真实 MIDI 事件计数另记，不能把旧镜像的累计计数归到本次候选。

本探针是独立实验入口。稳定修复仍需进入所属原生模块，运行真实 25K／Push 热插拔和整机来源回归，再以完整工作站的新候选单独验收；不得把本探针作为长期生产输入。

2026-10-29 的候选身份、时序、SRAM 下载及板间 FS 枚举证据见 [实测记录](../../reports/USB2_HOST_PROBE_20261029.md)。
