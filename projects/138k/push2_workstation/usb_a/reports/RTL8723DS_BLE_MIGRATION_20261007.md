# RTL8723DS BLE 迁移至 GW138K：2026-10-07

独立 138K 蓝牙工程完成综合、布局布线和位流生成，50 MHz 的 setup、hold、recovery、removal 均通过。联合缓存优化的完整工作站集成 0x90 已布通并生成位流，但新增 BLE 路径和 DDR 域时序退化，标记为实验候选，未通过发布验收；两者都没有在 138K 上完成模组实体测试。对应机器记录为 `RTL8723DS_BLE_MIGRATION_20261007.json`，接线和复现命令见 `../rtl/bluetooth/README.md`。

## 实现与来源

队友包位于 `/home/sphenicidition/Documents/fpga_scope_vec_delivery_20260930/rtl8723ds_ble_verilog/rtl8723ds_ble`。将完整 41 文件导出包逐字节冻结到 `usb_a/vendor/rtl8723ds_ble`，同时保存 SHA256 清单 `inputs.json` 和原始导出 `MANIFEST.json`。构建和仿真均先核对源包完整性。

这套驱动由 UART 8E1、H5、HCI ROM-v2 验证/补丁下载、ATT/GATT 组成。保留原版 FFF0/FFF1、固定广播名称和带 CRC 的 BTST 测试通知。没有加入 BLE MIDI、蓝牙音频或业务数据输入。本次迁移增加：

- 50 MHz 138K 接入层、板级三态输出、复位时立即撤销 OE。
- NEO Dock 31005 的 J8 PMOD1 球号、电平和时序约束。
- Gowin ROM / 同步器属性，只施加在构建副本，原包不修改。
- 独立只读 UART 状态快照与 PC 解码器。
- 独立工程和当前完整工作站的构建入口，候选使用独立结果目录与 UserCode。

## 独立候选

工具 Gowin V1.9.12.03，器件 `GW5AST-LV138PG484AC2/I1`。

- 构建：`results/ble_standalone_20261007_231650_271452`
- 位流：该目录下 `Prj1/impl/pnr/ble138k.fs`
- UserCode：`0x00000086`
- SHA256：`3b3e24eef6bb58970c9262989b36f62da86dfa9eb1272b56e435e9d9b45a7f10`
- PNR 资源：11405 LUT、9189 寄存器、72 RAM16、16/340 BSRAM；Logic 为 12623/138240。
- Fmax：55.529 MHz；50 MHz 下 setup WNS +1.991 ns、hold WNS +0.161 ns，违例端点均为 0；recovery +17.097 ns、removal +1.392 ns。
- UART 异步输入 false-path 确认只到 `rx_sync_0_s1/D`；两个 RX 同步器和两个复位同步器在 routed netlist 中保留。
- 从 Gowin 16 个 pROM 的 INIT 参数重建全部 32768 字节，与补丁 ROM 全字节匹配。Gowin 会省略 ROM 的零尾部 INIT 参数；已按安装包 UG285 与 pROM 仿真模型确认其默认初始化值为 0。重建镜像 SHA256：`827718bbda291c2b74ca4ccae3b6892cec6305cbb39d83c0c4c211d21d044bdd`。
- 输入文件在完整构建前后保持一致；没有编程硬件。

前一次候选在 SDC 仍使用 Xilinx 风格 `rx_sync[0]/D` 时未能进入 PNR，已改为 Gowin 实际寄存器名称 `rx_sync_0_s1/D`；上述新目录重新完成了全流程，保留失败目录作为过程记录。该失败尝试没有位流和实体写入。

## 回归

`results/ble_regression_20261007_231317_692807/result.json`：8/8 PASS。

