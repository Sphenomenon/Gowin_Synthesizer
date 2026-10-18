# 来源说明

UART/H5/HCI/ATT/GATT Verilog 源码来自本工程已实测版本。导出包未附加新的开源许可证。

Realtek RTL8723DS 控制器 RAM 补丁与配置为第三方厂商二进制，取自 https://github.com/armbian/firmware/tree/master/rtl_bt 。文件原始 SHA256、ROM 版本选择及生成配置记录于 firmware_manifest.json。

本包中的原始二进制供本地复现验证，生成 ROM 供本地 FPGA 驱动运行。原第三方文件的权利与许可仍由其权利人及上游条款决定；本导出不对第三方固件重新授权。

## MIDI_KEYBOARD 派生实现

本目录 `midi_ble_uart.v`、`midi_ble_h5.v`、`midi_ble_hci_init.v` 分别派生自同仓库 `example/RTL8723DS_BLE/vendor/rtl8723ds_ble/rtl/bt_uart.v`、`example/RTL8723DS_BLE/generated/rtl/bt_h5_transport.v`、`example/RTL8723DS_BLE/vendor/rtl8723ds_ble/rtl/bt_hci_init.v`。`midi_ble_gatt.v` 基于其 generated ATT/GATT 架构，替换为标准 BLE MIDI 服务和实际应用值接口。保留原来源说明；本次派生未更改旧例程，也未为原代码或固件增加许可授权。

`rtl8723ds_patch.mem` 与原导出包逐字节一致，来源与哈希见 `firmware_manifest.json`。`midi_ble_hci_init.v` 调整模块名、BLE MIDI 广播和接收存储结构；ROM-v2 检查、补丁下载及 115200 波特率配置保持原验证流程。

## GW25K 内存与接收流水优化

为适配GW25K资源，派生实现进一步调整了存储推断和消费时序：H5的`delivered_ram`采用同步读取，使控制器接收邮箱可推断为块RAM；HCI与GATT消费端增加相应WAIT周期，等待真实读数据，不改变UART/H5线协议。HCI只保留实际初始化命令需要的前16字节事件头，仍按完整事件长度逐字节消费。

GATT把原264字节可随机读取的寄存器包缓存缩为32字节前缀，标准MTU23及全部ATT解析字段保留于此前缀。HCI Number Of Completed Packets的各连接handle/count在CAPTURE期间流式归约，完整有效HCI长度和Num_Handles核对通过后才恢复当前连接的单ACL信用；不截断超过32字节的完成事件，不因其他连接或零计数授予信用。新增`sim/tb_ble_gatt_completion.v`用单周期同步读邮箱直接验证43字节及255字节事件、末项/首项匹配、高字节非零计数、其他handle/零计数和两种长度错误隔离。该优化不改变厂商补丁内容，也不修改旧BLE例程。

`midi_ble_smp.v`为本工程新增的Legacy Just Works安全主机状态机，通过控制器HCI LE Rand/Encrypt执行随机数和AES运算；不是厂商固件的SMP开关。其单个bond只保存在RAM，复位失效，不声明持久bonding、MITM或Secure Connections。
