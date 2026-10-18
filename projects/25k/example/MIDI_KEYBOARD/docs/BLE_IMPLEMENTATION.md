# RTL8723DS BLE MIDI 实现

`rtl/ble_board/midi_ble_link.v` 是实际板级 BLE 主机：50 MHz FPGA → UART 115200 8E1 → H5 → HCI 初始化/ROM-v2 RAM 补丁 → ATT/GATT → BLE MIDI。没有 MCU、运行时软件或180秒演示退出计时。原 `example/RTL8723DS_BLE` 保持原样，派生来源见 `rtl/ble_board/NOTICE.md`。

## 板级接口与启动

UART 名称以 RTL8723DS 模组为视角：`module_uart_tx` 是 FPGA 输入（模组 UART_OUT/J8）；`module_uart_rx` 是 FPGA 输出（模组 UART_IN/K9）。`module_bt_dis_n` 接 K8，低复位。正常 `CLK_HZ=50000000`、`BAUD=115200`、`DISABLE_MS=200`、`STARTUP_MS=2000`。上电/按键复位必须给 `reset` 高电平，时钟沿后计时重新开始，并执行完整 H5/HCI/补丁流程。`BAUD` 参数供加速仿真使用；实板必须保留115200，因为 HCI 波特率命令和 ROM 配置固定为此值。

`PATCH_FILE` 默认 `rtl/ble_board/rtl8723ds_patch.mem`，综合/仿真工作目录为 `example/MIDI_KEYBOARD`。换工作目录时须给出可读的 ROM 路径。ROM含30,147字节有效补丁/配置，存储文件填充到32 KiB；原固件来源和校验信息保留于同目录 manifest。

`initialized` 表示完成H5协商、芯片/ROM检查、120个补丁片段和BLE广播配置；`online` 只在连接成功且客户端已启用MIDI特征CCCD时置高。H5重传耗尽、HCI超时/失败、ROM不匹配、应用发送失败会锁存`failed`并拉低BT_DIS#，显式复位可重新启动；完整`midi_keyboard_top`还在failed连续5秒后自动脉冲reset，重新开始模块禁用、H5/HCI和完整补丁下载。断开连接属于正常事件，会清除CCCD及待发值，并发送真实 `LE Set Advertising Enable (0x200A, 1)`；控制器命令完成后恢复可连接广播，失败/两秒超时进入failed。

## 广播和ATT数据库

广播名称为 `GWK-MIDI`，使用31字节 legacy connectable advertising：Flags、完整128位MIDI服务UUID、完整本地名称。ATT MTU固定23；服务与特征UUID均按BLE要求低字节在前传送。

| Handle | 属性 | UUID/值 |
|---|---|---|
| 1 | GAP Primary Service | 0x1800，结束3 |
| 2 | Device Name declaration | Read，值handle3 |
| 3 | Device Name | `GWK-MIDI` |
| 4 | GATT Primary Service | 0x1801，结束4 |
| 5 | MIDI Primary Service | `03B80E5A-EDE8-4B33-A751-6CE34EC4C700`，结束8 |
| 6 | MIDI declaration | Read / Write Without Response / Notify，属性0x16，值handle7 |
| 7 | MIDI characteristic | `7772E5DB-3868-4112-A1A9-F2669D106BF3` |
| 8 | MIDI CCCD | 0x2902；0禁用、1启用通知 |

实现 Exchange MTU、Find Information、Find By Type Value（包括128位MIDI服务匹配）、Read By Group Type、Read By Type（16/128位查询）、Read、CCCD Write/Write Command、MIDI Write Without Response与Notify。混合16/128位UUID的发现按ATT规则分多次应答，元素长度不混用。未知请求返回ATT错误；不支持的命令不回包；CCCD值2（indications）返回无效值长度错误。Read Blob对这些短值返回Attribute Not Long。

MIDI值完全来自/交给现有`ble_midi_codec`，每值3..5字节，字节0在`data[7:0]`。不会生成旧测试用BTST/CRC数据或定时伪通知。Read返回最近被板级发送接口接受的值；初始值为合法三字节BLE MIDI Clock `80 80 F8`。

## Android配对与密钥范围

此前固件未处理SMP固定信道CID 0x0006，Android系统设置发出的Pairing Request得不到回应，会报告配对码或设备配置错误。本轮新增`midi_ble_smp`，通过HCI LE Rand产生随机数，使用控制器LE Encrypt完成Bluetooth c1/s1及STK握手，并处理LTK Request和Encryption Change。Legacy Just Works不需要输入配对码；不支持MITM认证或LE Secure Connections。

协商bonding时只分发Encryption Information和Master Identification，保存一个随机LTK/EDIV/Rand记录，用于本次上电期间的断连重连。记录不写入非易失存储：重新固化、FPGA复位或断电后，应在Android中忘记`GWK-MIDI`再配对。安全ACL与ATT共用控制器信用，LE Rand/Encrypt等HCI命令独立于ACL信用；配对过程中暂停MIDI通知。协议仿真通过后仍须实际手机验收，不把仿真成功视作Android已配对。

