# 138K E5 与已固化 25K 的协议核对（2026-10-28）

## 结论

本轮未发现两板 USB 描述符、端点、MIDI 或 PL 版本不匹配。使用 **138K E5 的原始 CPU ROM 与 USB2 RTL 快照**，连接 **25K C1251032 的原始设备 RTL 与 PL 端点快照**，高速和全速模型均完成枚举、128 条 MIDI 演奏事件、PL HELLO/CAPS 及两块 tile 的确认。

实板仍未完成设备识别。因此当前排查点是 USB 端口协商／枚举及两端 ULPI 收发，不是已证明的 PL 版本冲突。下一步应记录 EP0 的具体失败阶段与应答，而不是先更换业务协议。

## 核对的版本

| 对象 | 本轮使用的输入 |
| --- | --- |
| 138K | `C11028E5`；当前 Flash 部署见 [固化与补焊复测记录](USB2_HDMI_FLASH_20261028.md) |
| 138K CPU ROM | 原始 `usb2_cpu.hex`，SHA256 `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457`，允许高速，未重新编译 |
| 138K USB2 RTL | E5 的 `usb/component/` 暂存输入，仿真所用 14 份 RTL 均与原清单 `staged_input_sha256` 核对 |
| 25K | `C1251032`；[2026-10-28 02:56 Flash 固化及两次身份读回](../../../../25k/example/MIDI_KEYBOARD/reports/REFLASH_20261028.md) |
| 25K 位流 | 原始 `midi_keyboard.fs`，SHA256 `303e1403f67503285e07469bb6c13dd8aa698db77d42054ad102ead622a2e671` |
| 25K 源码 | `projects/25k/example/MIDI_KEYBOARD/results/slider_fix_20261023/build/source_snapshot/`，原始清单全部 114 项输入及位流哈希重新核对通过 |
| 25K 来源 | HEAD `f502f28f329c6665e4a6150583e390b2c9611cef`；输入清单 SHA256 `43f56f08547c40bb54506d6eb588292224af37a7a965da7ebbc31ca977fc49a1` |

工作树中的后续 USB1 Full-Speed 配置不是上述 25K 已烧录版本。本轮没有以当前工作树代替 C1251032 快照，也没有给任一板重新下载或写 Flash。

## 逐项对照

| 项目 | 25K C1251032 | 138K E5 | 结果 |
| --- | --- | --- | --- |
| 设备身份 | `FB9A:FB9B`，USB 2.0，EP0 最大包 64 字节 | 匹配该 VID/PID 后检查完整复合接口 | 一致 |
| MIDI 接口 | 接口 1，`01/03/00`，MIDI 1.0 | 解析同一类／子类／协议与版本 | 一致 |
| MIDI 端点 | OUT `01`、IN `81`，bulk | 从描述符提取相同端点 | 一致 |
| 面板接口 | 接口 2，`FF/00/00` | 要求接口 2、alternate 0、`FF/00/00` | 一致 |
| 面板端点 | OUT `02`、IN `82`，bulk | 与 MIDI 端点分离后启用 GW25K 模式 | 一致 |
| bulk 包长 | 高速 512；全速 64 | 高速要求 512；全速接受 8/16/32/64 | 一致 |
| PL | `PL`、local-v1、16 字节头、控制／显示独立序号 | 相同帧格式和会话处理 | 闭环通过 |
| CAPS | 428×142、RGB565LE、tile 上限 248 像素、payload 上限 512、在线期限 250 ms | `gw_response()` 检查相同字段 | 闭环通过 |

138K 的流程为：端口就绪 → `usb_configure_device()` → 描述符与 MIDI 接口解析 → 写入 GW25K 模式 7 → PL HELLO。PL 握手不是 USB 枚举的前置条件。源码入口为 `firmware.c` 的 `find_midi_in()`／`connect()` 与 `gw25k_panel.h` 的 `gw_response()`；已核对全部 16 项当前固件输入与 E5 清单哈希一致。

## 快速闭环验证

复用 `sim/usb2/tb_workstation_usb2_application_25k.sv`，仅更换为以上原始输入，不构建整机，不改冻结快照。USB3300 与线缆由已有模型代替；25K 的实体 ULPI wrapper 和模拟电气链路不在该端到端用例内。

| 用例 | 结果 | 编译／运行 |
| --- | --- | --- |
| 高速模型 | PASS；地址 1、configuration 1、模式 7、128 MIDI、CAPS、两块已确认 tile | 4.424 s／40.825 s |
| 全速模型 | PASS；同上，bulk 64 字节；保持 E5 原始允许高速的 ROM | 4.396 s／33.624 s |

时间：2026-10-28 15:27:40 至 15:29:03（UTC+08:00）。本轮两例共约 83 秒，不涉及综合或布局布线。

另外以同一份 25K 原始快照运行四项定向用例，全部通过：

