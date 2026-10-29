# 138K 直连电脑的 USB2 设备探针：2026-10-29

本轮目标是电脑作为 Host、138K 作为 USB High-Speed 设备，实际完成 480 Mbit/s 链路枚举和双向回环，不是继续验证 138K Host 与 25K 的握手。用户授权编写、综合和 SRAM 下载探针；Flash 未写，原 E5 持久镜像保留。

## 当前部署

截至 15:56，本轮实际 SRAM 身份为 **C11029D8**，FPGA IDCODE 为 **0001081B**。下载前核对全部暂存输入、路由审计、位流和 E5 回退位流哈希，执行 SRAM Program and Verify，再独立读回身份。当前状态是 **等待电脑总线复位，尚未枚举，尚无实际 480 Mbit/s 双向传输结果**。

证据根目录：

```text
~/.cache/fpga-usb2-hdmi/138k-device-c11029d8-20261029_155037/
```

| 项目 | 实际结果 |
| --- | --- |
| 顶层 | `workstation_usb2_device_probe_top` |
| 综合／布局布线 | 15:50:37.997308～15:51:33.563106，55.566 秒 |
| setup／hold | +1.512 ns／+0.209 ns |
| recovery／removal | +7.061 ns／+0.285 ns |
| ULPI 要求／路由后 Fmax | 60 MHz／65.988 MHz |
| GAO | 独立 50 MHz 参考域，384 bit，1024 点，ID 29D8 |
| USB 设备描述符 | FB9A:FB9B，`GW138K USB2 Loopback`，序列号 C11029D8 |
| 应用行为 | MIDI EP1 与 vendor EP2 原样回环，遵守 FIFO 背压 |
| 连接时序对照 | PHY 初始化后先保持约 250ms 断开，再允许 FS attach |
| SRAM 下载／独立身份读回 | 15:53:11 完成，通过 |

| 文件 | SHA256 |
| --- | --- |
| `inputs.json` | `0fbf65e2fc92436faa8dff42e18e7ccd737948ee934ca91f696288ff1a6121d0` |
| `audit.json` | `2f7723a338f94390fe498b12472c4cc044dbfdceaa68ba01a01530d7f0247065` |
| `impl/pnr/ao_0.fs` | `a5c95b7a91ab17dbf4cfafe37469bbe502fc0455a1f12dd06f14ad64f74b848a` |
| `deployment/deployment.json` | `768fe2630b5276260b78b379bb8734bd66eb45c3452ccb49f7a977728c617119` |

## 板上读回

15:53:14～15:53:16 的原始窗口及其前后身份读回保存在 `deployment/capture_1/`，CSV SHA256 为 `038f3dbc2a056a424f04176204df02fdeb6058a4514f4f09fe73dee425aedc15`。

- PHY 初始化完成，stage=18／0x12，boot_error=0，ULPI 源时钟存活。
- ULPI 频率量化值 59.904 MHz；此前 D4 连续窗口为 59.904～60.160 MHz。该结果来自当前板上计数，不沿用夜间旧候选约 30 MHz 的历史结论。
- 状态为 WAIT_RST=1，线状态为 FS J=1；HS active=0，USB 地址=0，online=0。
- 原始 RXCMD 收到 1 次，最后值为 0D；原始和 UTMI 的已武装 SE0 最长持续时间均为 **0**，原生及 UTMI 接收字节均为 **0**。
- 历史状态位图=03，仅经过 IDLE、WAIT_RST，没有进入 device chirp 或 HS 状态。启动时的未武装 SE0 不计作电脑复位。
- MIDI／vendor 应用 FIFO 计数均为零。不能把这些零值解释为已经发生但失败的 USB 包传输。

此前 D4 与带原始统计的 D6 均同样停在 WAIT_RST／FS J，D6 的原生／UTMI SE0 和接收字节也均为零。D8 的明确断开／延迟连接对照没有改变这一状态。电脑 `lsusb` 无本探针，内核没有对应新设备枚举记录；本机可热插拔根端口均未禁用、过流计数为零，原始读取保存于 `deployment/pc_usb_ports.json` 和 `kernel_since_first_device_probe.log`。

下一项受控刺激是保持供电与 JTAG 不动，拔插 **138K USB2（USB-A）至电脑的数据线**，再比较同一探针的原始 SE0、RXCMD、接收字节和 HS 状态。读回工具已经保留在板上，不需要重新综合整机。

## 来源、修复与验证

