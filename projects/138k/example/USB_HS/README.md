# USB HS：自制 138K Host 与热插拔

## 已跑通的程序

参考候选 **`C11030A2`**：实际 Push 以 HS 枚举，拔插后恢复 HS 和 MIDI 接收；恢复阶段可从 JTAG 观察。位流身份及前后采样见 [`verification.md`](verification.md)，机器可读身份见 [`module.json`](module.json)。

## 源码就在这里

- [`rtl/`](rtl/)：USB3300 初始化／链路、ULPI、MAC、Host 控制器、MMIO／CPU 桥。
- [`firmware/`](firmware/)：原生 Host C 驱动、CPU port、业务 backend。
- [`firmware.c`](firmware.c)：现有 Push／25K 业务固件；[`top.sv`](top.sv)：A2 使用的 headless 热插拔诊断顶层。
- [`driver.py`](driver.py)：原有 `prepare / build / audit / capture` 工具，不是新 builder。
- [`pinout.json`](pinout.json)：自制板引脚依据；[`device_25k/`](device_25k/)：配套 25K 键盘源码及其独立固件记录。

全部为仓库内相对链接。后续修改直接作用于现有唯一实现，不维护例程专用副本。

## 离线检查与准备

从仓库根目录执行：

```sh
python3 example/CUSTOM_138K/check.py --module USB_HS
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_host_probe.py
export PYTHONPATH="$PWD/projects/138k/push2_workstation/usb_a"
python3 example/CUSTOM_138K/USB_HS/driver.py prepare \
  --output /tmp/custom138k-usb-hs-NEW \
  --netlist-dir /path/to/locked-netlists --user-code NEW8HEX
```

将 `NEW8HEX` 替换为新的八位十六进制 UserCode。`prepare` 只准备输入；`build` 才综合／P&R，`capture` 会访问板卡，不属于目录检查。

## 装配边界

保留原输入 owner、会话失效与 PANIC、18 位事件和唯一参数提交点。Push／25K 交替接同一 USB-A；A2 参考候选无 HDMI、音源或 BLE，接入整机后另做用户验收。

`attempts` 是 PHY ready 上升沿次数，包含空口轮询，不能等同握手失败次数；真实连接看当次 CPU 枚举及 HS 状态。

已知本机 A2 工程：`~/.cache/fpga-usb2-hdmi/138k-push-recovery-c11030a2-20261030_001519/`，含原 manifest、位流、检查点和捕获，不随 Git 提交。
