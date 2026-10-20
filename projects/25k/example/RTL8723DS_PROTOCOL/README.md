> 仓库迁入（2026-10-20）：本目录为25K实测协议工程，APP唯一源码位于仓库根 `clients/android`，本目录的 `clients/android` 为相对链接。A25D/0.2.10及速率结论均来自25K，尚未迁入138K硬件顶层。位流、APK和构建缓存按仓库规则不进入Git；`reports/ready_build.json`及历史记录保留原验收路径。新克隆应重新构建，使用新生成的 `reports/last_build.json` 通过门禁后再编程。原APK的版本/哈希见[第十八轮](reports/speed18_20261020/README.md)，构建与迁入校验见[迁入说明](REPOSITORY_IMPORT.md)。历史报告仅带摘要，完整原始捕获仍保留在来源工程。
# 25K BLE v1 命令与内置音频录音测试

当前版本采用**通用二阶无损PCM下载**，配套 [0.2.10 APK](artifacts/gowin-control-0.2.10-gw25k-second-debug.apk)，已固化A25D。同一镜像三组一阶/二阶交替，中位有效PCM吞吐 **14.11→22.09 KB/s（+56.6%）**，固化后复测20.85 KB/s。同一APP核心完整192 KB下载含丢包重试、取消重开、断线续传与WAV保存，**18.65→14.15秒（耗时−24.1%）**；固化后完整下载13.72秒，WAV均与参考逐字节一致。以上为电脑BLE与生产APP Kotlin核心结果，手机实际速率待测。

OPEN_SECOND40显式授权READ41/ACK_READ42与DATA codec0/10/11，每块选择RAW、一阶/k9或二阶/k5，通用stereo PCM16无损预测，不使用音源字典。参考192000 PCM编码为80002字节（−58.33%，不含封装）。原3d/3e/3f只允许RAW/10，31/35始终RAW。APP仅明确UNSUPPORTED才按40→3d→3c→3b→39→38→37→36→30回退，保留完整CRC/身份/范围校验、可靠落盘后确认和窗口1。PCM上限仍8112、逻辑8160；UART921600/8E1、ACL27字节/8额度维持。详见[二阶协议](docs/SECOND_TRANSFER_EXTENSION.md)和[第十八轮报告](reports/speed18_20261020/README.md)，历史见[第十七轮](reports/speed17_20261020/README.md)。

固件 `builds/20261020_095747_100259/impl/pnr/ble_protocol.fs`，SHA256 `18c34c97a7bbe233f12096818310bbd689cc6d688c0a1b8adc8c19818693248d`，UserCodeA25D。50MHz约束Fmax50.018MHz、setup/hold0/0，最小setup余量0.007ns；17557 LUT、9480 Register、11140/11520 CLS（97%）、37/56 BSRAM。Flash写入校验、重载和无线验收通过；`reports/ready_build.json`指向本镜像。50组RTL与63项普通Android测试通过，完整下载另有实板验收。

**历史boot_id重复问题未解决**；板卡重启或重配置后，先删除手机未完成下载，再开始新录音。手机原生GATT/权限/UI/后台和本镜像物理断电上电尚未验收。原始HCI0x2002未封顶诊断确认控制器27字节/8包，没有隐藏额度；964字节边界对齐实测−2.9%，未采用。诊断代码仅归档，交付FFF1仍原BTST格式。

历史：[第十一轮](reports/speed11_20261020/README.md)972字节块、[第十轮](reports/speed10_20261020/README.md)命令写入试验、[第九轮](reports/speed9_20261020/README.md)DATA回执。操作见[APP联调](docs/APP_INTEGRATION.md)。

[第十三轮诊断](reports/speed13_20261020/README.md)：实读控制器特性不支持DLE/2M，最大TX/RX27字节；下载前后实际间隔均15ms，约七成下载时间处于ACL额度等待。7.5–15ms请求与原15ms请求各三次、前后回测共九次，电脑均采用15ms，未证实收益，未采用候选。生产输入与SRAM恢复22B4，Flash及0.2.8 APK不变；原始通知、能力查询与完整音频复验均归档。

