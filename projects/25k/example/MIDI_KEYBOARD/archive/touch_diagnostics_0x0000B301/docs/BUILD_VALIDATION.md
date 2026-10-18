# 整机构建与验证记录

## 当前版本 0x0000B301：G/H 滑条误触诊断

2026-10-17 已完成诊断固件构建和Flash写入校验、重载与读回。新增U1完整成功帧的原始前后检测、G/H SIGNAL/REF及帧序号；USB只读查询和U2 LP=0/1暂停/恢复命令用于实板隔离，不修改阈值、不屏蔽G/H。60 Hz区域显示代码保留。根因与采样记录见 [TOUCH_CROSSTALK.md](TOUCH_CROSSTALK.md) 和 [诊断汇总](../reports/touch_crosstalk_20261017.json)。

- 位流：[midi_keyboard.fs](../builds/20261017_030218_654822/impl/pnr/midi_keyboard.fs)，7,339,285字节；SHA256 `94a588b5135d231ff50f0b045f8ac67d0fe25025b2c6ffc1d4a77319dd3bc1d2`。
- [构建清单](../reports/last_build.json)：65项输入哈希，综合/PnR通过。
- [完整回归](../reports/validation.json)：69项检查通过，29个HDL测试台、9项Python测试，输入124项哈希不变。
- Flash UserCode=`0x0000B301`、Status=`0x70022020`；USB配置1、480 Mbps。见 [固化记录](FLASH_PROGRAMMING.md)。

| 时序项目 | 结果 |
| --- | --- |
| setup / hold违规端点 | 0 / 0 |
| 最差setup / hold余量 | +1.334 / +0.181 ns |
| 最差recovery / removal余量 | +1.344 / +0.965 ns |
| 50 MHz / 60 MHz域Fmax | 58.448 / 65.225 MHz |

[时序报告](../builds/20261017_030218_654822/impl/pnr/midi_keyboard.tr) 与 [PnR报告](../builds/20261017_030218_654822/impl/pnr/midi_keyboard.rpt.txt)。时序通过不能代替板级电源/电极或SPI波形测量。

新增双总线隔离测试逐周期验证：U2位置/触摸及伪G/H状态不断变化、共享CHANGE常低或翻转时U1空闲无误键，真实G/H仍可同时按放。新诊断测试验证完成帧一致性、LP写入后读回才ack、暂停U2时U1仍采集、恢复、NACK及错误读回的恢复。应用测试另验证诊断命令不会改变演奏配置或遮蔽G/H。

显示引脚仿真仍为全部26动态区域11.539220 ms、全屏19.450840 ms、静态零传输。动态界面按60 Hz节拍更新；任意全屏60 fps受50 MHz SPI带宽限制。见 [显示架构](DISPLAY_60HZ.md) 与 [最新性能汇总](../reports/display_60hz.json)。

诊断固件烧录成功并不代表误触已修复；当前需要本板正常/暂停U2的手指滑动对照。前版显示优化证据保留在 [0x0000F054记录](BUILD_VALIDATION_0x0000F054.md)。

```sh
sh example/MIDI_KEYBOARD/run_sim.sh
sh example/MIDI_KEYBOARD/build.sh
```
