# 音频时钟命令服务（内部 opt-in v1）

`workstation_audio_clock_service.sv` 属于常开 50 MHz 控制域，适配现有
`gw138k_apb_cdc` 已锁存、经过一拍本地预解码的命令。它没有接入任何旧
services、顶层、profile 或固件。本页只定义内部 page-local offset；**没有
分配 CPU 绝对地址**，未来组合根须显式选择独立页，不能覆盖旧服务
`0x000..0x1b4`。18-bit 事件、CC、USB、PL 和 BLE 线规不变。

## 请求、接受与结果

唯一可写寄存器 `COMMAND` 接受完整 32-bit 写入：0 请求 48 kHz，1 请求
44.1 kHz，2 恢复最近由硬件提交的采样率。不能写任意频率、epoch 或清除
DSP fault。每次本地合法提交分配非零 `command_id`，输出一拍寄存的
`request_o` 或 `recover_o`，最多一个在途，无排队。ID 由 `0xffffffff`
回绕至 1；它只在当前命令观察实例内有效，不是跨 CPU 复位的事务身份。

APB 响应只表示本地准入。错误地址、只读写、非全字节 strobe、非法值、
已有命令、观察端未重新就绪、关联失效、无许可、硬件忙、DSP fault、
未就绪或目标时钟不合格均立即 `PSLVERR`。APB 不等时钟切换完成，也不因
音频故障保持总线 pending。`command_valid` 保持高直到握手后，即使继续
保持高，也只执行一次；下一条命令需先观察到低电平。

状态为 `IDLE → ISSUE → WAIT_ACCEPT → WAIT_APPLY → IDLE`。`ISSUE` 对应
已寄存请求被核心采样的边沿，忽略此前产生的状态脉冲。普通请求只有
`core_accepted_i` 后才归属应用结果；同率请求允许核心同拍 accepted 和
applied。接受前的孤立 applied、无 owner 的启动／迟到事件只计入
`UNOWNED_EVENT_COUNT`。核心在请求寄存以后产生的 rejected、policy_rejected、
failed 或 DSP fault 被记录为终态，不能把 APB 成功当作 applied。

现有真实 `workstation_sample_rate_switch` 的 FAULT 恢复分支不输出
accepted。恢复的接受证据明确为：合法恢复提交以后，核心由 fault 状态
进入 `busy && !fault` 的事务；服务据此更新 `HW_ACCEPTED_COUNT` 与
`ACCEPTED_ID`，不生成或冒称核心 accepted 脉冲。回归实际实例化该核心，
核对恢复没有 core accepted 仍完成应用。`switch_permit_i` 在本地准入时
检查；已经发出的命令没有由许可撤销自动取消的语义，后续以真实核心
policy/reject/failure 结果为准。

应用还必须同时满足 runtime 的实际 valid、非 fault、目标 rate 与预期
epoch。普通同率请求预期 epoch 不变，换率与恢复预期为提交时 epoch+1
（32-bit 自然回绕）。这些字段是请求观察上下文，不作为 DSP 参数真值。
调用者必须把该服务作为这一切换核心的唯一命令 owner；不能并行接另一
个 CPU/面板请求源而不做统一仲裁。

接受与应用有独立常开域超时：默认 32 clocks（640 ns）与 20,000,000
clocks（400 ms），均可参数化且至少 4 clocks。后者是命令观察上限，不
替代核心每状态超时或整机时限证明。超时／上下文不匹配即结束命令 pending，
记录失败并置 `correlation_fault`；后续提交立即拒绝，直到观察端复位。
该限制避免迟到的无标签核心响应被分配给新 ID。已经由硬件接受的事务仍
继续，实际状态仍可读；本服务不复位、取消或伪装硬件完成。

## 复位与实际状态发现

`reset_ni` 仅使用 APB CDC 的 `command_reset_n`，**不连接 DSP、stream、
PLL、时钟核心或板级复位输出**。CPU/preset 复位会清本地请求寄存器、
pending owner、结果、计数与观察快照，不会撤销已经被硬件接受的事务。
复位发生在请求尚未被硬件采样以前时，本地脉冲可能被撤回，该请求没有
跨 CPU 复位的完成承诺。

复位后必须读实际状态重新发现：先读 `ACTUAL_STATUS`，再读
`SNAPSHOT_EPOCH`。前者在同一服务握手边沿把 runtime epoch 锁存；后者
与已返回的 status 构成一个一致的只读观察快照。它不是另一套可写采样率。
实际 rate／valid／epoch 与 fault 始终由 runtime 输入拥有。多次读取
`ACTUAL_STATUS` 会覆盖旧快照，CPU 应按顺序读这一对。

重新准入前需连续默认 4 个 50-MHz edges 看到核心非 busy 且无任何结果
脉冲；CPU 复位中的旧硬件事务先继续完成，结果仅计为 unowned，随后才能
提交新命令。外部 sticky DSP fault 继续显示，并拒绝包括 recover 在内的
所有命令；CPU 复位绝不清除它。没有硬件 owner 的永久 pending：故障、
丢 ACK、丢应用结果均有终态；失去关联时的重新附着需要观察端复位。

`command_reset_n` 两侧仍遵循既有 APB CDC 共同断言、各域本地释放契约。
未来物理装配必须复用并核对 held-payload、同步器和 reset 约束，不能添加
整域 false path 来代替验证。源总线停钟不影响 50 MHz 命令观察或音频。

## 页内寄存器

所有地址 4-byte 对齐。除 `0x008` 仅写，其余仅读；非法访问返回错误，
错误访问的数据值应丢弃。计数为 32-bit 饱和，CPU/preset 复位清零；
一次周期有多个无 owner 脉冲时按该周期计一次，并非每种脉冲各加一次。

