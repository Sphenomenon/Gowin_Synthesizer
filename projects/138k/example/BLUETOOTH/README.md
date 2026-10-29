# 蓝牙：自制 138K 的 RTL8723DS 业务链路

## 已跑通的程序

参考候选 **`C11027C1`** 的实板业务 GATT、会话／重连、短录音与下载校验通过，依据 [`verification.md`](verification.md)。它不是旧版 FFF0／BTST 通知诊断；参考位流身份见 [`module.json`](module.json)。

## 源码就在这里

- [`driver.sv`](driver.sv)：`workstation_bluetooth` 工作站接入层。
- [`assembly.py`](assembly.py)：真实 vendor／协议选择、哈希检查和 staging；以它为当前业务链的来源入口。
- [`protocol/`](protocol/)：复用的 `RTL8723DS_PROTOCOL` 业务、GATT、可靠下载及主机检查工具。
- [`transport/`](transport/)：原始 RTL8723DS UART／H5／HCI／补丁输入，原始字节及许可证不改。
- [`wiring.json`](wiring.json)：自制板 FPC 接线。
- [`bringup/`](bringup/)：原始独立 BLE／Wi-Fi 板级诊断，仅作链路参考；不拿它替换当前业务服务。

## 离线检查与原有综合入口

```sh
python3 example/CUSTOM_138K/check.py --module BLUETOOTH
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_bluetooth.py
```

以下是原有的整机准备与 BLE 分量综合入口，仅作后续操作参考，本次不执行：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --prepare-custom-board \
  --custom-board-output /tmp/custom138k-ble-inputs-NEW \
  --netlist-dir /path/to/locked-netlists
python3 example/CUSTOM_138K/BLUETOOTH/synthesize.py \
  --stage /tmp/custom138k-ble-inputs-NEW/workstation/Prj1 \
  --output /tmp/custom138k-ble-synthesis-NEW
```

第二条仅综合 BLE，不做完整工作站 P&R，也不部署。所有输出使用新目录。

## 装配边界

保留原业务线协议及 115200→921600 初始化策略。PCM 来自最终 FPC/I2S 输出链的既有取样点，不能另建参数真值。C1 记录的非静音内容、长录音及整机并发范围按原报告处理，不能将目录分类变成新的验收。

已知本机参考产物：`projects/138k/push2_workstation/usb_a/out/resource_a26_C11027C1/`；原始物理工程为 `out/workstation_resource_a26_20261027_c1_physical/`。位流及实现数据库不入 Git。
