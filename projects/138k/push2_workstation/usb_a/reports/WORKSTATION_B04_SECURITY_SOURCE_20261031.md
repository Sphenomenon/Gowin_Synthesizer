# B04 BR/EDR connection/security source stage — 2026-10-31

本批基于冻结父源 `4f8e42d`，新增未选择的第一方 `classic_security.c/.h`，
通过实际 HCI 命令／异步事件、密钥强度和抽象原子 bond owner 完成 Classic
非 SDP 准入链。它不是 native HCI 接线、物理持久化后端、真实手机互通、
A2DP/GAP 符合性、完整 ROM128 容量／调用链栈／周期验收或板测。
未运行 EDA、操作板卡或写 Flash；accepted/pinned、vendor、旧 seal 与历史证据不改。

维护契约见 [CLASSIC_SECURITY_SOURCE_STAGE.md](../firmware/ae350/CLASSIC_SECURITY_SOURCE_STAGE.md)。
当前明确策略为 SSP Security Mode4 Level2、NoInputNoOutput、OOB0、GeneralBonding，
不声称 MITM／Secure Connections／legacy PIN。新 pairing 仅接受 type4 P-192
unauthenticated combination key；可复用已持久的 type4/type5，不伪称 NoIO 新建了
MITM key。发现不可满足的 remote MITM 要求时明确失败。

启动依次实际提交 1003／0c56／1004(page1)／0c1a(page scan2)，SSP controller/host
能力校验成功后才开放 page scan。仅真实 ConnectionRequest 与实际 PL 容量产生
AcceptConnectionRequest；成功 ConnectionComplete 的 generation 来自唯一 PL owner。
读取真实 remote SSP 特征，支持 peer-auth 与特征查询交织，IO request 最多延迟1000ms。
AuthenticationRequested 的 Status0 只表示受理，必须另有 AuthenticationComplete；
SetConnectionEncryption 另等 EncryptionChange，再读 1408 的实际 handle／7..16-byte
key size，且不得降低已存 bond 的最低长度。新 key 的 atomic replace 真正完成后，
才调用实际 Classic security grant；原子后端本轮只定义契约，未接板上 Flash。

Classic 默认拒绝未安全的 AVDTP，返回 L2CAP security-block0x0003、不分配通道，
security owner 在回复被不可撤回接受或100ms后提交真实 owner2 Disconnect。SDP
保留未加密例外。该立即拒绝／关闭是保守实验策略；手机可能用 service request
触发认证，真实会话时序尚未验证，不能由离线链路推断互通。

owner2 命令 token／bytes 在实际 transport_done 和 matching response 两者齐全前
保持；不增加另一套 command/ACL credit、H5 retry 或 reset authority。CPU observer
reset 不清 PL 账本；不确定接受要求外部 recovery。旧 initializer 必须先在 advertising
与连接前交接，旧 bridge/GATT credit authority 必须实际退役；这些 native 条件仍未实现。

## 最终离线结果

证据目录：`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-security-owner-v1/verification-v7/`。
最终 verification SHA256：`c6ef9f2c4e6c5e861c93592d44fdbdf0d97de6a4abe3e60f5dcd037c9f57d1e0`。

| 验证 | 实际结果 |
|---|---|
| Security 原生／ASan+UBSan | 各 14445 checks；各4000 valid-envelope fuzz |
| Security 负控 | 26 killed：25项单变异＋1项双缺失历史故障变异 |
| 重叠保护正控 | 1项单删 generation 早退，被独立 inactive-close guard 覆盖，按预期完整通过；不计为 killed |
| Delay Reporting | 原生／san 各11199 checks；18 mutants killed |
| 原 Classic | 原生／san 各49640 checks；15 mutants killed |
| SBC 真解码参考 | 11 cases 保持；原生／san PCM 一致，既有 BlueZ 误差阈值通过 |
| accepted 来源／diff | 17项通过；diff whitespace 检查通过 |

既有协议 fixture 现在显式提供受信安全 grant；新增 security fixture 必须经实际
命令、异步事件、key-size 与 durable-model completion 才能得到同一 grant。
既有回归次数增加来自这些显式 grant 检查，不覆盖已封存旧报告的原始计数。

| RV32增量对象 | text+rodata | caller state | 最大单函数 frame |
|---|---:|---:|---:|
| 新 security owner | 11876 bytes | owner540；command48；bond32 bytes | 64 bytes |
| 当前 Classic | 15885 bytes | 2876 bytes | 480 bytes |

这是独立对象的静态编译数据，不能与 Delay 版完整 ROM128 seal 混为同一版本，
不能直接相加代替完整链接，也不是 store callback 调用链栈／CPU周期／实时期限或物理资源证明。

## 独立 review 与失败证据

已修复并在维护 fixture／负控保留：未提交新 key 断链后遗留 new_key 导致 forget
永久 BUSY；把 auth/PIN 等状态06/18直接当 Disconnect reason；旧 accepted 命令迟到
失败重新 closing inactive context；旧 ACL／peer事件在实际断链后重新进入策略副作用。
关闭原因映射为合法05／13，原 cause 另存；已接受旧命令 bytes 保持到退役，未接受
命令与临时 pairing facts 清除，pending durable revocation 继续完成。

原始独立 reproducer 与父级失败输出保持。`peer-recheck-v2/` 用最终维护源码复验：
中断 pairing 后 forget 可用、status06 发 reason05、late old status02 不阻止0409重连、
normal/violated 两条断链后 late ACL 都 STALE 且不复活 closing。原 reason-bug harness
最后原本给出 InvalidParameters12；复验明确改为检查合法05并给成功0，原件未改。

本地 v5 与父级 `b04-security-root-review-v1` 都真实发现单删早退的 mutant 存活；
原因是独立 inactive-close guard 已覆盖它。这两次失败没有改写为 PASS。最终 v7
把此单删列为 masked expected-pass control，并额外同时删除两道 guard，真实复现
旧故障且被维护 fixture 拒绝。不得把重叠保护的单删结果计为 killed。

## 保留门槛与回退

atomic store 只有接口和内存模型，无物理 key backend。replace/delete BUSY 有1000ms
有界轮询；LinkKeyRequest load BUSY/error/corrupt 保守负回复并关闭，forget load
BUSY/error/corrupt 直接 fence，不声称每种 store 操作都会轮询。存储失败不开放媒体，
remote key-missing06原子撤销后断开，下次真实连接才重新配对；没有同链无限重试。

成功 refresh 暂停并清理非 SDP 工作、重新查 key size，要求通道重新打开；尚未实现
透明连续播放。完整 L2CAP RTX/ERTX／connection timers、真实 phone 时序、native
BLE共存／credit退休、payload RAM/MMIO、可靠 epoch、实际延迟／漂移、完整固件与
调用链／周期、音频输出、时序／资源与硬件验收仍单列。未变更任何生产选择，回退
仅不导入此 source commit；已封存 Delay/HCI/decoder 与 accepted 输入保持独立身份。
