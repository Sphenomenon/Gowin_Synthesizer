# 自定义 138K：综合／上板／固化前检查

日期：2026-10-22，Asia/Shanghai。用户明确要求完成、检验、综合、上板和固化，并随后告知调试口已插入；这些属于本次硬件操作授权，不是实际完成证据。

**结果：当前来源的 USB2 电气检查被阻断，运行环境也未枚举到下载器或板卡串口。本轮未综合、未 P&R、未下载 SRAM、未写 Flash。** 不使用旧 Dock 位流冒充新底板整机，不绕过前一阶段门禁。

## 1. USB2 的具体阻断

已有补充工程的 SCH_PAGE `acfe54c5657f8d2b` 中，U2 的组件为 `USB3300-EZK.1`，U4 为 `TXS0108EPWR.1`，U5 为 `TXS0104EPWR.1`。型号依据来自已有工程，不能从三份网表 `$PACKAGES` 的 `{Value}` 推断，也尚未核对实板丝印。

工程 `ProPrj_138K（这个有效）_2026-10-16.epro2/138K（这个有效）.epru` 的 SHA256：`c714cacea6ca2b6dc400c8e22a851f9e0b644303968b76dde492c7f4b043e19b`。连线仍采用较新 `Netlist_my_138k_2026-10-21.tel`，SHA256 `deff91f6c48be8d66241e32107b88f7eea47ad2bf6c5b607b139c4b85c33a121`。

| 核对项 | 当前网表／器件手册 | 判断 |
|---|---|---|
| U4 PHY 侧 | VCCA `U4.2=VDD_1V8`；PHY DATA 接 A1–A8，FPGA 接 B1–B8 | PHY 接 1.8V 侧，不是 3.3V 侧 |
| U5 PHY 侧 | VCCA `U5.1=VDD_1V8`；CLK／STP／DIR／NXT 接 A1–A4 | 同上 |
| STP 实际路径 | FPGA E17 → U5.12(B2) → U5.3(A2) → U2.13(STP) | 到 PHY 的输出侧名义供电只有 1.8V |
| USB3300 输入 | DS00001783C，第 12 页表 5-3：VIH 最低 2.0V | 1.8V 侧不能保证满足高电平要求 |
| PHY 返回方向 | USB3300 输出高电平下限为 VDD3.3−0.4V；手册工作供电最低 3.0V，即至少 2.6V | 高于 TXS A 侧 1.8V 推荐输入高电平范围上限，不是合规的电平匹配 |
| 核心 1.8V 网络 | `VDD_1V8` 还连 U2.15／U2.26，即 USB3300 的内部数字 1.8V 供电脚 | 不能直接把整条网络改接 3.3V 来“修复”转换器 |

以上是依据明确器件模型及名义电源的规格冲突，不是实际电压、波形或器件损坏测量。若实板器件或走线已改，必须提供对应装配／供电依据，更新检查来源；不能把 FPGA IO_TYPE 改为 1.8V 就假称修好了 PHY 侧问题。手册不匹配也不能用一次偶然通信成功替代电气验收。

先核对实板 U2／U4／U5 型号、U4／U5 VCCA／VCCB、核心板 Bank2 实际电压及改线情况，再审查硬件修订和更新网表；本报告不提供未经该核对的飞线方案。

## 2. 原厂资料与可复核来源

资料按原始字节下载到 `/tmp/custom-138k-preflight-20261022/`，通过文本及页面渲染复核；第三方 PDF 不加入源码，不修改原始资料。原厂地址：

```text
https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/00001783C.pdf
https://www.ti.com/lit/gpn/txs0108e
https://www.ti.com/lit/gpn/txs0104e
```

| 文档 | 依据 | 原始 PDF SHA256 |
|---|---|---|
| Microchip DS00001783C | 第 9 页电源引脚、第 12 页表 5-3 | `33e73e37f5110cb9e3ef66ccf8c7fdd4a16593c7b1afcff0c5df523e41963a9e` |
| TI SCES642L，2024-11 修订 | 第 6 页 §5.3 推荐输入条件；A 侧跟随 VCCA | `a6ddbe03088d291d1a1f8012189086b4b9962d1c878a462a8393c59fe225c883` |
| TI SCES651K，2023-10 修订 | 第 9 页 §6.3 推荐输入条件 | `88295316d8d520f1b967af2ce9c7dc4b7491c1e647968728b9690c6514fb7b41` |