Android系统配对完成后，需在支持BLE MIDI的音乐应用中选择该设备建立MIDI会话并订阅CCCD，屏幕BLE在线标志才亮。系统设置中的配对状态本身不代表MIDI端口已经打开。

## 流控与支持边界

发送端仅在`value_tx_valid && value_tx_ready`时接受一个值；断线、未订阅或待发槽占用时ready为低。长度必须是3..5。ATT响应优先于通知。每个ACL包都同时等待H5可靠传输完成及HCI Number Of Completed Packets的当前连接credit后才发送后续ACL，控制器仅需一个ACL槽。

接收端在`value_rx_valid`置高后保持data/length直到`value_rx_ready`；后续完整Write Command可暂存在内部解析包，H5接收邮箱满时不确认新可靠帧，由对端重传提供背压。有效短值不因codec暂停而覆盖。上层应及时处理输入，以免长时间停顿阻塞连接事件处理。

当前支持一个LE连接、Legacy Just Works配对及链路加密、单一ATT bearer、固定MTU23和完整L2CAP ACL包；不实现Secure Connections、MITM认证、持久bond存储、L2CAP分片重组、Prepare/Execute Long Write、EATT或多连接。MIDI codec范围是每值一个完整1..3字节MIDI消息，不接受SysEx、多消息打包、running status或MIDI实时字节交错。客户端需要通过平台BLE MIDI驱动/应用连接，普通传统MIDI端口不会自行发现BLE服务。尚未进行本次完整键盘固件的实板/主机兼容性验收。

## 可复现实验

在 `example/MIDI_KEYBOARD` 执行：

```sh
iverilog -g2012 -s tb_ble_board_system -o /tmp/tb_ble_board_system.vvp rtl/ble_board/*.v sim/tb_ble_board_system.v
vvp /tmp/tb_ble_board_system.vvp
vvp /tmp/tb_ble_board_system.vvp +wrong_rom
```

系统测试在真实UART引脚边界建立独立控制器模型，逐字节从旧例程保留的原始厂商bin重建预期补丁，核对30,147字节和120个片段回显、全部HCI命令参数、H5序号/ACK/SLIP/校验和/UART奇偶校验、标准128位UUID发现、3/4/5字节通知、Read、Write Without Response、RX背压、CCCD合法性/跨连接清除、断线后的真实HCI重广播、超过原180秒边界的持续工作、复位重新从H5和补丁下载开始。`+wrong_rom`确认不兼容ROM在下载前失败。


### 定向完成事件测试

```sh
iverilog -g2012 -Wall -s tb_ble_gatt_completion -o /tmp/tb_ble_gatt_completion.vvp rtl/ble_board/midi_ble_gatt.v rtl/ble_board/midi_ble_smp.v sim/tb_ble_gatt_completion.v
vvp /tmp/tb_ble_gatt_completion.vvp
```

该测试采用与H5块RAM一致的单周期同步读取，先通过连接/CCCD和真实通知消耗ACL信用，再验证43/255字节Number Of Completed Packets事件的流式归约。匹配项可以位于最后一项或第一项，16位计数的高字节非零同样有效；其他handle、匹配但零计数、HCI参数长度错误、Num_Handles与长度不一致以及空列表均不能释放待发通知。它不通过force修改DUT信用或完成信号。

### 配对和错误恢复测试

`sim/tb_ble_smp.v`检查560项行为：Bluetooth已知c1/s1向量与独立OpenSSL计算结果、7..16字节密钥、Just Works协商、正确/错误Confirm、早到LTK请求、真随机命令路径、RAM bond、RPA变化后的重连、复位丢失bond、长度/OOB/乱序拒绝、HCI失败/超时、背压中止及迟到结果不会重启已失败的配对。HCI命令超时通过`transport_failed`进入现有板级5秒重置恢复。

`sim/tb_ble_pairing_transport.v`在同步H5邮箱边界检查CID6路由、35字节AES命令全部发送字节、真实双方地址输入、H5确认/Command Complete/ACL完成互相独立、Num_HCI_Command_Packets=0时阻塞、加密事件、Android AuthReq=0x2D协商，以及命令未完成时断连后重新广播、旧ATT/MIDI接口可继续使用。

这些测试由`run_sim.sh`自动发现执行，未用其结果代替真实Android手机配对和演奏验收。

### Android实板连接确认（0x00005A52）

2026-10-17用户确认：忘记旧设备并重新配对后，Android系统配对成功，MIDI应用也能连接。该反馈确认配对与应用连接，不扩大为音符收发、长期演奏或持久bond存储验收。单RAM bond的复位/断电限制仍适用。证据见`reports/ble_encoder_20261017.json`。