[第十四轮](reports/speed14_20261020/README.md)：已取得逐包额度/发送微秒轨迹，两次均见额度归还批次周期中位15ms、额度从零恢复后下一包交付中位98µs。100µs H5确认合并通过定向/系统仿真和时序，但两份无记录器镜像交替三组仅−1.78%/+0.39%/+0.85%，无一致收益，未采用。全部15份测速及2份轨迹离线CRC/PCM核查通过，最终仍交付22B4/0.2.8；轨迹为FPGA/HCI边界观测，非空口抓包。

[第十五轮](reports/speed15_20261020/README.md)：实际计数每32768字节约1321个FPGA独立ACK、1302个host帧、5.63万UART字符，传输重试/错误增量为0。在当前8112块下重测2Mbps，字符占线约0.669→0.310秒，而下载中位原速前测9502、2Mbps9579、原速回测9752 B/s，未证明收益，保持921600。九份原始计数和通知独立CRC/PCM核查，最终恢复22B4；Flash/APK不变。

[第十六轮](reports/speed16_20261020/README.md)：同为8112块，MTU158将满通知从7个ACL包改为6个，但中位9627 B/s低于原MTU185前测9980、回测9757，未采用。另完成通用无损差分/Rice离线原型：参考PCM192000→130153字节（−32.2%），解码逐字节一致，含噪声RAW回退和错误输入检查；尚未接入FPGA/APP或部署协议，不能据此宣称实板提速。仍交付22B4/0.2.8。

## 初次 SRAM 验证（历史）

2026-10-20 已完成本板 SRAM Program+Verify 和真实无线命令测试：HELLO、GET_STATUS、完整响应 CRC32、精确重传、请求冲突、未知命令、坏 CRC 拒绝、乱序 ATT 错误及断线自动重连均通过。原始记录和重启 boot_id 核查见 [实板测试报告](reports/hardware_20261020/README.md)。

初次测试镜像为 `builds/20261020_024629_137760/impl/pnr/ble_protocol.fs`，UserCode=`2764`，SHA256：

```text
72d6d72f81312f58ac47dba95e647fc85898d8a80f2db94d6bbde368a11b44fc
```

50 MHz 下 Fmax=55.529 MHz，setup/hold 违例均为 0。9 组回归通过，包括完整 UART8E1/H5/30147 字节补丁模型、新服务发现/分片命令/自动重连、错误 ROM、失败或全零 LE Rand，以及主机编解码测试。

## 板级接线与启动

| 信号 | 球号 | 用途 |
|---|---|---|
| clk_50mhz | E2 | 50 MHz 输入 |
| module_uart_tx | J8 | 模组 TX → FPGA RX |
| module_uart_rx | K9 | FPGA TX → 模组 RX |
| module_bt_dis_n | K8 | 模组复位/使能 |
| restart_n | L10 | SW1，低有效 |
| READY / DONE | E8 / D7 | 心跳/初始化、连接状态 |

UART 启动与补丁下载为 115200/8E1，完成补丁和 Reset 后切换为 921600/8E1，不能按 8N1 AT 模组使用。模组仍需 RTL8723DS ROM-v2。上电复位 200 ms、启动等待 2000 ms，然后下载完整补丁并执行 HCI LE Rand、设置静态随机地址和广播。USB1 L6/K6 仅输入，不发送数据。

广播名 `GW25K-PROTO`，广播包含业务服务 UUID `9b6d0000-4c2a-4f87-9a31-138000000001`。设备使用 HCI LE Rand 生成 boot_id 和地址，但同镜像 JTAG 重载已观察到重复，不能保证跨重启唯一；普通断线重连保持本次 boot_id，重开业务会话。按 UUID 发现设备和特征，不保存固定句柄或固定地址。

