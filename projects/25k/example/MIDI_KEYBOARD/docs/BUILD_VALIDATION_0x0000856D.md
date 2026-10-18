# 整机构建与验证记录

验证日期：2026-10-17（Asia/Shanghai）。顶层 `midi_keyboard_top`，器件 `GW5A-LV25MG121NC1/I0`，Gowin V1.9.12.03。

## 历史版本 0x0000856D

完整参考工程与手册对照后，修复共享CHANGE绕过轮询间隔、配置后首帧RESET被忽略两处问题，加入U2滑条独立诊断，并将LCD SPI从5 MHz提高到12.5 MHz。保留已确认的A–P映射、WS灯序、PCA滑条灯及反向横屏。

- 位流：[midi_keyboard.fs](../builds/20261017_010056_274646/impl/pnr/midi_keyboard.fs)，7,018,285字节。
- SHA256：`4e8a93557693e76a241cdf70a23e5a1dcc5afd2f6ff743eb8fe22ca49f2812a3`。
- [构建清单](../reports/last_build.json)记录62项构建输入哈希，综合与布局布线分别在新进程内完成；构建、回归和烧录预检均确认输入未变化。
- Flash已完成operation54写入校验、operation1重载；两次读回UserCode=`0x0000856D`、Status=`0x70022020`。本轮USB2数据设备未被macOS识别，尚未完成新版本枚举核验，见 [Flash固化记录](FLASH_PROGRAMMING.md)。

## 时序与构建

| 项目 | 结果 |
| --- | --- |
| setup / hold违规端点 | 0 / 0 |
| 最差setup / hold余量 | +0.934 / +0.215 ns |
| 最差recovery / removal余量 | +5.585 / +1.068 ns |
| 50 MHz域Fmax | 59.293 MHz |
| 60 MHz ULPI域Fmax | 63.564 MHz |

详细 [PnR报告](../builds/20261017_010056_274646/impl/pnr/midi_keyboard.rpt.txt) 与 [时序报告](../builds/20261017_010056_274646/impl/pnr/midi_keyboard.tr)。USB3300输入/输出延迟及Gray首级约束参与实际PnR；异步外设只豁免首级采样路径。LCD/UART/I²C等外部引脚波形仍须实测。

工具检查完整BLE ROM内容与原manifest，禁止发布ROM漏载、负时序或构建期间输入变化的结果。源码保留相对ROM路径，仅ASCII暂存副本转换为绝对ROM路径。

## 仿真

[完整回归清单](../reports/validation.json)与[仿真日志](../reports/simulation.log)记录61项检查全部通过：25个HDL测试台、USB额外FS模式、BLE错误ROM模式、9项Python协议测试、顶层Verilog-2005 elaboration、描述符一致性与22个原参考文件校验。回归期间输入哈希无变化。

- 新增扫描保护测试通过真实开漏I²C从机验证：共享CHANGE持续低/频繁变化均不绕过最小起始间隔；无通知使用较慢fallback。独立检查生产默认16/20 ms，受控从机epoch中的单次位置尖峰不被重复读样确认。
- 上电RESET在配置前读取清除；CAL_WAIT中的额外RESET和reg20丢失被拒绝，报07并发布释放，随后重新写回滑条模式0x28。G、原始位置、OV锁存、成功计数及NACK保留诊断/恢复均验证。
- S2诊断经过独立字模像素、十进制/十六进制、状态颜色、四拍流水线及按帧快照检查。
- LCD在真实50 MHz时钟、默认12.5 MHz SPI下逐引脚检查CS/DC/MOSI建立保持、SCK高低及两整帧121,552像素；方向、GRAM窗口、RGB565高低字节与快照一致性通过。
- USB HS/FS、50/60 MHz跨域、BLE完整ROM-v2补丁及GATT、16键MIDI按放、编码器、panic、双链路恢复、PCA9685与WS2812等回归均通过。

LCD传输仿真测得整帧91.174480 ms；含生产2 ms间隔后快照周期93.174500 ms，10.732550 fps。旧5 MHz对照为209.877860 ms、4.764676 fps，约提升2.25倍。时钟、SPI及像素流水线未加速，仅启动/帧间毫秒等待被缩短后按生产参数还原；这不是实屏帧率实测。[实际RTL预览](../reports/midi_keyboard_preview_3x.png)已更新。

这些测试不能证明QT2160不同读样一定属于不同ASIC扫描，也不能代替实板抗扰、端到端演奏延迟、BLE连接、灯序和显示效果验收。当前USB枚举缺项如实保留。

## 历史版本

| UserCode | 内容与结果 |
| --- | --- |
| 0x00006712 | 完整A–P映射、NTHR12、12/10迟滞与滑条滤波；24测试台通过，setup/hold 0/0；Flash校验/重载及USB480 Mbps枚举已确认 |
| 0x00003D0B | WS灯序、PCA滑条灯、反向横屏与右侧滑条；当时未补全H–P；Flash校验/重载和USB480 Mbps枚举已确认 |
| 0x0000DF05 | 首次完整MIDI框架固化；Flash校验/重载及USB480 Mbps枚举已确认 |

历史构建目录保留，不能用历史枚举或测试结果替代当前版本证据。当前固化记录见 [FLASH_PROGRAMMING.md](FLASH_PROGRAMMING.md)。

## 复现

```sh
sh example/MIDI_KEYBOARD/run_sim.sh
sh example/MIDI_KEYBOARD/build.sh
```

前者需要Icarus与Python；后者需要Gowin及有效许可证。成功构建发布到新的时间戳目录，不覆盖旧固件；失败保留诊断记录。