| 测试 | 覆盖 |
|---|---|
| H5 | 物理 8E1 UART、SLIP、ACK、重试、重复包、280 字节上限、背压、校验和、奇偶错误 |
| GATT | 连接、发现、ATT 错误、CCCD、控制器额度、两槽回复队列、CRC 与通知序号 |
| 原版完整系统 | 独立控制器模型从原厂二进制重建期望补丁，核对全部 30147 字节与 120 片回显，再检查 HCI/ATT/通知 |
| 原版错误 ROM | 非 ROM-v2 控制器在补丁下载前失败 |
| 138K 板级完整系统 | 对实际迁移顶层重复完整控制器模型验证 |
| 138K 板级错误 ROM | 高阻释放下的错误型号停止行为 |
| 板级生命周期和状态 | 上电复位、延迟使能、会话到期、异步 OE 释放、重启；完整 24 字状态快照及 8N1 串口格式 |
| 真实 50 MHz UART | 115200 8E1 同时收发、坏奇偶校验丢弃和后续字节恢复 |

原系统测试假定 UART TX 始终有驱动，138K 板级模型增加接收端上拉，并仅在 OE 有效期间检查奇偶与停止位；会话停止可中途释放正在发送的 ACK。原版协议测试保持原包字节不变，仍独立检查正常传输。另新增被动通知校验工具 `verify_ble_payloads.py`：队友原平台的 40 条真实 PC 捕获全部通过，坏 CRC、重复/丢号与数量不足的负例被拒绝；这不构成 138K RF 实测。

## 工作站集成

基线是当前 0x85 的完整 staged 工程 `results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1`。基线清单 597 个输入先逐一核对；集成只改五个原文件：工程文件、工作站顶层、CST、SDC、构建 TCL，另加入 BLE 文件。现有其他 RTL/IP/ROM 输入都保持基线内容。

综合结果 `results/ble_workstation_20261007_231515_347100`：69303 LUT、49902 寄存器，综合 BSRAM 为 232/340，较基线同阶段 216/340 增加 16。综合和 PNR 的 BSRAM 统计口径不同，不能用 232 与基线 PNR 的 260 直接比较。原版综合结果用于对照；联合优化版的最终物理结果见后文。

完整尝试 `results/ble_workstation_20261007_232742_721890` 使用 UserCode `0x00000087`、route_option=1；映射 BSRAM 276/340、CLS 61258/69120（89%），布线结束报 PR0004，10713 条网络未布通，没有生成位流或时序报告。算法 2 比较尝试 `results/ble_workstation_20261008_003117_890857`（0x88）和 HCI-only 尝试（0x89）在联合 HCI+H5 优化版 0x91 通过独立 PNR 后被主动终止，记录为 superseded，保留输入校验与日志，没有生成位流；这不代表算法 2 的路由失败。完整集成验证转向 0x90 联合优化版。新 BLE 模块使用既有 50 MHz 时钟，状态从 J8 pin 9/AB21 独立输出。原 U15 工作站诊断串口不混入 BLE 帧。基线本来就有尚未关闭的全板音频/USB/CDC 时序，集成后的完整报告必须单独核对。

## 实体状态

没有执行 SRAM/Flash 下载、模组连接或 BLE 实测；`LATEST_WORKSTATION.json` 保持当前板上 0x85 的记录。下一步需要按 README 接外部 RTL8723DS，确认 Bank4=3.3 V、模组电平/供电和 ROM-v2，再做 SRAM 候选与模块发现/连接/订阅/CRC 通知实测。不能将队友原平台的验证记录或本次控制器仿真当作 138K 实物结果。

## 可选 compact HCI 缓存

`--compact-hci` 使用 `rtl/bluetooth/adaptations/bt_hci_init.v`，把原版并行写 32 个参数、寄存器实现的命令缓存改为单写口异步读 RAM。命令头由已有 opcode/length 寄存器给出，32 个参数逐周期准备；补丁、片号、命令、超时和 GATT 行为保持原协议。原始 vendor 包保持字节一致，此优化只在 staged 构建副本中替换初始化器。

实验 `results/ble_compact_hci_experiment_20261008_004209_144875`：独立综合 10225 LUT、7116 寄存器、104 RAM16、16 BSRAM，相比原版独立综合减少 1184 LUT、2073 寄存器。`results/ble_compact_regression_20261008_004448_005737/result.json`：同一 8 项回归全部通过。完整 compact 集成候选 `results/ble_workstation_20261008_004513_616338`，UserCode `0x00000089`、route_option=2，完整综合通过：68244 LUT、47828 寄存器、1711 RAM16、232 综合 BSRAM，比原版集成减少 1059 LUT/2074 寄存器；HCI-only 物理比较被联合优化版替代并停止。

