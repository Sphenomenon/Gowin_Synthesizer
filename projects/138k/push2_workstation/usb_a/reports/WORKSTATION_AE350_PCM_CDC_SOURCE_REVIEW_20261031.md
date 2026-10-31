# AE350 PCM / HCI CDC 源码、prepare 与行为门禁

日期：2026-10-31。范围：显式 `custom138k-workstation-classic-runtime-v1`，基于 `e0688427d517632cc61eae16300efa15500eb0e0` 的独立审查。本文不改变 accepted、默认 profile、RTL、时钟或约束预算。

本阶段已固定 15 份维护源码和实际 prepare 产生的 F806 `gw138k_apb_cdc.sv`，检查选择的 HDL/include/macro/端口闭包，并加入真实 HCI→音频会话及 F806 APB 异步行为回归。实际整机 VG、约束对象解析、布线传播、recovery/removal 和硬件验收仍未完成；所有物理及发布标志保持 false。

## 已验证的边界

- `tools/workstation_ae350_pcm_cdc.py` 的源码/prepare 模式锁定源清单与 APB SHA，不从历史私有输出回退；策略字节、维护源码漂移均被拒绝。`--synthesis-evidence` 模式必须接受严格完整 process/source/VG 身份，但当前实际 VG 门禁只实现 APB 范围，HCI、hold 与 RAM 项明确为未验。
- SDC 扫描要求原候选 bundle 逐行仅出现一次，拒绝未审查 Tcl、整域/multicycle 例外、宽通配 false path 和 max/min delay 覆盖。source name witnesses 只用于提前筛选通配，绝不被记录为实际工具对象；现有 serial hold 的 CLEAR wildcard 是否对应真实 PRESET 要待 VG 逐对象解析。
- APB auditor 检查 181 个标量 FF、49-bit 请求与 33-bit 响应的全部位映射、共享 capture enable、完整 fanout、唯一 driver、三级同步/settling 顺序、两个本地复位释放和请求/响应 Boolean 契约。其当前正测网表为明确标记的**手写 synthetic fixture**，不构成 Gowin 实际综合证明；额外、异域、未知原语消费者等 10 项结构负控均拒绝。
- `run_ae350_hci_session_cdc.py` 使用哈希锁定的原 native HCI 集成 TB、七个实际 HCI owner 模块和真实 `workstation_ae350_pcm_session`。只在外部证据目录给既有 TB 增加观察者，源时钟设 50 MHz，对 76.8 MHz compute 时钟检查三个相位；每相位保留 269 个原集成检查，发生 3 次会话抓取和 3 次撤销。覆盖实际断连/同 handle 新 generation、CPU overflow fence、observer reset、common reset 新 epoch 和精确 CPU fence。检查 ready 连续高期间 tuple 不变、低 ready 至少完整源周期、三边沿 settling、bundle 一致、ready 下降异步撤销；删除 close 预撤销、绕过 settling、丢 generation、移除异步 revoke 四负控均在对应断言失败。
- `run_ae350_pcm_apb_reset.py` 直接编译已锁定的实际 prepared F806 桥。54 项检查、6 次准确接受，覆盖服务背压、compute 停钟前取消、实际接受后 ACK settle 前复位、producer 停钟时取消，以及复位后拒绝旧命令/旧响应。破坏请求保持、响应载荷、ACK 退休和 compute 异步复位四负控均失败在预期断言。
- 既有 `sim/test_ae350_pcm_boundaries.py` 两项回归通过：held epoch/generation、短 ready pulse 与 reset；两率 I2S 原帧完成、cached/late response 丢弃、零帧 schedule 和 guard 后恢复。它不是 runtime 实际两级 hold FF 的物理证明。

## 可复现命令

以下命令从 `usb_a/` 执行。`$CDC_STAGE` 指向明确选择的、未修改的 joint128 prepare `workstation/Prj1`；输出目录应新建并置于源码树之外。

```sh
python3 sim/test_workstation_ae350_pcm_cdc.py
python3 -m tools.workstation_ae350_pcm_cdc --stage "$CDC_STAGE" --output "$CDC_OUT/prepare.json"
python3 sim/run_ae350_hci_session_cdc.py --output "$CDC_OUT/hci"
python3 sim/run_ae350_pcm_apb_reset.py --stage "$CDC_STAGE" --output "$CDC_OUT/apb"
python3 sim/test_ae350_pcm_boundaries.py
```

审查记录：[ae350_pcm_cdc_source_review.json](workstation_task_20261030/ae350_pcm_cdc_source_review.json)。实际行为证据包含输入/输出 SHA 与负控失败点。本阶段没有启动综合、P&R、JTAG 或操作硬件。

## 后续验收与回退

实际 joint128 整机综合网表到达后，必须对真实 APB inventory/Boolean gates、HCI epoch/generation mux 源与全部消费者、selected-MCLK hold、PCM RAM clocks/ports、SDC D/CE/async pins 作严格审计。缺失对象或错误 PRESET/CLEAR 不能以“源上有约束”解释为通过；未知或多驱动拓扑失败。之后单独绑定 routed STA/传播、recovery/removal 和硬件证据。不得放宽既定 10 ns payload / 2 ns synchronizer 预算或添加整域 false path 以取得通过。

该提交只新增 checker、仿真及报告；撤销这些新增文件即可回退，功能与候选输入不改变。ROM96、其它存储配置或新的 RTL 身份需另立显式策略，不能静默沿用 joint128 的哈希或物理结论。
