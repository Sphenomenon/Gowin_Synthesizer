# 整机构建与验证记录

## 当前版本 0x00005A52：Android配对与编码器响应

2026-10-17已补齐Android系统蓝牙配对所需的Legacy Just Works SMP，并将两个编码器方向反转、调节速度减半。源码、回归输入与位流哈希一致；新固件已写入板载Flash并校验、重载、读回。汇总见 [本轮记录](../reports/ble_encoder_20261017.json)。

此前固件忽略SMP固定信道CID6，本轮增加控制器LE Rand/LE Encrypt、c1/s1、STK加密握手、LTK请求及单个RAM bond。HCI命令信用与H5确认、ACL信用独立；错误/迟到结果不会恢复已终止的配对，命令超时进入既有5秒BLE复位流程。Android常见AuthReq=0x0D/0x2D可协商NoInputNoOutput的Legacy Just Works，不承诺MITM或Secure Connections。见 [蓝牙实现](BLE_IMPLEMENTATION.md)。

两个编码器均每两个机械卡位输出一步，方向与前版相反；正反半步相消，非法相位/复位清余量。A/B成对20 µs滤波与按键1 ms滤波保留。触摸、按键映射和显示RTL与F054一致；G/H排查保持停止。

- 位流：[midi_keyboard.fs](../builds/20261017_033415_116117/impl/pnr/midi_keyboard.fs)，7,178,789字节。
- SHA256：`91819e9d4c7971c9fb1b53144c3d5822e6ca0b7c100cbed4b9fe6b377e5aa73e`。
- [构建清单](../reports/build_20261017_033415_116117.json)：65项输入哈希，综合与布局布线通过。
- [完整回归](../reports/validation_0x00005A52.json)：31个HDL测试台、9项Python测试、73项检查通过，126项输入哈希无变化；[日志](../reports/simulation_0x00005A52.log)。
- Flash UserCode=`0x00005A52`、Status=`0x70022020`，USB配置1、480 Mbps；[固化记录](FLASH_PROGRAMMING.md)。

| 时序项目 | 结果 |
| --- | --- |
| setup / hold违规端点 | 0 / 0 |
| 最差setup / hold余量 | +1.107 / +0.184 ns |
| 最差recovery / removal余量 | +6.189 / +0.864 ns |
| 50 MHz / 60 MHz域Fmax | 52.929 / 68.841 MHz |

详细 [时序报告](../builds/20261017_033415_116117/impl/pnr/midi_keyboard.tr) 与 [PnR报告](../builds/20261017_033415_116117/impl/pnr/midi_keyboard.rpt.txt)。

## 行为验证与使用边界

新增SMP单元测试560项检查，覆盖独立密码学向量、正确/错误Confirm、随机bond、RPA地址变化重连、复位丢key、早到LTK、背压取消、乱序/长度/状态错误与超时。GATT集成测试从同步H5邮箱输入真实SMP/HCI包，逐字节核对35字节AES命令、独立信用与Android AuthReq协商，验证配对后原ATT/MIDI接口和断连重广播。编码器两项行为测试共400检查，含实际50 MHz默认滤波与反向半速。

配对记录仅保存在RAM：板卡复位/断电后，Android需要忘记旧的`GWK-MIDI`再配对；系统配对完成后还需在支持BLE MIDI的音乐应用中打开该设备并订阅CCCD，屏幕BLE才显示在线。用户已在Android实测确认“系统配对成功，MIDI 应用也能连接”。本次确认覆盖系统配对和应用连接；音符收发、长时间演奏及断电后行为尚未由该反馈验证。

显示引脚仿真保持26个动态区域11.539220 ms、全屏19.450840 ms、静态零传输。动态界面60 Hz节拍保留；未测实屏/TE扫描帧率。见 [显示架构](DISPLAY_60HZ.md) 与 [性能汇总](../reports/display_60hz.json)。前版恢复记录见 [F054验证](BUILD_VALIDATION_0x0000F054.md)。

```sh
sh example/MIDI_KEYBOARD/run_sim.sh
sh example/MIDI_KEYBOARD/build.sh
```