设备核心以冻结 DA 为父，准备时验证全部 127 个输入及其成功位流；只显式替换当前第一方 FIFO、物理链路观察接口及原始事件模块。每项替换均记录当前 SHA、冻结父 SHA 和原因。描述符由冻结生成器生成独立实验身份，未修改原生成文件、vendor、冻结输入或外部锁定网表。

实际修复两处异步复位释放：FIFO 读写指针各用本域同步释放；attach 延迟计数也在参考域同步释放，ready 注册后送入 ULPI 两级同步器。仅这些 CDC 接收边界使用有界时序例外，未降低 60 MHz 时钟或屏蔽整域。没有部署负时序候选：D1／D2／D3／D5／D7 的失败构建原样保留，实际下载仅 D4、D6、D8。

主机侧修复实际 GAO 逐 bit CSV 与冻结解码 API 的不兼容。D4 第一个已完成的硬件采样经原始 CSV 重放恢复；没有为解码修复重编 FPGA。后续解码要求页面完整一致，记录主机解码器 SHA。构建入口也改为在路由审计不通过时返回失败。

- 独立探针／实际 CSV／页面一致性／回环字节流／速率门禁测试：**12 项通过**。
- `test_current_workstation_sources.py`：**10 项通过**，完整工作站来源选择未变。
- FIFO 针对性仿真：**8155 项检查通过**，含顺序、背压、复位。
- 实际 detach／attach RTL 仿真通过，覆盖参考域复位同步、断开 Function Control 写入、连接恢复和复位取消。
- 修改后的完整 25K 回归：**43 个 HDL testbench、50 项 Python 测试通过**，含 USB HS／FS；15:51:45～15:56:09，证据在 `~/.cache/fpga-usb2-hdmi/138k-device-attach-regression-20261029_155145/validation.json`。

使用方式见 `rtl/workstation/USB2_DEVICE_PROBE.md`。原 E5 回退位流 SHA256 为 `e723f82f45e5807452125f8a3bb6429ec4955bce91c7770066586fb738c66703`，位于原 `20261028-020452-d5-hotplug/candidate-e5/impl/pnr/ao_0.fs`。Flash 仍为原 E5；本报告不将离线回归或 SRAM 下载当作已实现高速收发。

## 16:50 重插读回与 17:09 接线核对

用户确认已重插后，16:50:21.378850～16:50:23.484403 再次采样，前后独立身份读回均为 C11029D8。原始证据保存在当前候选的 `deployment/after_user_replug_20261029_165021/`。

- 初始化仍完成且无错误；ULPI 频率量化值 60.160 MHz。
- RXCMD 累计由 1 增为 2，最后值仍为 0D，链路 NXT 累计为 2。
- PHY 仍为 WAIT_RST／FS J；原始与 UTMI 的已武装 SE0 最长时间仍为零，接收字节均为零；HS active=0、地址=0、online=0。
- 电脑没有本设备枚举或对应的新 USB 连接日志。此时仍未进行物理 USB 回环。

随后用户明确确认接法：**普通 A-C 线，A 头插 138K USB2，C 头直接插电脑左侧雷电 USB-C 口，无转接器**。该线的角色定义与本探针要求相反：USB Type-C 规范 Release 2.0 §3.5.2、Table 3-13 规定 C 插头以 56 kΩ Rp 上拉到 VBUS，是 A 端 Host／Source、C 端 Device／Sink 的传统主机线。

17:09:00 保存的本机 Type-C 只读状态为 `port0: data_role=[host], power_role=[sink]`、`port1: data_role=[device], power_role=[sink]`。没有独立验证物理雷电插座与 sysfs 端口编号的映射，不能据此宣称已定位为 port1；已确认的线缆方向本身足以要求先修正主机连接。

本次核对未下载 FPGA、未写系统 USB 角色，也未修改锁定网表。下一步按探针说明连接电脑 Host 与板卡 Device，保留 D+／D−／GND 并隔离测试线 VBUS，再读取同一 D8 探针；无需重综合。

接线记录、规范 PDF 和提取文本保存在 `~/.cache/fpga-usb2-hdmi/typec-role-confirmed-20261029_170852/`。PDF 来自 USB-IF，标题为 USB Type-C Cable and Connector Specification Release 2.0（August 2019），SHA256 为 `87d15160bf8bd25129b27e0b7c5e261ed0b1806b3b0d3a7b5d8b1eb783dc9981`。锁定网表中 USB2.1 接 VBUS2／F2.1、F2.2 接 +5V，仅作只读核对。