## 可选 compact H5 缓存

`--compact-h5` 使用 `rtl/bluetooth/adaptations/bt_h5_transport.v`。接收帧中用于链路探测的字节 4/5/6 在 UART 捕获时单独锁存，因此完整帧 RAM 只保留一个动态读端口，可推断为 SSRAM；H5 状态机、序号、ACK、重传和背压不改变。实验 `results/ble_compact_h5_experiment_20261008_010159_415270` 和 `results/ble_compact_all_regression_20261008_010554_904969/result.json` 确认完整补丁、H5 和 8 项板级回归通过。HCI+H5 合用时独立综合为 8152 LUT、4860 寄存器、140 RAM16、16 BSRAM，比原版少 3257 LUT、4329 寄存器。

完整联合优化集成候选 `results/ble_workstation_20261008_010628_324000`（0x90）及独立候选 `results/ble_standalone_20261008_010636_258601`（0x91），均使用路由算法 2。独立 0x91 已完成 PNR：8148 LUT、4860 寄存器、140 RAM16、16 BSRAM、6658 CLS；Fmax 61.075 MHz，setup WNS +3.627 ns、hold +0.180 ns、recovery +16.957 ns、removal +1.389 ns，setup/hold 违例 0。32 个 parameter RAM16 和 36 个 frame RAM16 正确推断，ROM 与同步器审计通过。位流 SHA256 `df0bee20abb6facc8935b4d7630eb4a848f491370f433aaf20283a32a22c037f`，硬件未编程；完整 0x90 综合已通过：66386 LUT、45573 寄存器、1747 RAM16、232 综合 BSRAM，较原版集成减少 2917 LUT/4329 寄存器；最终 PNR 结果见后文。

## 完整 0x90 最终结果与发布边界

`results/ble_workstation_20261008_010628_324000/Prj1/impl/pnr/Prj1.fs` 已生成，UserCode `0x00000090`，SHA256 `9b20bb271d12a485ec550d3ddf7fc06b8c5b6623c3da6838eed689195a7091c1`。Gowin 退出码 0，输入文件在构建前后保持一致，未执行硬件编程。物理资源：66321 LUT、45573 寄存器、1747 RAM16、276/340 BSRAM、58954/69120 CLS（86%）。新增物理 BSRAM 恰为 16；补丁全字节、两个缓存推断及 RX/复位同步器审计通过。

**该集成位流未通过时序验收，不能作为稳定工作站发布或替换当前 0x85。** 50 MHz 域 Fmax 45.134 MHz，clk50-only setup WNS -2.156 ns，最差路径在 `u_ble/u_driver/core/application/packet[10]_7_s1/Q -> response[22]_6_s0/D`。基线该域 Fmax 为 53.055 MHz；DDR UI100 的 Fmax 从 215.707 MHz 降到 71.563 MHz。其他主要域：audio 58.161/76.8 MHz、USB 40.011/48 MHz、HDMI pixel 154.589/148.5 MHz、CPU bus 72.997/50 MHz。整体 STA 报告 setup 5587、hold 116 个违例端点。标准路径表中同步 hold 的正裕量不能代表全部跨域/异步端点通过。

PR1014 对 `clk_50m_d` 的 generic routing 警告在原 0x85 基线也存在；完整工程 PRIMARY 8/8、LW 8/8 已满。仅凭该警告不能判定本次退化原因。后续集成发布需单独优化 GATT 回复组合路径及完整工程布局/DDR 时序，再跑全板验收；本次独立 0x91 的 50 MHz 时序通过结果独立有效。

本次交付包含完整的独立 138K BLE 工程、已通过回归的缓存适配、复现构建、板级接线、状态与通知校验工具，以及明确标注时序问题的完整集成实验候选。138K 实体 BLE 验收仍需接外部模组；板上记录保持原 0x85，未写 SRAM/Flash。
