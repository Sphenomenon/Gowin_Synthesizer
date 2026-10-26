# 25K 滑条本地反馈回归修复

用户报告 `0xC1251031` 滑动时滑条指示灯完全不动，旧版可以工作。本轮已在生产面板分支复现未连接主机时灯条固定在中点的问题；修复版本 `0xC1251032` 的完整离线回归、综合、P&R 和最终时序全部通过，现已完成 Flash 写入、校验、重载，随后两次均读回 `0xC1251032 / 0x70022020`。固化后用户回复“没问题了”，本轮滑条反馈问题已获实物确认，见[用户验收记录](slider_feedback_20261023/slider_acceptance.json)。此前 [C1251031 证据](HOST_HOTPLUG_20261023.md) 保留。

## 根因与修改

旧兼容分支 `midi_performance` 在收到 `slider_valid` 时独立更新 `strip_value`。面板分支 `gw138k_panel_performance` 将同一更新放进了 `input_targets!=0` 的 MIDI 接收目标门控；当 USB 未枚举且 BLE 未连接时，触摸采样仍可运行，但位置和 PCA9685 灯条一直保持复位值 128。USB 接入还会把正在显示的本地位置强制重置为 128。

本轮将本地位置更新移出连接门控，并移除 USB 接入对本地位置的重置；MIDI 弯音仍只发给原本在线的目标，离线采样不排队、不在重连时回放。松手／驱动故障释放快照仍立即把本地位置回中。触摸配置、阈值、滤波、引脚、PCA9685 驱动、弯音曲线及 USB／BLE 协议保持原实现。

## 验证

- 修复前的新增回归真实失败：`offline slider feedback frozen: pos=0 strip=128 leds=00ff`，日志保留在 `../results/slider_fix_20261023/reproduce.log`。
- 修复后同一生产应用测试通过：256 个离线位置逐点检查实际 `midi_slider_led_map` 输出；连接后不改变已显示位置，不发送离线弯音；断开后的左右端、释放回中、控制会话复位及再次连接均检查通过。
- 既有 16 键、256 个在线弯音位置、48 条排队控制、持音移调与不回放旧会话的定向测试继续通过。

完整设备回归通过：39 个 HDL 测试台、25 项 Python 测试，共 90 项检查，包含 USB HS／FS、BLE 固件逐字节检查及错误 ROM 拒绝、触摸 I²C 和 PCA9685 实际总线测试；无失败项，运行期间输入无变化。构建、回归、源码快照与当前 114 项构建输入逐项哈希相同；相对 C1251031 仅更改滑条本地更新门控及其回归测试两项输入。

候选证据：[清单](slider_feedback_20261023/candidate.json)、[构建](slider_feedback_20261023/build.json)、[完整回归](slider_feedback_20261023/validation.json)、[修复前复现](slider_feedback_20261023/reproduce.log)、[修复后定向测试](slider_feedback_20261023/controls.log)、[物理资源](slider_feedback_20261023/routed_resources.txt)、[最终时序](slider_feedback_20261023/routed_timing.tr)。

## 构建身份与物理结果

生产配置仍为 `midi_keyboard_top / HOST_PANEL_CONTROLS=1 / GW5A-LV25MG121NC1/I0`，工具 Gowin V1.9.12.03。Git 起点为 `f502f28f329c6665e4a6150583e390b2c9611cef`；输入清单 SHA256 为 `43f56f08547c40bb54506d6eb588292224af37a7a965da7ebbc31ca977fc49a1`。

位流为 `../results/slider_fix_20261023/build/impl/pnr/midi_keyboard.fs`，UserCode `0xC1251032`，SHA256 为 `303e1403f67503285e07469bb6c13dd8aa698db77d42054ad102ead622a2e671`。SecurityBit／Encryption OFF、CRCCheck ON，无 GAO。

| 项目 | 结果 |
| --- | --- |
| Logic／Register | 21,388/23,040（19,267 LUT + 2,121 ALU）／10,166/23,280 |
| CLS／物理 BSRAM／DSP | 11,206/11,520／54/56／3/28 |
| 综合等效 BSRAM | 40，与物理数分开记录 |
| setup／hold 违规 | 0／0 |
| 最差 setup／hold | +0.348／+0.247 ns |
| 最差 recovery／removal | +4.305／+1.025 ns |
| 时钟约束 | 原 50 MHz 与 ULPI 60.002 MHz；未放宽约束或添加例外 |

复现命令（从工程目录运行，输出目录须为新目录）：

```sh
sh run_sim.sh --output results/slider_fix_20261023/regression
sh build.sh --user-code C1251032 --output results/slider_fix_20261023/build
```

## 固化与回退边界

用户重新接入下载器后，首次读回全为 `0xFFFFFFFF`，门禁在任何擦写前停止；[失败部署记录](slider_feedback_20261023/initial_deployment.json)及原始读回日志保留。用户再次确认供电／连接后，重新读到 FPGA ID `0x0001281B`、原 UserCode `0xC1251031`、状态 `0x70022020`；Flash ID 为 `0x0B4017`。本轮使用 Gowin WINUSB cable-index 5、location 54、2.5 MHz；备份工具另行只读确认 JTAG 链仅有该 25K。

写入前完整读取 8 MiB Flash 到 `../results/slider_fix_20261023/hardware_retry_01/before_flash_c1251031.bin`，SHA256 为 `a69c1a509626a79994807f01b3de49478b7fce58b30dd30545d0694fa6c05c7c`。备份后从 Flash 重载并再次确认仍为 C1251031，再复核构建／回归／源码／快照与位流哈希一致，执行一次 operation 54 擦写及校验，工具确认 `Program and Verify Flash successfully.`。operation 1 重载后等待配置稳定，再进行两次独立只读核验，两次 FPGA ID、UserCode 及状态均符合预期。

最终证据：[发布索引](slider_feedback_20261023/release.json)、[固化清单](slider_feedback_20261023/deployment.json)、[第一次读回](slider_feedback_20261023/device_after.log)、[第二次读回](slider_feedback_20261023/device_after_repeat.log)。最初的离线候选清单保留其生成时尚未部署的状态；固化结果由独立部署清单记录。

回退可使用上述完整 Flash 备份，或此前 C1251031 已验证位流 `../results/hotplug_20261023/build_romstream/impl/pnr/midi_keyboard.fs`，SHA256 为 `809f93e1c548e6700e2721dafd5f44cb0cb54a35f33a3e466603deeeb26383a1`；此前 A25D 的 8 MiB 原始备份也继续保留。回退未实际演练，本轮不操作 138K。

实物滑条反馈已由用户确认；部署时生成的清单保留当时尚待实物确认的状态，后续确认单独记录。物理断电冷启动及触摸至 138K 音频／屏幕验收尚未完成。