- `tb_usb_board_boot`：USB3300 ID／scratch／配置读回、首次命令超时恢复、DIR 抢占与永久故障限速。
- `tb_usb_board_cdc`：8155 项检查，2014 个接受字，50/60 MHz FIFO 顺序、背压、回绕与复位。
- `tb_usb_board_device`：高速 1523 项检查，描述符、独立端点、CRC 回滚、重复 OUT、丢 ACK 重试、halt、挂起／恢复及会话复位。
- `tb_usb_board_device` 的 `HIGH_SPEED=0`：全速 400 项检查。

本机可追溯证据目录：

```text
/home/sphenicidition/.cache/fpga-usb2-hdmi/20261028-020452-d5-hotplug/protocol_audit_20261028_152740/
```

`evidence.json` 包含两侧输入身份、复制后仿真输入哈希、端到端用例完整编译命令、日志哈希、六项结果及同期实板捕获位置；`hs_1/execute.log`、`hs_0/execute.log` 包含模型内 EP0 请求／应答及 PASS。端到端用例复现脚本为同一 cache 根下的 `audit_deployed_25k.py`。用例结束后再次核对 25K 的 114 项输入，快照未变。

## 同期实板状态与下一步

15:30:54 至 15:30:56 的只读 GAO 窗口读回仍为 E5：ULPI 心跳变化 647 次，链路快照更新 128 次，PHY 初始化 stage 17、failure 0，端口状态 16（ACTIVE），但 `recognized_devices=[]`。主机高速标志不代表已经证明 25K 同样进入高速。

当前观察量没有给出具体 EP0 请求及应答，不能据此区分“没有返回描述符”和“后续枚举步骤失败”。最小下一步是保留 HDMI 及现有只读探针，增加以下枚举诊断：

1. 当前请求：GET_DESCRIPTOR／SET_ADDRESS／SET_CONFIGURATION／配置描述符解析。
2. 最近一次传输结果：ACK／NAK／STALL／超时／CRC 错误及收到的长度。
3. 若接入 25K JTAG，同步读取 boot_done/error、PHY 状态、设备地址、configured 与 SETUP 收包计数，判断请求在哪一侧消失。

本轮只新增核对报告与本机仿真证据，未改变任一板的固件、协议或部署状态。

## 25K JTAG 身份与电脑枚举复测（15:58）

用户确认连接 25K USB2 至电脑，并将 JTAG 切到 25K。2026-10-28 15:58:50、15:58:51（UTC+08:00），使用当时扫描得到的 WINUSB location 53、0.9 MHz，仅执行两次 operation 0（Read Device Codes），均返回 `ID=0x0001281B / UserCode=0xC1251032 / Status=0x70022020`，工具退出码 0。未下载 SRAM、重载配置或写 Flash。

电脑内核日志在 15:56:07 至 15:56:09 已检测到 `usb 3-6` 全速设备接入，但出现 `device descriptor read/64, error -71`、`Device not responding to setup address`，最终 `unable to enumerate USB device`。`lsusb` 仍无 `FB9A:FB9B`。故障已在电脑主机上复现，不仅存在于 138K；当前证据将排查重点前移至 25K 设备端及 USB 物理连接／收发，尚不能区分设备 RTL 与硬件原因。

已固化 C1251032 的构建输入没有 GAO，启动模块的 `stage/vid/pid` 与 bridge 的 `phy_state/device_address` 也未导出，不能通过普通 JTAG 凭空读取这些运行状态。独立 `example/USB3300_HS/reports/verified_build.json` 虽有旧 GAO 镜像记录，但所指位流在本机缺失，`program_sram.py --check-only` 因找不到文件拒绝，未启动编程；不能将该记录当作可直接下载的文件。

本机原始证据：`/home/sphenicidition/.cache/fpga-usb2-hdmi/25k-readback-20261028_155750/`。`readback.json` SHA256 为 `4c2be9dc827f19913af6b26386bc1489c6edd26f221881c5db9165bebb85c1d7`，包含两次完整命令与日志哈希；`kernel_usb.log` SHA256 为 `838f362d3bf6b1bde51bcff6ed9ff53c09883ad30c4ad2e1862d5d3fb3465b43`。

此后用户明确授权25K自主综合及SRAM迭代。独立探针C12528D4／D5已实际读通USB3300 ID、Scratch和配置读回。18:22曾加载完整MIDI_KEYBOARD加JTAG观察器的C12528DA；23:08重插已复现电脑枚举 `error -71`。23:29 SRAM更新为显式USB-only MIDI回环／原生事件历史探针C12528DB，构建24秒，42个RTL bench及48个Python用例通过；它不是完整键盘。23:33再次接入仍在USB口3-6枚举失败；23:36按新下载器location786只读采样，前后身份均DB，初始化与约60 MHz时钟正常，但PHY历史仅{0,1}、UTMI有效接收字节0、地址及online均0。当前继续定位接入／复位收发，没有实际板间握手或MIDI通过证据。25K Flash C1251032及138K Flash均未改，具体位流身份、捕获与下一步见 [25K USB2 独立诊断](../../../../25k/example/MIDI_KEYBOARD/reports/USB2_LINK_DIAGNOSTIC_20261028.md)。
