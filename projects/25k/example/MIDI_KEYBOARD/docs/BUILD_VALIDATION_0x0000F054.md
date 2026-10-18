# 整机构建与验证记录

验证日期：2026-10-17（Asia/Shanghai）。顶层 `midi_keyboard_top`，器件 `GW5A-LV25MG121NC1/I0`，Gowin V1.9.12.03。

## 历史版本 0x0000F054

显示改为60 Hz场景快照和变化区域更新，采用50 MHz连续SPI、四像素预取FIFO及26个动态矩形。静止场景不发送像素；全屏重画保持同一快照至批次完成。横屏方向和界面布局保留。架构、坐标和带宽边界见 [DISPLAY_60HZ.md](DISPLAY_60HZ.md)。

- 位流：[midi_keyboard.fs](../builds/20261017_015947_664453/impl/pnr/midi_keyboard.fs)，7,232,301字节。
- SHA256：`07f2c363b463982f3ea7ed300603267951c2e03225a4d0bb105e285faa87d1c4`。
- [构建清单](../reports/build_20261017_015947_664453.json)记录64项输入哈希；综合、布局布线和回归均成功，烧录前再次核对源码与位流哈希。
- 板载Flash已写入校验并重载，UserCode=`0x0000F054`，Status=`0x70022020`，见 [Flash固化记录](FLASH_PROGRAMMING.md)。

## 显示性能

| 项目 | 最终源码RTL引脚仿真结果 |
| --- | --- |
| 连续动态场景节拍 | 16.666660 / 16.666680 ms，平均60 Hz |
| 26个动态区域全部变化 | 11.539220 ms，35,860像素 |
| 428×142全屏重画 | 19.450840 ms，60,776像素 |
| 静态场景 | 0窗口、0像素传输 |

全屏RGB565在60 fps下仅像素就需要58.345 Mbit/s，超过50 MHz单线SPI容量。因此60 Hz结论适用于当前动态界面区域；首次、主题和背景变化会跨过一个节拍，`overrun_count`记录错过的tick。没有将RTL仿真结果当作实屏扫描帧率或TE实测结果。

## 时序与回归

| 项目 | 结果 |
| --- | --- |
| setup / hold违规端点 | 0 / 0 |
| 最差setup / hold余量 | +0.746 / +0.186 ns |
| 最差recovery / removal余量 | +3.356 / +0.892 ns |
| 50 MHz域Fmax | 58.646 MHz |
| 60 MHz ULPI域Fmax | 62.815 MHz |

详细 [PnR报告](../builds/20261017_015947_664453/impl/pnr/midi_keyboard.rpt.txt) 与 [时序报告](../builds/20261017_015947_664453/impl/pnr/midi_keyboard.tr)。四路ODDRC直接连接输出；CS使用INIT=1和独立流水守卫，复位清除SCK并等待CS释放后再接收字节。50 MHz MOSI名义setup/hold各10 ns，外部引脚波形与板级裕量仍需实测。

[完整回归清单](../reports/validation_restore_0x0000F054.json)与[日志](../reports/simulation_restore_0x0000F054.log)记录65项检查全部通过：27个HDL测试台、USB额外FS模式、BLE错误ROM模式、9项Python协议测试、顶层Verilog-2005 elaboration、描述符与参考完整性检查。回归输入121项哈希保持一致。

- SPI测试通过连续1024字节、8191个连续20 ns采样间隔、停顿、DC切换、末字节释放及长短复位恢复；本地与原厂Gowin原语模型均通过。显式检查idle不能早于物理CS释放。
- 显示测试逐引脚解码55窗口、194,172个RGB565像素，覆盖全部动态区域、全屏、静态零流量、四级渲染预取、快照一致性和超时计数。
- 区域测试覆盖全部输入字段、16键、64种focus转换、主题/背景全屏，以及未抓取快照时实时输入不污染比较。
- 其它MIDI、触摸、USB/BLE和灯光回归通过；本轮仅完成显示优化，不扩展此前触摸排查结论。

[性能与构建烧录汇总](../reports/display_60hz.json)集中记录证据。Flash重载后附带观察到USB设备`GW25K MIDI Screen`、配置1、480 Mbps；未做实际断电、板级SPI波形、TE或屏幕效果测量。

## 历史记录与复现

前一版`0x0000856D`使用12.5 MHz字节SPI，整帧快照约10.73 fps；其当时USB未枚举等结果保留在 [历史验证记录](BUILD_VALIDATION_0x0000856D.md)，不能代替当前证据。

```sh
sh example/MIDI_KEYBOARD/run_sim.sh
sh example/MIDI_KEYBOARD/build.sh
```

失败构建与探测日志均保留，最新成功固件由`last_build.json`和`last_program.json`关联。
