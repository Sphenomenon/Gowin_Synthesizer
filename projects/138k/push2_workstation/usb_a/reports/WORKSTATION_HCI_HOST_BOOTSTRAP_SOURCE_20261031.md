# HCI host flow bootstrap 源阶段

日期2026-10-31。隔离clone基点为host RX源阶段 `4a7600cb0f83ab3a5c275d789f44cda5e086db93`；既有sealed delivery保持不变。该阶段尚未由整机profile选择。

新增 `workstation_hci_host_bootstrap.sv`、实际共享owner／RX联合bench和runner。显式无link initializer handoff后，依次发送真实BR／LE Read_Buffer_Size、与flow owner的pool配置事务、Host_Buffer_Size（默认276字节／4物理槽／无SCO）和ACL-only Set_Controller_To_Host_Flow_Control。所有命令经唯一owner0接受与响应路由，producer不持有另一份credit。LE count0保留BR共享池语义；原始BR容量不被截成8-bit或虚构。

发现原规范化HCI响应缺失CommandComplete／CommandStatus类型会让status0错误充当最终成功，因此event decoder和flow owner新增显式种类sideband并原样路由。四个bootstrap opcode均只接受匹配的CommandComplete；原18-bit应用event布局不变。bytes持续到实际transport_done，不在accept或response时提前复用。只有最后响应与退役均成功才一次激活host RX。

每个OFFER／WAIT／POOL独立32-bit超时，quota／transport／response／pool停顿均继续计时。默认50MHz、每阶段50,000,000周期；九个busy阶段接近9秒的上界加有限转移边沿，不是任意时钟下固定9秒。controller fault、配置漂移、提前link及deadline优先于同拍最终成功。错误、重复、意外响应、坏容量或transport违规锁定fault，必须由外层公共恢复，不自动重发。

## 验证

最终证据：`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-hci-host-bootstrap-v1/verification-v3/verification.json`。入口：

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_host_bootstrap.py --output /absolute/external/empty-dir
```

| 范围 | 结果 |
|---|---|
| 实际bootstrap＋真实flow／RX | 418 checks、32场景、4条命令、独立／共享两种pool、5类timeout阶段 |
| 关键边界 | 实际逐字节命令、顺序／pool backpressure、早到response／晚退役、quota0、原始BR大容量、LE count0／16-bit坏count、geometry／link／handoff、status失败、四opcode成功CommandStatus负测、重复／错误owner／opcode、最终同拍fault／deadline、一次activation |
| 行为突变 | 17项全由实际断言拒绝，包括跳过LE／flow enable、pool忽略ready、伪造容量／SCO、参数长度错误、提前释放transport、timer停转、忽略kind／错误／geometry／deadline／owner、重复activation |
| 参数与lint | 3个非法timeout参数拒绝；四module的Verilator5.052 `-Wall`无warning豁免；Icarus13.0实际编译仿真 |
| 前序回归 | RX160,228 checks／13突变；flow116,780 checks；event9,174 checks；原11突变全拒绝。event bench同时验证原始CC／CS经真实flow保持kind |

`verification-v1`保留早期pool突变存活失败；补充八拍pool停顿断言后v2通过354 checks／28场景／16突变。v3加入CC／CS种类后完整重跑；v1／v2不是最终source身份。输入／工具／输出哈希由runner及外部sealed delivery完整绑定。accepted source-boundary17项回归及diff whitespace检查另存外部日志。

| 最终测试输入 | SHA256 |
|---|---|
| bootstrap RTL | `497865e4498f3174a592a77d4f2a7b61a61cef4a4b07a97f868d5ad870a5b5d0` |
| flow owner（显式response kind） | `8240975d4f1e119c86b7f5a0dd743f6db96dc67caa688c9992413a5a68e223e5` |
| event decoder | `f0b25d9f41d789d322728c5d9b8fa3887130d48711a21e56249dba77cf546d45` |
| bootstrap bench | `09a0aab7de79e2b46fc6dc345059fb7ab88558744cb16bfacacb226b520c61c1` |
| bootstrap runner | `bb0fb0cc044cf3d12b3169e6b3a2c3488dc0df2e856b33824c39f561c6036d99` |

## 原BLE保持门槛与回退

真实接入须在原initializer advertising／link前增加明确handoff、停止旧命令authority，再由唯一owner建立BR／LE／RX状态；当前原initializer会一直走到advertising开启，不能拿其最后的initialized信号冒充安全接管。原bridge的credit与GATT逻辑credit仍需退休为非授权观测，不能保留两个物理发送权威。原BLE ATT／GATT协议、MTU、UUID、业务向量、重连／时限及控制器能力拒绝必须重新验证。完整接线说明见[README](../rtl/bluetooth/hci_owner/README.md)。

本阶段不含native profile选择、H5 router／payload RAM／DMA／CPU mailbox、实际初始化改造、BLE行为保持实证或控制器命令支持实测。不得把source仿真写成当前板上Host_Buffer_Size生效、A2DP吞吐、手机互通或SIG qualification。没有EDA／STA／CDC／PLL／净资源或SRAM／Flash证据。回退为移除这一未选择producer及kind sideband，不改变现有production源策略或板上身份。未来集成须新source／配置／bitstream身份和独立硬件证据。

依据Core6.0 HCI §4.1／4.2／4.3／4.4、§7.3.38／7.3.39／7.3.40与BR／LE buffer readback、CommandComplete／Status定义。完整规范只在前序外部 `b04-hci-owner-v1/standards/`保留，URL／SHA256见[前序报告](WORKSTATION_HCI_OWNER_SOURCE_20261031.md)。
