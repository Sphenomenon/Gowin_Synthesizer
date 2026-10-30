# 共享 HCI accounting 与原始事件校验源阶段

日期：2026-10-31。仅新增未选择组件；不修改既有 BLE／CPU owner、生产 profile、frozen baseline、H5 transport 或历史证据。源基点为 `6ae34680e5b2ac89854cdc2bf868d013edd9f331`；最终提交和交付 seal 另由 handoff 绑定。

## 本阶段结果

新增 `rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv`，统一 BR／LE 控制器发送 buffers、物理 ACL 包 outstanding、handle generation、命令 quota／pending owner 与特殊 host receive-credit command 准入。LE count0 使用 BR 共享池；buffer length 按控制器能力与276 data bytes取小值；HCI header加data不超过当前 H5 payload280。generation 不回绕，CPU旧描述符不能借 handle 重用取得授权。成功断连仅回收其自身 outstanding。NCP聚合全部pair后原子退款，over-completion不局部退款，未知handle只累计饱和诊断。

新增 `workstation_hci_event_decoder.sv`，直接读取现有 H5 风格的一拍延迟、外部不可变 packet RAM。支持完整 BR／LE(v1)连接与断连、CommandComplete／Status、BR／LE buffer readback、0..63-pair NCP；长度、16-bit保留handle位、成功状态和原始字节序均显式验证。NCP后段错误不会退回前段credit；普通命令响应按真实pending opcode路由，opcode0只更新quota。timeout／无效事务优先于同拍成功，transport或解析故障锁住控制器账本。Hardware Error／Data Buffer Overflow进入明确故障边界。

普通命令保守限制为一个pending，0x0c35仅允许专用硬件owner3且绕过普通command quota；不含其参数构造、host RX ledger或发送队列。ACL／command的send握手必须与transport私有槽的不可撤回接受原子发生；H5内部重传不再debit，失败不猜测退款。所有接口同域；无CDC或CPU邮箱接入。完整接口约束见相邻[README](../rtl/bluetooth/hci_owner/README.md)。

## 离线验证

可重现入口为 `python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_owner.py --output /absolute/external/empty-dir`。所有波形之外的实现执行文件、变异源码、日志和JSON留在外部证据目录；本次未产生波形。

最终本地证据：`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-hci-owner-v1/verification-v3/verification.json`。

| 验证 | 结果与边界 |
|---|---|
| 实际flow RTL | 116,780 checks，15场景，10,000步独立credit模型；共享／独立池、重复pair、over-completion、断连、重连／旧代次、最后generation、未知计数饱和、特殊命令、异常响应、超时竞争 |
| 原始事件+真实flow组合 | 9,174 checks，1,830个event；其中1,806个fixed-schema替代长度负测，最大257字节event、最大63-pair NCP、空batch、迟到坏handle、生命周期成功／失败、BR／LE读回与命令归属 |
| 行为突变 | 11项全部由真实断言拒绝：移除共享池、旧代次获准、断连不退款、特殊命令被普通quota阻塞、opcode0误完成、超时同拍误成功、忽略外层长度、先截handle、漏NCP handle校验、伪造LE count、忽略packet寿命 |
| 严格lint | Icarus13.0实际编译／仿真；Verilator5.052逐module `--lint-only -Wall`，无warning豁免 |
| 参数错误 | HANDLE_SLOTS=0／17，H5_ACL_DATA_LIMIT=0／277均明确拒绝；功能验证使用默认2／276 |
| 既有accepted输入边界 | `sim/test_current_workstation_sources.py` 17项通过；无生产输入选择变化 |

验证过程中，早期“经典断连不退款”突变未被原随机场景覆盖；加入显式共享池BR outstanding断连与保留LE场景后拒绝该突变。初始原版／失败结果保留在外部 `verification-v1/`，不以覆盖旧证据替代回归。中间 `verification-v2/` 和最终 `verification-v3/` 同时保留。

独立代理对下列精确RTL哈希完成只读审查：共享／独立池守恒、断连、重复NCP聚合、63-pair与求和上界、旧代次、命令quota／opcode0／0x0c35、fault优先级、RAM读延迟、最后pair到commit的节拍和packet寿命均未发现本阶段契约内的具体阻塞。审查未重新运行测试，也未编辑源码；不扩大上述离线证据范围。

