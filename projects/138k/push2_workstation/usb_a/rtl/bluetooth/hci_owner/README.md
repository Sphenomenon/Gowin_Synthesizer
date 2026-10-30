# 共享 HCI accounting 源组件

本目录是尚未由构建 profile 选择的第一方 RTL。它为现有 H5 transport 与未来 BLE／CPU Classic 路由提供单一控制器账本；不包含另一份 UART／H5、GATT 或 A2DP 栈。当前生产 `bt_acl_bridge`、`bt_gatt` 与 initializer 仍按原输入选择，不能把本组件的仿真结果写成已完成整机替换。

## 发送账本

`workstation_hci_flow_owner.sv` 的所有输入在同一时钟域，控制事件已经校验。配置来自成功的 BR `Read_Buffer_Size(0x1005)` 和 LE `Read_Buffer_Size(0x2002)` 返回：LE count=0 选择 BR 共享池；非零选择独立 LE 池。各池 data length 限制为控制器报告值与 276 的较小值，使四字节 HCI ACL header 加 data 不超过当前 H5 payload280。**这只约束主机发往控制器的包，不约束控制器发回的包。**

默认两个活动 handle，各自持有 outstanding **物理 HCI ACL 包数**。一次发送 grant 在 `valid && ready && send` 的上升沿与 transport 私有槽的不可撤回接受原子发生；transport 必须已经取得稳定 payload 的所有权。H5 自身重传不再次 debit。若接受后 transport 失败或结果不确定，整个控制器账本进入 fault；不能凭重试或 CPU 重启退款。禁止同拍提交 ACL 和 command；公平仲裁与 payload 预留由外层实现。

每次成功 open 获得严格递增的非零 32-bit handle generation；重用相同 HCI handle 也不能接受旧 CPU 描述符。代次耗尽后拒绝新 open，保留其他 handle。表满／重复 open／未知 close 返回 `handle_rejected_o`，外层必须断开或采取明确恢复，不能继续声称新链路已登记。成功 Disconnection Complete 回收该 handle 全部 outstanding，保留另一 handle 的包数。

Number Of Completed Packets 作为 start→0..63 pair→commit 的原子事务输入；期间不发送 ACL 或修改 handle。重复 pair 聚合，全部核对通过后一次退款；over-completion 不会局部退款。未知 handle 只累计饱和诊断，不凭空增加 credits。abort 只供尚未被外层接受的事务显式撤销，丢弃 staged refund；真正控制器事件若损坏或失去同步，外层必须 fault 控制器，不能靠 abort 继续运行。事件最大 pair63 来自八位参数长度，Core 的 Num_Handles 字段本身允许0..255。

普通命令保守串行化为一个 pending opcode，保留控制器 Num_HCI_Command_Packets 配额。owner0=初始化、1=BLE、2=CPU Classic。CommandComplete／Status 按 pending opcode 路由至原 owner；非零 status 是正常失败结果；opcode0只更新 quota。错误 opcode、超时、transport fault、违规 send 均锁住账本，fault 优先于同拍成功发布。`Host_Number_Of_Completed_Packets(0x0c35)` 仅允许专用硬件 owner3，按规范绕过普通 command credits 且不成为 pending opcode；异常返回该 opcode 时 fault。外层仍须校验其参数，不能让 CPU 标记 owner3 冒充 receive-credit authority。

CPU observer reset **不能复位此账本**。共同硬件 reset 会清账本和 generation，因此必须同时关闭 transport、清除所有旧队列／DMA／CPU 描述符，建立新的外部 reset epoch；不能用本地 generation 代替跨硬件 reset 的身份。

## 原始事件校验

`workstation_hci_event_decoder.sv` 读取外部稳定 packet RAM，读延迟一拍，与现有 H5 接口一致；每字节两周期，不复制完整 event RAM。包长2..257，要求 HCI parameter length 与完整 packet length 精确相符。支持 BR ACL Connection Complete、LE Connection Complete／Enhanced v1、Disconnection Complete、CommandComplete／Status、BR／LE buffer readback，以及0..63 pair的 NCP。成功生命周期及 NCP 的16-bit handle必须在0..0x0eff，不能先截成12-bit再校验。失败的连接／断连事件不改变活动 handle。Hardware Error／Data Buffer Overflow 与结构错误均 fail closed，需将 `fault_o` 接入共享账本的 transport fault。

NCP 在读取期间暂存 pair 到账本，整包验证结束才 commit；后段出错时不会退还前段 credits。其他 complete event 仅通过外层长度校验后报告 `packet_done_o`，由后续有界 router 处理其业务语义。`packet_done_o` 只表示结构校验及 sideband 派发完成，不表示命令执行成功或全链路仍健康；外层必须同时检查 controller fault。open 的 `handle_admitted_o/generation_o` 是共享账本实际准入结果。

packet RAM 必须持有 valid、length 与 bytes，直到 `packet_release_i` 后看到 consume。**release 必须来自 FPGA 有界 router，不能直接等待 AE350 服务。** 路由层仍需独立安排原始事件复制、队列满后的 Classic fencing／控制器恢复和 BLE 优先级，避免 CPU 停顿阻止后续 NCP／命令处理。这一层目前未实现。未知事件不等于未知事件语义已支持；SCO／ISO、LE 新版 connection 事件也未承诺。

## 集成门槛

尚需实现并验证 Host_Buffer_Size(0x0c33) 的276字节接收长度、Set_Controller_To_Host_Flow_Control、控制器→主机每个物理包的 buffer lease／return、专用0x0c35包构造与发送、CPU慢端的回收／丢弃政策。未执行这些命令前，不能假定控制器遵守 H5 的280字节上限。A2DP v1.4 §5.2.1 要求至少支持335字节 L2CAP MTU，因此不能用240字节 MTU规避；CPU当前计划的672字节重组与 HCI 分片是不同边界。

接入时还必须退休旧 `bt_acl_bridge` 的控制器 credit authority，并使 `bt_gatt` 的旧逻辑 PDU credits 不再授权物理 H5 发送。现有 BLE 协议／时限、初始化 BR／LE／host RX flow bootstrap、payload 缓冲、命令仲裁／超时、跨 reset 外部 epoch、配对／认证、CPU raw event／ACL邮箱、音频代次、速率确认与 DMA 都尚未组合。

本阶段无生产 source selection、EDA、资源净收益、时序、实板或手机互通结论。验证入口：

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_owner.py --output /absolute/external/empty-evidence-dir
```

依据为 Bluetooth Core6.0 HCI §4.1.1／4.2／4.3／4.4，§7.3.39／7.3.40 与各对应 event；A2DP v1.4 §4.3.4／5.2.1。完整规范只保留外部取证，不向仓库复制其版权正文。阶段报告记录 URL／SHA256 和验证范围。
