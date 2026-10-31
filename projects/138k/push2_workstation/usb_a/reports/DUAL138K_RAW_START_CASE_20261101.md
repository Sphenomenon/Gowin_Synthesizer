# Raw START quiescent case 精确分解

W12 默认实际最差 raw 路径为 DDR recording response-tag `read_pointer_1_s0/Q→write_address_3_s1/CE`，16 级、setup −4.350 ns。实际 LUT 链从 `native_bridge/n20_s4` 继续进入 `command_wait_31_s6`、完整 command／read fault 和 START 初始化；先前源码 cofactor 没有阻止本次综合重新共享这条长反馈路径。D2110107 far 的同类路径仍为 −5.845 ns。两者物理失败证据保持，本阶段只做局部源变更，不宣称已消除实际 mapped path 或取得任何时序／资源收益。

## 精确变更

实际维护 raw-store SHA256 为 `21471d722da294e841829f6ff1ec396fab016358bf6a796f93d17ec0f95c978d`，与经主线程审阅批准的 cache variant 逐字节相同。唯一生产 `RAW_STORE_SHA256` 随之更新，工具 `workstation_bluetooth_ddr.py` SHA256 为 `f4e3e9630d36cf4b573ee851ba9076210149d60e44d17b373ff178fb6fa78276`。旧 pin 对实际已变源码的拒绝记录单独保留，更新后的正式 BLE runner 再次拒绝 raw-store 漂移。

仅把 `start_initialize` 的组合守卫写成显式 `case(memory_quiescent)`：known 0 不初始化；known 1 使用相同的五项即时 fault veto 与原 command／kind／context 嵌套守卫；default 保留原完整守卫及未知态 fallback。known 0 时原 `start_context_bad` 必为 known 1，因此不接受 START；default 原样处理 X/Z，保留过程 `if` 的 else 语义。没有 casex／casez 或 translate_off。

原 `start_fault_now` 完整方程不变，其余 RTL 字节不变；没有新周期、状态寄存器、握手或缓存。所有顺序赋值位置及优先级不变：真实 native retirement 仍先执行，START 的四个宽赋值仍位于原位置，CLEAR 完成仍在其后。全局 fault、取消、隔离、ACK、response、故障码和超时不变；没有扩大到 memory_committed 的 CLEAR 路径。

## 两代完整源证明与正式回归

新增的完整 W12 fixture 就是实际被构建消费的改前源码，SHA256 `214c0a5df77d11921fecb4848e5897f7b116de039f48b69cae47b7953809da1d`；原 W11 fixture `ca212e5f93c9110ba63bb5c90399558bcb5edd8ed3d096d8d9ec5956c35363a7` 保持。两个证明均编译实际维护源，使用真实 FIFO、SDP cache、native bridge，并在执行期间检查来源稳定。

- W11→当前：完整源逆变换证明只在已批准 START factor／case 位置变化；原 bridge／fault／context 方程逐项绑定。完整二态 fault／START guard 及四个宽字段 next-state 均为 UNSAT。context 中 `!memory_quiescent` 与其余独立谓词的源关系显式纳入，不增加可达状态假设。
- W11 实际源 fault 方程四态穷举 16,777,216 组合，另 4096 组原 case／if 守卫组合通过。
- W12→当前：精确全文逆变换、二态 guard UNSAT；抽取原／新过程守卫，按实际 `context_bad = residual_bad || !memory_quiescent` 关系穷举 65,536 组四态组合。其余 context 谓词、full／fast faults、command、channel 和 2-bit kind 均独立，不用可达状态过滤。
- 每个基线的两套完整 raw twin 分别比较 356,656 与 304,921 个时钟／复位边沿。W11 比较 24 outputs、112 registers、176 common signals；W12 比较 24 outputs、114 reg 定义（含 2 个组合 reg）、179 common signals。全部 FIFO 状态／最终 RAM、4096 cache RAM 单元、cache 输出及 native bridge 状态参与比较，不屏蔽 X。
- 两个基线分别通过 18 组同沿定向场景及 4096 组任意完整寄存器四态单沿状态，覆盖 native 写退役、同沿读接受＋响应、CLEAR 优先级、取消、异常 native／submitted／response、世代耗尽和 X/Z。
- W11 7 个专项破坏负控全部拒绝；W12 另 3 个 case 专项负控（删 unknown fallback、删即时 native veto、occupied 时强制 START）全部拒绝。
- 原 raw 回归 94,766／93,238 checks、完整 16,384 帧、8112-byte fetch、5 mutants 通过；lint 精确保持原 4 项 warning，无宽泛豁免。
- 正式 BLE DDR runner 全通过：真实对象 owner 异步／100 MHz 各 24 cases、协议 6 cases、五层链 3 cases、27 个行为／来源／输出／证据负控，包含更新 pin 后的 raw_store_tamper 拒绝。初始化及命令注入仍为维护仿真 fixture，不能转授为实机 BLE 验收。

W11 完整维护证明第一次重跑在所有正例／任意状态之后，被旧负控文本锚点重复拒绝；原失败输出保留。只把三个 cofactor 负控锚点收紧到实际 fast 分支，断言和故障条件保持，再完整重跑成功为 v2。W12 证明先前已执行完成且保存 helper 快照；随后 W11 main 中的负控锚点调整没有改变 W12 实际调用的全部 helper 函数，逐项 AST identity 单独封存。

## 封存与下一候选

[机器证据](dual138k_raw_start_case_20261101.json)记录全部维护源、两个 fixture、proof runner、命令、输出及失败身份。source seal SHA256 为 `be4c91954f39e533f1aedc056bf0233dad08a670a39b1988c468c70b0b4a276d`。本阶段未更新 profile 锁、task2、commit 或候选身份；由主线程分别完成版本化和 push，保留其他 agent 的 PCM 修改。

本阶段完成源码与离线验证，没有新综合、P&R、SRAM、Flash 或实板声画验收。W13 须以新来源锁／身份重新综合，并检查真实 START CE 是否避开旧完整 fault cone、实际资源／STA／CDC／PLL 与正式功能门禁；不能把这份源证明当作时序改善或双板验收。
