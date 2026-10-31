# B04 A2DP Delay Reporting 源阶段

2026-10-31。隔离clone基点 `beae08d7dd7ddb70a12b217a2b7afd3cea27e039`，冻结前序CPU／SBC／HCI delivery不改。仍是未选择的实验源组件；没有修改构建profile、firmware选择、冻结输入或板上身份。

## 实现及边界

在既有 `classic_service.c/.h` 中补SNK的Delay Reporting发起角色，沿用单链路、单signaling CID、原HCI ACL不可变token API。没有新增HCI command／credit／Reset／UART authority。GetAllCapabilities提供08/00，basic GetCapabilities不泄漏这一非basic能力；SetConfiguration验证长度／重复并要求真实外部clock与delay值已具备。远端SEID及能力只在最后配置响应片段被唯一HCI owner接受后提交；此时把原远端INT SEID用于DelayReporting角色反转后的ACP地址。

五字节AVDTP命令是label／command、signal0x0d、remote SEID、以0.1ms为单位的MSB→LSB 16-bit delay。首次报告先于等待的Open派发；**OPEN可在完整报告被发送owner接受后进入，START还必须等匹配的peer Accept及原物理rate-ready**。owner仍须保证同link已接受packet的顺序及H5退役前的稳定bytes；源码队列接受不等于实测空口发送。普通peer command与本机report可使用相同数值label，方向不同，不互相完成。

准确匹配signaling channel／活动link epoch／PL generation／label／opcode的Accept才完成；Accept不得有参数，Reject／GeneralReject与坏匹配响应分别明确fence。支持有界分片response并核对message type／label一致性。其它旧／重复／无关响应消耗为MALFORMED，不推进report。没有协商DelayReporting的旧路径不主动发报告。

`tick(now_ms)`使用独立单调毫秒时钟，每轮其他服务方法之前执行、至少每100ms调用。发送阶段整体1秒（包括quota／部分片段／明确拒绝停顿），最后片段接受后另起peer响应1秒。uint32回绕允许，倒退或≥2^31ms歧义跳变fence；deadline先于随后送达的成功。C代码不能发现外部clock服务完全停转，真实调度／watchdog仍待集成。GAVDP1.3信令timer建议0.5–3秒，本地1秒在此范围。

changed delay在控制TX／报告忙时返回BUSY且不消费新值；>65535拒绝而不截断。每link最多16个不复用label，耗尽显式fence，Abort／同link重配置不重置历史；这是保守实验资源策略，并非规范声称的限制。disconnect／cancel／UNCERTAIN／timeout清本地旧work；实际连接策略owner仍必须断连／恢复，不能只停CPU对象而假装控制器链路已关闭。

## 验证与复现

入口：

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/run_ae350_delay_reporting.py --output /absolute/new/external-dir
```

首次最终候选证据：`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-delay-reporting-v1/verification-v1/verification.json`。独立root review以同一C／H／fixture／runner哈希完整重建通过，另存 `b04-delay-reporting-root-review-v1/`，不把它混入producer封存包。

| 范围 | 结果 |
|---|---|
| 实际新增C fixture | native／ASan+UBSan各11,049 checks，输出一致；basic／all／configured能力、未就绪拒绝、remote SEID、大端0／0x1234／0xffff、4／27／276物理片段、早排队Open、START等Accept、有效分片response、长度负测、错误label／opcode／Reject、clock回绕／倒退、TX／response超时、deadline后成功拒绝、BUSY稳定、断连／Abort／取消／旧epoch与16 labels耗尽 |
| 新行为突变 | 18项全部通过实际断言拒绝，包括能力泄漏／遗漏、SEID／字节序、未就绪配置、漏首次报告、TX即提前完成、错误label／opcode／Reject／Accept长度、两个deadline／clock回退、label回绕、BUSY覆盖、早START及分片message type丢失 |
| 前序Classic全回归 | native／ASan+UBSan各44,612 checks；原15行为突变全拒绝，4000个有效envelope随机SDP／AVDTP样本保持；旧录音／BLE生产逻辑不由这些fixture代表 |
| 实际SBC回归 | 原11条wire→frame queue→真实OI decoder→参考PCM用例保持，通过native／san一致性和独立BlueZ误差门槛；无decoder源码改动 |
| RV32增量 | text+rodata15,549字节（基点14,485），service对象2876字节（基点2848），最大单函数frame480字节不变；**不是完整固件link／调用链stack／周期deadline证明** |
| 其它 | accepted source-boundary17项PASS，diff whitespace PASS；root逐项审查TX生命周期、SEID／label隔离、协商／不协商与取消／timeout后无阻断 |

| 最终行为输入 | SHA256 |
|---|---|
| classic C | `528bebd91596e05f7ac227e84e7940456fcb4b66b692bb1a792b387fd9b3d921` |
| classic H | `af14f6ffe3949fe9bf8f5ad92b7c32b3ee4e850c22dc4b838e02c9001c6245e8` |
| delay C fixture | `399aca93aad2fd4ebd7ee20d1ae9344563afeb58dc702088a4521fde59b39c08` |
| delay runner | `067700e847fd62f167cd3aac6fa05e0505f328e6d0766e2ce79dbfc9c538638b` |

## 实际delay／安全与后续验收

本源组件不测量delay。GAVDP1.3 §3.1.8.2–.3定义从基带收媒体到用户实际呈现、最大偏差±30ms（建议±15ms），且报告间持续满足并补偿漂移。实际audio owner必须给稳定运行范围估计，包含controller／HCI缓冲、解码和呈现；不能把瞬时FIFO填充或固定零值冒充。更新等待期间也须保持精度，做不到应取消。源码向量中的边界数值只验证编码，未测真实延迟、漂移、声画同步或radio吞吐。

配对／bond数据库、connection/security owner、SSP／authentication／encryption门禁仍缺；A2DP1.4 bondable必选，SDP例外不能扩展为未加密AVDTP／media。Host RX／bootstrap／共享HCI仍未组合到native router／payload RAM／CPU mailbox，旧BLE credit authority未退休。原ATT／GATT／业务／并发时限、C04聚合固件fit与stack、实际PCM队列／样本时钟、STA／CDC／资源、手机互通及硬件验收都仍独立。没有EDA、JTAG、SRAM／Flash操作或SIG qualification结论。

依据A2DP1.4 §5.1.1.2、AVDTP1.3 §6.7／6.8／6.19／8.19／8.21.9、GAVDP1.3 §3.1.8／8。AVDTP官方PDF SHA `3419b8af519120c246ae4ceb42eeacb125c06c8c93289e209913a5a033bcf3fc`，GAVDP SHA `148be562676c8d85bd5e3908840cbbb44541b02cccef6454514c631a95398880`；官方URL／回执写入provenance，完整PDF及渲染只在独立sealed standards checklist cache保留。接线／取消契约详见[源说明](../firmware/ae350/CLASSIC_SOURCE_STAGE.md)。

回退为移除这一未选择的DelayReporting diff，保留前序CPU源身份；不回写历史报告或重用改变输入前的候选身份。后续生产集成须显式新source／配置／bitstream及独立阶段验收。