当前 APP 固化版默认 `SESSION_MS=0`，表示持续运行；不再三分钟自动关闭。SW1 按住并释放各至少约 20 ms 可重启模组及业务状态；计时器饱和避免长期运行回绕后重复初始化。正数参数仍可用于限时测试。READY 约 1 Hz 心跳，DONE 常亮表示已初始化，连接后约 1 Hz 闪烁。DONE 快闪仅代表原 FFF1 订阅，不代表业务 Response CCCD；业务结果以客户端校验为准。

## 构建、仿真和下载

以下命令在本目录执行：

```sh
sh build.sh
sh run_sim.sh
python3 program_sram.py --manifest reports/ready_build.json --check-only
python3 program_sram.py --manifest reports/ready_build.json --frequency 2.5MHz
```

需要 Gowin EDA、Python 3、Icarus Verilog。构建使用 ASCII 临时目录、全局构建锁及分进程综合/PnR。原始 vendor 包每次构建均按 MANIFEST 验证。新构建应使用 `reports/last_build.json`；自带 `ready_build.json` 固定指向最近已固化并实测的镜像。`program_sram.py` 核对 SHA256、器件、时序、安全位并执行 SRAM Program+Verify。固化使用 `python3 program_flash.py --manifest reports/ready_build.json`，会替换启动区，执行已验证的 Arora V operation54、重载和身份核验。推荐 JTAG 2.5 MHz。

回归结果保存在独立 `reports/simulations/<时间戳>/`，最近结果索引为 `reports/last_simulation.json`；不覆盖此前日志。

## 电脑联调

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-ble.txt
.venv/bin/python tools/protocol_check.py --output reports/protocol_next.json
```

工具默认连续连接两次，检查服务属性、Capability、Status Read、HELLO、GET_STATUS、精确重传和第二次连接的新 nonce。首轮同时检查 REQUEST_CONFLICT、UNSUPPORTED、错误 CRC 无响应及乱序 ATT 0x80；随后继续正确命令，验证错误未消耗新请求 ID。每次逻辑请求的写入分片都使用 Write with response。

`--connections 1` 可做单连接测试。工具结束会主动断开，FPGA 随即重新开启广播，可再次运行。输出须使用新文件名以保留证据。macOS 需允许宿主访问蓝牙。

## 文件

| 路径 | 作用 |
|---|---|
| rtl/ble_protocol_command.v | 分片/CRC32、会话、32 条精确请求缓存及录音命令调度 |
| rtl/ble_recording.v | 内置 PCM 录制时基、任务、封存、分块下载和续传 |
| audio/ | 内置 ROM、1 秒参考 WAV 及来源哈希 |
| adaptations/bt_gatt.v | 新数据库、业务写入/分片通知和断线重新广播 |
| adaptations/bt_hci_init.v | 补丁初始化、随机 boot_id、地址和广播 |
| adaptations/bt_h5_transport.v | 参考 138K compact 版后改为 25K 同步块 RAM |
| adaptations/bt_uart_fast.v | 原速启动和运行期高速分频的 8E1 UART |
| adaptations/bt_acl_bridge.v | 控制器ACL分包、物理信用、接收重组与事件穿插 |
| adaptations/bt_verilog_core.v | 新模块接线和会话输出使能门控 |
| prepare_adapted.py | 生成 H5 pending RAM 和 32 字节 ATT 槽的构建副本 |
| tools/protocol_v1.py | 独立主机线格式、CRC32、分片重组 |
| tools/protocol_check.py | 实际 BLE 命令、错误和重连测试 |
| vendor/rtl8723ds_ble/ | 未修改的原始包、固件及来源/权利说明 |

原始包的权利与固件来源仍以 [NOTICE](vendor/rtl8723ds_ble/NOTICE.md) 和 [firmware manifest](vendor/rtl8723ds_ble/firmware_manifest.json) 为准。本次没有给第三方代码或固件添加新的许可证。
