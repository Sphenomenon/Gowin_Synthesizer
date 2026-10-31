# 原生共享 HCI 组合：源码与 prepare 检查点

2026-10-31。基点 `f8882c5`，隔离 clone 为
`/Users/sphenicidition/.cache/gw138k-task-20261030/native-hci-owner-v1/tree`。
本阶段将已有 flow／event／host-RX／bootstrap 接到真实 H5／UART 和 AE350
原始包邮箱，由显式 `custom138k-workstation-hci-owner-v1` 选择。
它不包含后续 CPU Classic／security／PCM 联合业务，不代表 B04、时序或硬件完成。

`workstation_hci_native_transport` 是唯一物理 command／ACL 额度所有者。
initializer 完成原补丁和 0x2005 后，在真实发送退役后暂停；统一 owner 依次执行
BR／LE Read_Buffer_Size、Host_Buffer_Size=276/4/SCO0 和 ACL-only host flow，
完成响应与退役后才恢复 initializer 的 0x200a。CPU 普通命令固定 owner2，
BLE 固定 owner1，0x0c35 由专用硬件 owner3 发送；CPU 不能伪造这些 owner。
普通命令额度为零仍允许归还 host RX 包。Opcode0 CC 只更新额度，不继承此前的
CPU owner／token，不生成普通响应或 CPU 副本。

新增 CPU mailbox、BLE packet queue／fragment bridge 和原生组合根；字节经过实际
同步 RAM 读延迟后完整发布。CPU 接收队列为四槽，保留原始 HCI 事件／ACL、
epoch／handle generation／ticket／原 command token。精确 RELEASE 只退休 CPU
副本，不返还物理 controller credit；硬件物理 lease 在副本完成后独立归还。
CC／CS 与 H5 退役顺序独立，不能提前 ACK 或重放已接受事务。
CPU 慢、复位或满队列会隔离 Classic 并由同一 owner 安排 BR Disconnect，
LE 业务、NCP 和接收额度继续前进。接口细节见
[原生传输契约](../rtl/bluetooth/hci_owner/NATIVE_TRANSPORT_CONTRACT.md)。

GATT 增加默认关闭的 `SHARED_HCI_OWNER` 参数。只有新 core 显式开启，停止旧 GATT
逻辑额度作为发送授权；新 fragment bridge 同样没有另一份物理额度账本。
其余配置继续使用原选择策略和默认参数。BLE UUID／ATT／业务报文、录音下载、
18-bit 演奏事件和冻结 baseline／vendor 字节保持原契约。

| 离线验证 | 最终结果 |
|---|---|
| 实际 native owner＋邮箱＋BLE bridge | 268 checks；11 个行为突变全部由真实断言拒绝，包括 opcode0 继承旧 CPU owner、quota0 阻塞 0c35、提前 ACK、错误 token、旧 generation、RAM 字节移位及漏还 lease |
| 真实 UART8E1／H5 仿真 | 253 个测试补丁字节／两片、四条 host bootstrap；实际 GATT 发现／MTU／UUID、三条 notify、十次 host RX return、断开广告重连通过；不是板卡实测或完整 30,147-byte 补丁吞吐接受 |
| 前序完整回归 | bootstrap 418 checks／32 场景／17 突变；host RX 160,228 checks／13 突变；flow 116,780、event 9,174 checks／原 11 突变 |
| 实际旧 C 业务保持 | C/APB/parser/raw-DDR 12 组、1,701 checks、15 行为突变；136 条 wire／block 与旧 RTL 参考逐字相同 |
| 来源与准备 | accepted sources 17 项通过；新 profile 的真实 prepare／verify 为 626 staged／281 enabled；六项真实候选输入负控拒绝、恢复后重新 verify 通过 |
| 工具检查 | native transport 的 Verilator `-Wall`，仅豁免子模块未消费诊断信号／显式空输出；未屏蔽 width／latch／multidriver 告警。所有模块由真实 UART bench 编译展开 |

最终 prepare 身份为 `custom138k-workstation-hci-owner-v1-42cfbbfe775a9d6b`，
配置 SHA256 `d8da281a54711218aa29bf8f1041eb596ab152d8303d19ad0e1b3dc8ae30e0b5`；
其 source lock 包含 474 项输入。冷镜像仍由既有 AE350 business 固件产生，
尚不调用新增 Classic raw 入口，不能把接口准备当成 A2DP 正在运行。
prepare 明确选择 xPack GCC 15.2；默认 Homebrew GCC 16.2 的旧间接调用证明失败
保留在 `prepare-v1.log`／`prepare-v2.log`，未修改旧证明规则以绕过失败。

机器汇总见 [hci_native_source.json](workstation_task_20261030/hci_native_source.json)。
原始完整结果位于上述外部目录的 `regression-final-v4/verification.json`、
`c-business-final-v1/verification.json`、`prepare-final-v4/` 和
`candidate_guards.json`；其中旧 v1～v3 结果保留原身份，不冒充最终来源。
复现入口：

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_native.py --output /absolute/new/evidence
python3 -B projects/138k/push2_workstation/usb_a/sim/services/run_ae350_ble_business.py --output /absolute/new/business-evidence
python3 -B projects/138k/push2_workstation/usb_a/build.py --prepare-custom-board --workstation-profile custom138k-workstation-hci-owner-v1 --netlist-dir /absolute/netlists --custom-board-output /absolute/new/candidate --riscv-prefix /absolute/riscv-none-elf
```

没有运行 EDA、P&R 或操作板卡，没有新位流、SRAM／Flash、物理 CLS／BSRAM 或 routed
STA／CDC 接受；新增 RAM 的实际映射和净成本必须另测。CPU 服务周期、最长延迟、
安全持久化、真实 controller／手机互通、持续 SBC 音频、采样时钟漂移和完整 PCM
路径也仍需后续联合验证。回退使用基点 `f8882c5` 的冻结输入或此前固定候选；
导入主树后需保留主树新增 BSRAM／RTC 修正并生成新 lock／candidate 身份，
不能复用本阶段身份或继承它没有取得的硬件接受。