最终测试输入SHA256（其余新增说明由交付seal绑定）：

| 输入 | SHA256 |
|---|---|
| flow_owner RTL | `3a93b7e59752014de83215387afa6b94b136dd341f98a7e3642d6f8bcec9d579` |
| event_decoder RTL | `8b9ae8ec9a9fab9fc2e2313e3199a60b1e1ec3fe957d4497237b28be8dac7792` |
| flow bench | `aa264aa73f761b9f905c764a8874539282bc26be0ecc0a917b71ed41256c2332` |
| event bench | `5b1e1414462d6e6ac4b0319f81e5a68d2fc52e1b5deeb9d1d144b009cc854e1d` |
| runner | `4534bba07d3e30d5f695c2b6e2d92eb42d8f357fbd930c2b6a009c8290e68f4c` |

## 规范取证与实际边界

完整官方规范只留在外部 `b04-hci-owner-v1/standards/`，含URL／时间／SHA256回执，不向仓库复制全文。

| 官方来源 | SHA256与所用条款 |
|---|---|
| [Core6.0 HCI](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-60/out/en/host-controller-interface/host-controller-interface-functional-specification.html) | `c5015f5f22f255f5672e7794799110f012d799d4dd8b3a1122d49488962f92c7`；§4.1.1共享buffer／物理包计数，§4.2／7.3.40特殊0x0c35，§4.3断连回收，§4.4命令quota及opcode0，§7.3.39 Host_Buffer_Size与各event |
| [Core6.0 L2CAP](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-60/out/en/host/logical-link-control-and-adaptation-protocol-specification.html) | `1b796894811a9eb0c23f6d9adb2efba0e30891fec8fa0ec02571cb66263d57b7`；§4 signaling MTU／多命令、§5.1 directional MTU |
| [A2DP1.4官方HTML wrapper](https://www.bluetooth.com/specifications/specs/html/?src=A2DP_v1.4/out/en/index-en.html) | `cb1c8e5e5c2a345c39b9529e28b7ac7ad960f761cc70cb115e62bca914a90dd6`；完整profile嵌入wrapper，§5.2.1最低L2CAP MTU335，§4.3.4 SBC分片计数；直接embedded-source后续请求403，未冒充成功 |

当前H5 `MAX_PAYLOAD=280`、地址／host接口9-bit，而wire header完整12-bit长度已验证；它当前拒绝DIC flag，没有启用H5 body CRC。不能将包长问题写成wire header截断，也不能声称已有body CRC保护。现有UART fast921600baud的8N1理论上限92,160B/s，还未扣除H5 framing／escaping／重传／BLE；此阶段不宣称A2DP吞吐预算闭合。

## 尚未完成与回退

尚未接入真实native组合，也未退休现有bridge和GATT两处控制器credit权威。后续必须统一这两处并验证BLE功能保留；GATT如保留发送窗口，其身份只能是应用窗口，不能独立授权H5物理发送。还缺BR／LE buffer bootstrap、Host_Buffer_Size276、controller→host flow enable、按物理包的host RX lease／return和0x0c35构造、独立有界raw router／CPU邮箱、timeout、跨reset队列fencing及CPU connection／security策略。

发送长度裁剪不约束控制器→主机方向，必须实际发出并验证Host_Buffer_Size和接收流控能力才能保留H5上限。A2DP最低MTU335不能压成240；CPU672字节L2CAP重组与HCI276字节physical data是两个边界。packet release不能等待CPU，CPU洪泛／停顿时的Classic终止、host credit回收和BLE优先级尚待组合。H5事件次序必须保留，不能把disconnect前的旧NCP重排到相同handle的新open之后；generation只保护显式带身份的CPU描述符，不能从无generation的wire event恢复丢失的顺序。

本阶段无ROM／RAM整机fit、EDA、净资源收益、STA／CDC／PLL、SRAM下载、Flash、物理音频、手机互通或SIG qualification结论。回退仅撤去尚未选择的新增文件；原profile、板上身份及回退bitstream均未改变。主集成需重新命名候选并记录完整source／configuration／bitstream身份，不能继承既有accepted身份。