## 3. 本轮落地与来源身份

不修改旧 [v1 重定位证据](CUSTOM_BOARD_PIN_RELOCATION_20261022.md)的结果，当前配置使用新身份 `custom_138k_usb2_20261022_pinout_v2`：

- `check_ulpi_electrical()` 对当前实际网表报告两个 `ULPI_PHY_OUTPUT_DOMAIN` 和一个 `ULPI_STP_HIGH_LEVEL`。
- 输出记录 `electrical_check.status=blocked`、`actual_board_measured=false`、`full_electrical_acceptance=false`。型号改变、未知电源网名、缺供电端点不能被默认为兼容。
- 即使隔离测试中的电压域检查不再报冲突，`synthesis_allowed`、`hardware_accepted`、`sram_deployed`、`flash_deployed` 仍保持 `false`；局部检查不能授予整机部署资格。
- 原有 101 个端口位置不变；位置文件 SHA256 仍为 `282a251a97016aa774b14277ba534c1d29c57ca05b6b8a87bd9afd08bace352b`。完整 IO／原生顶层、ULPI Host／CDC、DAC 格式和时钟／安全启动、HDMI 极性与 CEC 等集成缺口仍显式保留。

再次执行已有命令，输出在 `usb_a/results/custom_138k_pinout_20261022_012244_620182/`。`pinout.json` SHA256 为 `9a139b0523c8bd02ffdc6936055e70d9ffb4fb75669b3d6bee8f9d08f6140915`；位流身份为空，不存在新板整机 `.gprj`／位流。

工作区起点仍为 Git `3e1475e0f4c498d2171cb17269422ca6cb37d305` 加未提交修改；精确配方如下，不能把起点提交说成包含新配置的干净提交：

| 配方输入 | SHA256 |
|---|---|
| `boards/custom_138k/pinout.json` | `2213484d9472d192f877beb6323f13b79bc3b832f6f45f71fb968f8c70f802ae` |
| `tools/workstation_pinout.py` | `2a86e6c788d2d38db66f7b5e745a2f67a1a1249f3eab0a6a09f55f93ec33e734` |
| `tools/workstation_baselines.py` | `96db9cf95c8747f68ffd4c9949f6774baa51eda6a43b8ff314d9a7aa14167ac0` |
| `build.py` | `41ddc319c3f01dbcd82c1a70fb9567d92d10c0d2042b25a924d9875c1ffd9381` |

## 4. 验证与设备可见性

64 项测试全部通过，无跳过：引脚回归 25、已接受输入边界 10、固件暂存 6、启用 `GW138K_VERIFY_CLEAN_PREPARE=1` 的基线回归 23。干净 clone 的 accepted full83／pinned timing85／resource-timing 输入分别与当前工作区的对应路径逐文件一致，既有 trace CDC 和 lifecycle 仿真通过；未运行综合／P&R，也没有将这些旧路径的仿真当作新 USB2 验收。

用户告知插入调试口后，2026-10-22 01:22 起复查 USB：`openFPGALoader --scan-usb` 返回 `empty`，`lsusb` 仅列根集线器、摄像头、Intel 蓝牙和 Apple 键盘，无可识别下载器；`/dev/serial` 无串口链接。未因看到历史调试器序列号而假定同一目标已连接，也未进行有写入副作用的探测。

只读枚举日志保留在上述输出目录 `readonly_usb_inventory.log`，SHA256 `22138de428a28d66d0200258c300beb9464644706574f50aa14fffbb46012549`。当前不能读回目标 IDCode／UserCode／Status；这些均是未知，不沿用昨日结果。需检查数据线、目标供电，以及下载器是否确实连接到运行本任务的电脑。

## 5. 继续条件与回退

硬件电平来源核清后，继续新板原生适配和针对性仿真，再做完整综合／P&R、IO／时序／CDC／PLL／资源及功能门禁。目标被唯一识别后才可 SRAM 下载并按新板验收；Flash 固化须在该候选验收与读回成功后执行，并单独记录 Flash 校验与启动证据。本次授权不需要重复申请，但不能代替这些技术条件。

没有改写冻结基线、vendor、`p11.cst`、现有部署索引或板卡；回退路径仍是既有旧板配置与部署记录。无关未跟踪文件和历史结果保留。
