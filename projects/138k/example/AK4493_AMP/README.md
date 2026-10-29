# AK4493／功放：独立发声验证与工作站 I2S 接口

## 已跑通的程序

修焊后用户确认 **CN 扬声器出声**，对应 `0x13802302`，见 [`speaker_verified.json`](speaker_verified.json)。后续左右交替／持续音诊断仍保存在原例程，不把不同身份及不同插座的记录合并成一次验收。

## 源码就在这里

- [`bringup/`](bringup/)：独立 AK4493 测试完整入口，包含 RTL、约束、测试音、GAO、主机工具和历史报告。
- [`driver.sv`](driver.sv)：待装配的 `workstation_fpc_audio`，接最终 PCM、主音量、复位与使能；不是测试音顶层。
- [`wiring.json`](wiring.json)：工作站按原网表审核的 FPC 接线与来源锁定。
- [`assembly.py`](assembly.py)：现有板级外设准备和映射，不产生另一份接口实现。
- [`clock_measure/`](clock_measure/)：K18／J19 音频晶振的实测依据。

独立已出声镜像与工作站流式接口分别列出；`driver.sv` 的整机装配仍等待用户验收。

## 离线检查

```sh
python3 example/CUSTOM_138K/check.py --module AK4493_AMP
python3 example/CUSTOM_138K/AK4493_AMP/bringup/tests/check_audio.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_fpc_audio.py
```

原有构建脚本、Tcl 和报告保留在 `bringup/`；其中历史本机路径按原记录保留。工作站装配使用 `driver.sv`，不是测试音顶层。

## 装配接口

工作站使用 FPC2.n → 功放 FPC1.(25−n) 反序映射，K18 12.288 MHz 直接作为 MCLK，BCK 3.072 MHz、LRCK 48 kHz，32-bit slot 中 PCM16 左对齐。主音量在既有权威提交／输出路径只应用一次；静音、失钟和启动顺序由现有接口负责，不因整理目录修改。

原镜像路径在 `bringup/reports/build_20261023_050730_086783.json` 中，属于历史另一台机器的本地构建，不是本机可下载文件。位流、Flash 及 SRAM 均未因本次分类而改动。
