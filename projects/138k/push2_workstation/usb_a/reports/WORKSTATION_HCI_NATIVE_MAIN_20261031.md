# 原生共享 HCI 主树复验与 include 闭包修复

作者 `0d154b3` 导入主树 `c820005`，精确来源锁刷新为 `a1026bf`，
include 修复为 `b4cb7f6`。保留主树 metadata BSRAM、RTC单标量／可见边界审计；
accepted、vendor 和 frozen baseline 不变。仅显式 HCI profile 选择新的物理额度 owner。

独立整合树重跑268项 native owner检查、11个行为突变和真实UART8E1／H5仿真：
253个测试补丁字节、四条host bootstrap、十次host return、三条notify及重连通过。
实际C／APB／parser／raw-DDR旧业务1,701检查、15个突变通过，136条WIRE／BLOCK
报文与legacy参考一致。导入主树后再通过accepted来源17项、business来源／prepare
八项及实际HCI prepare verifier；默认profile 22项中21项通过、一项明确前置跳过。

联合接入发现原HCI provider `include` 的business包装文件未被拷到prepare目录。
补入 `HCI_DEPENDENCIES`，只更新受影响来源锁；没有修改旧准备结果。
对原 `247a7d85` 实际278份enabled Verilog执行
`iverilog -E -g2012 -grelative-include -I.`，明确因缺该文件失败；
新候选同命令通过，六个实际prepare篡改负控被拒绝，恢复后verify通过。
较早只使用 `-I.` 的Icarus检查因原MP3局部include失败，按源文件相对include语义
修正检查命令，保留该记录。预处理证明include闭包，不代表综合或物理接受。

| 最终prepare | 身份后缀 | staged／enabled |
|---|---|---:|
| 显式共享HCI | `313aea7bea71ecef` | 627／281 |
| 原business | `81e2d489abd2cf31` | 614／272 |
| 原默认runtime | `294a2bc845a1db6c` | 581／261 |

默认最终581项staged与固定 `4e5dfeea` 逐字一致。此前隔离clone的default-v1仅USB
build.log不同，include修复后其完整来源快照按原规则失效；重新从主树prepare-v2，
没有编辑旧元数据或归一化发布哈希。business的staged变化为GATT两份源副本、
显式选择工具及隔离clone的USB构建日志；GATT新参数默认关闭，旧业务实测保持。
HCI v2比v1新增被漏拷的包装文件，enabled数不变。

父级封存 `~/.cache/gw138k-task-20261030/native-hci-main-parent-v1` 保存486份源码
和5650个外部文件身份，seal
`9f03a4eb4413db9f7be49458bdee5e2e0fb40b0bdd14d411f3f5f28ac5788b9b`，
独立复验通过。机器记录见
[hci_native_main.json](workstation_task_20261030/hci_native_main.json)，协议细节继续由
[原生传输契约](../rtl/bluetooth/hci_owner/NATIVE_TRANSPORT_CONTRACT.md)维护。

本阶段未选择CPU Classic／SBC／PCM runtime，没有综合、P&R、真实controller／手机、
持续音频或硬件接受；新增RAM映射、成本和CPU期限待后续候选验证。
没有位流、板卡、SRAM或Flash操作。回退可选原business profile并重建其固定来源，
不得转授本阶段没有取得的物理／功能接受。
