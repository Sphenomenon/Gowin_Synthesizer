# 整机构建与验证记录

## 已构建、未烧录：0x00003BE9，USB2输入画面与本地设置

按用户确认，MIDI与屏幕数据都使用USB2。没有显示输入时保留原界面；首个有效RGB565像素块进入输入页。E1长按1秒进入并锁定设置页，再次长按解除锁定、等待主机重新输入；E2紧急停音始终有效。有效请求维持250 ms会话，静态画面需心跳，超时恢复本地完整重绘。详见 [协议与操作](PANEL_DISPLAY_PROTOCOL.md) 和 [本轮汇总](../reports/panel_display_20261017.json)。

**用户明确要求本轮先构建、暂不烧录，因此没有擦写、重载或USB实机屏控测试。板上最后已确认版本仍为0x00005A52。** [固化记录](FLASH_PROGRAMMING.md) 与 [上一版本验证](BUILD_VALIDATION_0x00005A52.md)保留。

- 位流：[midi_keyboard.fs](../builds/20261017_040922_367174/impl/pnr/midi_keyboard.fs)，7,124,921字节，UserCode=`0x00003BE9`。
- SHA256：`4a92abead4898f11b5347950cca35735ef196fee8893979e58360364fb16b3e5`。
- [构建清单](../reports/build_20261017_040922_367174.json)：69项输入哈希；综合、布局布线与时序通过。
- [完整回归](../reports/validation.json)：36个HDL测试台、25项Python测试、84项检查通过；149项输入哈希保持不变。[日志](../reports/simulation.log)。
- 新增tile接收暂存和在途显示缓冲均映射BSRAM，共2块；全工程31块BSRAM。

| 时序项目 | 结果 |
| --- | --- |
| setup / hold违规端点 | 0 / 0 |
| 最差setup / hold余量 | +0.405 / +0.184 ns |
| 最差recovery / removal余量 | +2.239 / +0.911 ns |
| 50 MHz / ULPI域Fmax | 51.034 / 69.090 MHz |

详细 [时序报告](../builds/20261017_040922_367174/impl/pnr/midi_keyboard.tr) 与 [PnR报告](../builds/20261017_040922_367174/impl/pnr/midi_keyboard.rpt.txt)。

## 行为验证

新增5个HDL测试台覆盖：短按释放/长按边界且无附带短按；MK/PL分片、合并、像素内魔数、输入残帧恢复及回复背压；会话/双通道序号/重复/长度/矩形边界；250 ms心跳及设置覆盖；FRAME_END只在实际tile完成后成功。软链路复位和换session期间在途RAM保持不变，新输入BUSY，旧SPI窗口完成后才释放。

实际模块集成仿真149项检查：首次有效像素才切页、无输入本地、静态心跳、超时回退、手动设置持续屏蔽、解除覆盖后需要新tile、MK控制共存；主机停止接收屏控回复超过超时仍保持字节，同时触摸USB NoteOn和E2全部48条panic消息继续工作。LCD未接收tile时FRAME_END立即BUSY，不消耗seq，心跳可继续。

引脚级测试解码真实ODDRC输出，覆盖两个旋转方向、同步RAM逐行像素重排、非原点非方形tile、非对称RGB565端序、首次清黑、静态零传输、切页完整窗口收尾、CS释放后tile_done，以及本地dirty=0时返回仍完整重画。原显示测试保持26个动态区域11.539220 ms、全屏19.450840 ms；60 Hz是本地动态界面快照节拍，不代表任意外部整帧或实屏扫描60 fps。

新增16项Python测试覆盖完整画面tile重建、PPM二进制解析、请求响应匹配、BUSY原序号重试与有界失败、超过600 ms启动等待、部分USB写入后的会话失效、设置覆盖与恢复整屏重传。工具仅依赖标准库和本机libusb：

```sh
python3 tools/panel_display.py demo --seconds 10
python3 tools/panel_display.py image input.ppm --seconds 30
```

以上命令在example/MIDI_KEYBOARD运行；当前板上旧固件尚不支持PL，需之后烧录本次位流再做实机验证。本轮没有实体主机应用联调、实屏图像/E1手势验收、断电或TE扫描测量。Android配对及BLE MIDI连接的用户确认属于上一已烧录版本；本轮保留相关RTL并通过回归，不替代新的实机验收。

```sh
sh example/MIDI_KEYBOARD/run_sim.sh
sh example/MIDI_KEYBOARD/build.sh
```