| offset | 字段 | 含义 |
|---|---|---|
| 0x000 | ID | `0x434c4b01` |
| 0x004 | CAPS | 高 16-bit 版本 1；低三位为 48k／44.1k／recover 操作支持 |
| 0x008 | COMMAND | 写 0／1／2；成功响应数据为分配的 command ID |
| 0x00c | STATUS | [1:0] phase：0 idle、1 issue、2 wait accept、3 wait apply；bit3 armed、bit4 correlation fault、bit5 snapshot valid |
| 0x010 | COMMAND_ID | 最近本地准入 ID，复位 0 |
| 0x014 | OPERATION | 最近本地准入 0／1／2；ID=0 时无命令 |
| 0x018 | RESULT_ID | 最近终态 ID，和 pending ID 分开保存 |
| 0x01c | RESULT | 下表终态码；复位 0 |
| 0x020 | RESULT_DETAIL | 核心终态当拍：[2:0] reject code、[6:3] fault code、bit7 accepted、8 applied、9 rejected、10 policy rejected、11 failed、12 fault、13 DSP fault |
| 0x024 | BASE_EPOCH | 命令准入时实际 epoch，仅为观察上下文 |
| 0x028 | EXPECTED_EPOCH | 命令预期 epoch，仅用于验证应用结果 |
| 0x02c | ACTUAL_STATUS | runtime 当拍 bit0 rate（1=44.1k）、1 valid、2 busy、3 request ready、4 fault、5 DSP fault、6 permit、[8:7] 两路 source qualified；读时原子捕获 epoch |
| 0x030 | SNAPSHOT_EPOCH | 与最近一次 0x02c 返回值同拍的 runtime epoch |
| 0x034 | SUBMITTED_COUNT | 本地合法准入次数 |
| 0x038 | HW_ACCEPTED_COUNT | 核心 accepted，或上述真实 recover busy 接受证据次数 |
| 0x03c | APPLIED_COUNT | 经过实际上下文核对的成功次数 |
| 0x040 | FAILED_COUNT | 非成功终态总数（含拒绝、超时、上下文不匹配） |
| 0x044 | BUS_REJECT_COUNT | 被本地拒绝的读／写次数 |
| 0x048 | UNOWNED_EVENT_COUNT | 启动、复位遗留、接受前孤立 applied 等无 owner 事件周期数 |
| 0x04c | LAST_BUS_REJECT | 最近本地拒绝原因，下表 |
| 0x050 | ACCEPT_TIMEOUT | 参数对应的 50-MHz clocks |
| 0x054 | RESULT_TIMEOUT | 参数对应的 50-MHz clocks |
| 0x058 | EXPECTED_CONTEXT | bit0 预期 rate、bit1 最近命令是否 recover |
| 0x05c | ACCEPTED_ID | 最近有硬件接受证据的命令 ID |

| RESULT | 含义 |
|---|---|
| 0 | 无结果 |
| 1 | applied，且实际 rate／epoch／valid 验证通过 |
| 2 | core rejected |
| 3 | runtime policy rejected |
| 4 | core failed、fault 或 sticky DSP fault |
| 5 | acceptance timeout，关联锁定 |
| 6 | application timeout，关联锁定 |
| 7 | applied 上下文不匹配，关联锁定 |

| LAST_BUS_REJECT | 含义 |
|---|---|
| 0 | 无 |
| 1 | 地址／对齐／读 COMMAND 非法 |
| 2 | 写只读寄存器 |
| 3 | 写 strobe 非 `0xf` |
| 4 | 命令值非法 |
| 5 | 本地命令仍 pending |
| 6 | 观察端尚未重新就绪 |
| 7 | 结果关联已锁定，需要观察端复位 |
| 8 | 没有切换许可 |
| 9 | 核心 busy |
| 10 | sticky DSP fault |
| 11 | 核心未 ready／actual invalid／非 recover 时 fault |
| 12 | 当前不在可 recover 的 fault 状态 |
| 13 | 目标（recover 为最近实际 rate）时钟未 qualified |

## 验证与集成门禁

`sim/services/run_audio_clock_service.py` 从既有锁定 baseline 经现有
`timing.apb` 重建真实预解码 CDC，实际实例化该 CDC、此 native service 与
未改的 `workstation_sample_rate_switch`。三组异步相位覆盖合法请求、
held-valid、busy、迟到拒绝／失败、同率同拍 ACK、真实 fault 恢复、丢 ACK／
丢应用结果、epoch 错配、启动旧 applied、CPU 复位时硬件继续、sticky DSP
fault 与源总线停钟。许可与丢响应注入单列，不把它们当物理时钟验证。

本阶段没有运行 DCS、PLL、真实参考时钟监视、整机 DSP／I2S、综合、P&R、
固件或板测。未来显式 profile 还须绑定唯一 owner、50-MHz inputs、独立
APB 页与绝对地址、时钟切换业务许可、超时预算和真实 CPU 程序，再完成
整机 CDC／时序／音频与硬件验收；C01／A06 整项未因此完成。

## Optional reserved-zero epoch policy

`RESERVE_ZERO_EPOCH` defaults to zero and must match the attached stream owner's
configuration. With value one, feature register bit 3 is set and the command
observer expects `0xffffffff -> 1` for a real switch or recovery. Same-rate
requests preserve the actual epoch. The observer still reads the epoch from
the core; this option never assigns or remaps authoritative stream identity.
The native owner propagates this option through clock domain/runtime/controlled
composition. See [STREAM_EPOCH.md](../audio/STREAM_EPOCH.md). A new explicit
profile must select it for display metadata v1.1; existing profiles retain
their previous selection.
