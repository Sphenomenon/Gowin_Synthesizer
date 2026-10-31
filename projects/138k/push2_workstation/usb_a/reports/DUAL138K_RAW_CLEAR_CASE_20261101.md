# Raw CLEAR completion quiescent case 精确分解

W13 默认实际 raw 路径经过 tag response／完整 fault cone 进入 CLEAR completion；far 的最差 raw 路径则终止于 `fetch_address` CE。本阶段只把已独立审阅的 CLEAR completion 组合分解落到维护源码，保留两份物理失败证据。没有扩大修改到 fetch 分支，也没有预记时序或资源收益。

## 实际维护变更

实际 `rtl/memory/workstation_ble_raw_ddr_store.sv` SHA256 为 `39ae3b918a4674f849eb0663bb193e2890881f164063f22b473b5dbb61df290b`，与独立审阅批准的 cache variant 逐字节相同。改前实际 W13 源另存为 `sim/memory/fixtures/workstation_ble_raw_ddr_store_before_clear_case.sv`，SHA256 `21471d722da294e841829f6ff1ec396fab016358bf6a796f93d17ec0f95c978d`；原 W11、W12 fixture 保持原身份。

仅新增组合 `clear_initialize`，并替换原 sequential CLEAR completion 的 `if` 条件。known quiescent 0 不完成；known 1 使用原 pending／target／FIFO／channel 条件与五项即时 fault veto；X/Z default 逐字保留原完整守卫。known quiescent 1 强制 published、read outstanding、return pending、pack pending 均为 known 0，此时实际完整 fault 方程恰好缩成 transport、sticky protocol、submitted、native accept、read response 五项。正向过程守卫仍拒绝未知 fault，未改成会改变 X 行为的过程 else。

所有 NBA target、RHS、顺序、优先级与其余源码字节均由精确逆变换校对。CLEAR 的 clocked 赋值仍在原位置，没有新增周期、握手、clocked state 或 RAM。全局 fault、正常 FIFO ready、START、native retirement、取消、隔离、超时、失败码和 fetch 业务保持原字节。为保留批准身份，RTL 中原 cache proposal 注释也保持；本报告记录其现已落到维护源码。唯一生产 `RAW_STORE_SHA256` 同步更新，工具 SHA256 为 `e34fd879977e487ba83942c8212ec2ecd0109f82640aa8c87fe3d1fedd26c3fb`。

## 独立 CLEAR 证明与保留的 START 证明链

新增可重复执行的 `sim/memory/prove_ble_raw_clear_quiescent_case.py` 编译实际维护 SHA39ae，使用完整改前 W13 fixture、真实 FIFO／SDP cache／native bridge。它校对精确全文逆变换、原 fault 方程身份与全部顺序赋值；binary guard 全域证明 UNSAT，无可达状态筛选。

- 精确原／新过程 CLEAR guards 的 16,384 组四态组合通过；实际 source fault equations 的 16,777,216 组四态组合通过。
- 两套完整 twin 分别比较 356,656 与 304,921 个时钟／复位边沿，合计 661,577；比较 24 outputs、114 原 reg 定义（含 2 个组合 reg）、179 common signals、FIFO 状态、完整 4096-cell cache RAM、cache 输出与 native bridge 状态，不屏蔽 X。
- 36 组定向场景及 4096 组任意完整寄存器四态单沿状态通过。新增场景覆盖 CLEAR 的 transport／sticky／submitted／native accept／response／channel fault、未知 fault、占用的 command／read／return／pack、未知 quiescent、target mismatch 以及 command／read timeout；新 runner 的最终计数已正确写为 36。
- 4 个破坏性对照全部按具体 twin mismatch 拒绝：删 native fault、删 transport fault、允许 nonquiescent CLEAR、把未知 fault 正向守卫错误改成过程 else。
- 精确 CLEAR inverse 另拒绝 body 与 guard 两种字节漂移；维护源及改前 fixture 都锁定完整 SHA，不能接受任意其他修改。

旧 W11／W12 START runners 现在先通过新 runner 的严格逆变换，仅撤销本次已批准 CLEAR 插入，得到字节完全等于新 W13 fixture 的 SHA21471 normalized 输入，再执行各自全部原门禁。它们编译这份 normalized 输入；新 CLEAR runner 独立编译真实 SHA39ae，合成完整证明链。W11 proof 的全部 16 个非 main helper 函数保持字节完全一致。

