# 138K 直连电脑的 USB2 设备回环探针

这是独立诊断，不是工作站 USB Host 配置。电脑充当 Host，138K 的 USB3300 充当设备；目标是电脑实际以 **480 Mbit/s** 枚举，并完成逐字节双向回环。FPGA 的 ULPI 接口保持 **60 MHz**，不是把 FPGA 时钟改成 480 MHz。

## 设备实验的接线

138K USB2 的物理接口是 USB-A 母座，本探针却将其 PHY 配置为设备。不能因此把普通 A-C 线的 A 头插板、C 头插电脑，当成电脑 Host 到板卡 Device 的连接。

USB Type-C Cable and Connector Specification Release 2.0 的 §3.5.2、Table 3-13 规定：普通 A-C 线的 C 插头 CC 通过 56 kΩ Rp 接 VBUS。这种线用于 A 端 Host／Source 到 C 端 Device／Sink；按上述方向接入时，电脑 C 口看到的是 Source，而不是待枚举设备。初始 Source／DFP、Sink／UFP 的对应关系见 §2.3.3；普通 A-C 线不提供对端 USB PD 数据角色交换。

本次自供电板卡实验可使用以下受控数据连接：

```text
电脑 USB-A Host ── USB2.0 A-A 数据测试线 ── 138K USB2
                     D+、D−、GND 直通
                     VBUS／5V 断开
```

若电脑使用 USB-C，先接 C 转 A 母口的 Host／OTG 转接器，再接上述测试线。USB2 插座 VBUS2 经 F2 与板上 +5V 相连，所以保持现有独立供电，在测试数据线中隔离 VBUS，避免将板上与电脑的 5V 输出直接并联。数据线需保持 USB2.0 差分线对，不用松散探针线代替。

接线正确后先检查电脑新设备日志和原生 SE0，再判断 HS 握手、480 枚举与字节回环。仅有 `WAIT_RST`／FS J 不能跳过主机角色与接线检查而归因于设备协议。

## 来源与边界

- 顶层为本目录 `workstation_usb2_device_probe_top.sv`，构建入口为 `tools/workstation_usb2_device_probe.py`。
- 设备协议来自经哈希核对的 25K DA 冻结快照；准备阶段验证原清单的全部输入和位流，选取其中 USB RTL，不依赖完整工作站。
- FIFO、物理链路观察接口和原始事件统计显式选择当前第一方文件。`inputs.json` 分别记录当前 SHA256、冻结父 SHA256 和选择理由，不改写冻结文件或 vendor 字节。
- FIFO 的读写指针分别由本时钟域同步释放的复位控制，避免把异步公共复位直接释放到指针寄存器。
- 板级位置继续从锁定网表推导；ULPI 使用旁路后的 LVCMOS33，时钟在 C18、无内部上下拉。不修改外部网表或其它端口。
- 不包含 HDMI、DDR、CPU、音频或 USB Host；不改变工作站生产 profile，也不自动写 SRAM 或 Flash。

## 准备与构建

在 `projects/138k/push2_workstation/usb_a/` 下运行，使用新的候选目录和新的八位十六进制 UserCode：

```sh
python3 -m tools.workstation_usb2_device_probe prepare \
  --netlist-dir /path/to/locked-netlists \
  --peer-manifest /path/to/accepted-25k-da/acceptance/build.json \
  --output /path/to/new-candidate --user-code C11029D7
python3 -m tools.workstation_usb2_device_probe build /path/to/new-candidate
```

`build_result.json`、`audit.json` 分别保存工具运行和实际路由时序；不能只看 CLI 返回码。下载前必须确认 `audit.passed=true`、输入和位流哈希一致。SRAM 部署及独立身份读回单独保存，Flash 不在本工具的操作范围。

GAO ID 取 UserCode 低四位。时序仍要求 50 MHz 参考、60 MHz ULPI 和实际 USB3300 输入／输出延迟。异步 mailbox、Gray 指针和同步器仅在各自接收边界使用有界 max-delay／hold 例外，不整域屏蔽时序。

## JTAG 观察与实际回环

已部署对应候选后：

```sh
python3 -m tools.workstation_usb2_device_probe capture /path/to/candidate \
  --output /path/to/new-capture
python3 -m tools.workstation_usb2_device_loopback --events 4096 \
  --output /path/to/midi-loopback.json
```

采样工具核对读前、读后的芯片身份，互斥使用 JTAG；保留 1024 点原始 CSV、日志和解码结果。GAO 使用独立参考域，即使 ULPI 停钟也能采样。CSV 按实际的逐 bit 列读取，页面必须具有完整的四页、各八拍、相同 cohort／flags 和正确结束标记。

384-bit 观察总线的低 160 位保留原设备状态、应用层 MIDI／vendor FIFO 握手计数及自由运行参考计数；高 224 位为七个独立 mailbox：历史状态、原始／UTMI SE0 最长时间、RXCMD、原生接收字节、UTMI 接收字节以及链路 NXT。每个 mailbox 独立一致，七个 mailbox 不声称同一时刻原子采集。160-bit D4 的历史窗口仍可重放。

MIDI 和 vendor EP2 都直接回环，遵守 FIFO ready／valid 背压。应用握手计数不能证明 USB 数据已经到达电脑。电脑脚本先要求 sysfs 中产品为 `GW138K USB2 Loopback`、速率为 `480`、配置为 `1`，再通过本设备的 ALSA raw-MIDI 节点发送平衡 Note On／Off 并逐字节比较接收结果。默认 4096 个事件，不将小规模回环结果解释为峰值吞吐量。

若停在 `WAIT_RST`、FS J 状态且原始与 UTMI SE0、接收字节均为零，先记录这是尚未收到电脑总线复位，不能记成 HS 握手失败或硬件验收通过。当前实验及部署身份见 `reports/USB2_DEVICE_PROBE_20261029.md`。
