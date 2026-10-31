# W12 raw-store START 初始化因子化

W11 实测 recording 读标签至 raw-store `write_address` CE 路径为 15 级、setup −5.009 ns，实际反馈绕经 native 接受与完整 fault veto。原始路径及实际 LUT 解码的 v2 证据保持；本阶段仅修改维护 raw-store 的已接受 START 初始化使能。来源是 W11 `custom138k-workstation-w-demo-v1-bafd43c180d52b1c` 实际消费源码，不修改 W11 冻结候选。改后 RTL SHA256 为 `214c0a5df77d11921fecb4848e5897f7b116de039f48b69cae47b7953809da1d`，完整旧版 fixture 为 `ca212e5f93c9110ba63bb5c90399558bcb5edd8ed3d096d8d9ec5956c35363a7`。

## 改动与赋值优先级

仅当 `memory_quiescent` 已知为 1 时，START 的 fault veto 使用由真实 store/native bridge 源方程推导的五项 cofactor；为 0 或 X 时保留原完整 `memory_fault_now`。原嵌套过程 `if` 保留 X 条件进入 else 的语义，不能替换成正向 `!bad` 使能。全局 fault、超时、隔离、DDR 请求／接受／响应、FIFO、取消、ACK 和完成路径均保持。

原 START 成功分支中的 `memory_generation`、`memory_next_index`、`memory_committed` 与 `write_address` 四个宽赋值移到完整命令块之后、CLEAR 完成块之前。三个 active／closed／empty 状态位、completion 与 ACK 仍在原处。完整源码逆变换检查证明范围只在这些编辑；跨越区间唯一涉及四个目标的其他写入是 CMD_CLEAR 的 `memory_generation<=command_generation`，RHS 相同且属于另一 case。之前的 native retirement／FIFO 与之后的 CLEAR 完成优先级均保留，无新增周期或时序寄存器。

唯一生产 `RAW_STORE_SHA256` 同步更新。原严格锁的拒绝记录保留，正式维护 BLE runner 通过，并再次拒绝 raw-store 漂移；未用 monkeypatch 绕过来源校验，也未放宽校验。

## 离线验证

- 实际 store/native bridge 方程逐项绑定；完整 W11 fixture 身份及全文逆变换通过。15 个独立布尔谓词及 2-bit command kind 的 fault／START 守卫等价为 UNSAT；四个移动目标的 next-state 值等价也为 UNSAT，先前值和 CLEAR 完成均不限制到可达状态。
- 实际源码方程四态穷举 16,777,216 组合（12 个独立 0/1/X/Z 谓词），另 4096 组合比较原 case／if 与新嵌套过程守卫。
- 旧／新完整 raw-store 双实例使用真实 FIFO、SDP 缓存和 native bridge；两组 FIFO／异步时钟配置比较 356,656 与 304,921 个边沿，覆盖全部 24 outputs、112 registers、176 common signals、FIFO 状态与最终 RAM、4096 个缓存 RAM 单元。原 bench 的 5 处 force 与 5 处 release 全部镜像，不屏蔽 X。
- 18 组完整模块同沿定向场景通过：START 与 native 写退役、native 读接受＋响应、CLEAR 完成、取消、异常 native／submitted／response、世代耗尽，以及 X/Z context／channel／native／response／quiescent／kind。另 4096 组任意完整寄存器四态单沿状态通过，7 个专项破坏性负控被拒绝。
- raw-store 维护回归两组 94,766／93,238 checks，完整 16,384 帧与 8,112-byte fetch，5 mutants；lint 精确保留原有 4 warning，不增加宽泛豁免。既有新世代 FIFO mutant 只更新锚点，原断言保持。
- 实际顶层／owner8／raw／DDR 地址权威组合：3 正例与 5 分配负控；共享 native DDR 队列／core／bridge：27 配置、6 故障场景与 11 mutants。
- 完整 BLE 业务：异步及 100 MHz 两组真实对象 owner 各 24 cases，正式协议 6 cases、五层链 3 cases，27 项行为／来源／输出／证据负控全部通过。其链路初始化及命令注入仍是维护仿真 fixture，不能转授为实机蓝牙验收。

执行命令及全部来源、报告和日志身份见 [机器证据](dual138k_raw_start_20261101.json)。最终完整 proof 在外部 `raw-start-factor-proof-v3`；v1 的随机生成开销超时、v2 的生成 SV 依赖声明顺序编译拒绝以及旧生产锁拒绝均保留，未列为通过。两项夹具问题只修改验证工具，未改变审定 RTL。

## 状态与下一步

本阶段完成源码实现与离线验证，没有执行新候选综合、P&R、SRAM、Flash 或实板验收，不预记任何资源／时序收益。W11 先前 setup／hold 失败仍有效。root 负责更新 W12 来源锁、候选身份及 task2，再执行完整综合／P&R 和物理门禁；通过后才进入已授权的实板验证。