- W11→normalized W13：原全文 START inverse、source equations、binary fault／guard 与四个宽字段 next-state UNSAT，16,777,216 组实际 fault 四态及原 4096 组 guard 四态全部通过；两套完整 twin、18 directed＋4096 arbitrary four-state 和全部 7 个原负控均通过。
- W12→normalized W13：原精确 inverse、binary guard UNSAT、65,536 组四态 guards、两套完整 twin、18 directed＋4096 arbitrary four-state 与全部 3 个原 case 负控均通过。
- 三份 runner 记录真实维护 SHA39ae 与 normalized SHA21471。最终封存再次校对所有声明的实际输入；两份 normalized 文件在运行后仍精确等于 immutable W13 fixture。

## 正式回归与来源门禁

原 raw 回归通过 FIFO8／异步 memory 的 94,766 checks 及 FIFO3／100 MHz memory 的 93,238 checks，完整 16,384 frames、8112-byte fetch、5 mutants 均通过；lint 保持精确原 4 项已审阅 warning，无宽泛豁免。

正式 BLE DDR runner 全通过：原 live recorder、真实 raw object owner 异步／100 MHz 各 24 cases、真实协议 6 cases、五层链 3 cases，以及全部 27 个行为／来源／输出／证据负控。更新 pin 后仍拒绝 `raw_store_tamper`；default-off 不改字节，完整 prepare／verify、失败 prepare 不发布字节的门禁全部保留。单独把旧 pin 仅在缓存验证进程内恢复为 SHA21471，实际 SHA39ae 源立即报 `BLE raw DDR store identity changed`，空 stage 保持空。维护文件未为负控修改。

录音 DDR authority 的 10 个异步 phase、每 phase 17 scenarios／666 checks 与 6 mutants 通过；`test_current_workstation_sources.py` 的 17 tests 通过。BLE 初始化／命令注入及 native DDR 仍为正式维护仿真模型，不转授为实机协议、RAM、声画或下载验收。

最初系统 `python3` 缺少 z3，在创建 proof 输出目录之前退出；其观察记录保留。随后三套 source proof 全部使用已存在的 `/Users/sphenicidition/miniforge3/bin/python3`，没有安装或改动依赖，没有覆盖失败实现输出。

## 封存与下一候选

[机器证据](dual138k_raw_clear_case_20261101.json)记录完整命令、输入、输出、所有验证结果、独立批准及导入失败记录。缓存 source seal 位于 `w14-maintained-clear-final-seal-v2/source-seal.json`，SHA256 `ed447ca80e49ef64eae3ee958857bd2e04c13a997b53d3ba1d01ae9ebe6e5694`；54 个源码及实际消耗输入、280 份原始证据文件均再次按字节校验。所有 54 个输入另按内容 hash 保存为 48 个独立 blob，原路径索引在 `w14-maintained-clear-input-snapshot-v1/snapshot.json`，SHA256 `f028bf41a1fb676a67bbee12aea917312a6bdeaf96c56689cf99274953784973`；完整最终 seal 共封存 331 份证据，包含该索引与全部 blob。以后 live 源变化仍能恢复本阶段实际输入字节，最终 seal 与报告自身没有递归 self-hash。上游独立 review SHA256 `2aa74923b4b33c46b8d55de71f6e1a507921b42bd5b9322f1b9738d1e2666779` 及其 seal `cfc013561d7fbdb646adbf394802dcdc21e4a2b177b202516948f5a20ec6900c` 保持匹配。

本阶段只完成源码实现与离线验证，worker 未修改 profile locks、task2 或进行 commit／push；由主线程统一更新来源锁及候选身份。本阶段没有新综合、P&R、SRAM、Flash 或实板操作。下一候选必须重新制备与综合，检查实际 CLEAR predicate 和 `memory_next_index`／`memory_committed` 的 D／CE 映射；`fetch_address` 由 CMD_FETCH admission 和 fetch publication increment 写入，CLEAR completion 并不写它，far 最差 fetch CE 仍需独立核对。不能将本证明当作整机时序收敛、资源收益或双板并发验收。
