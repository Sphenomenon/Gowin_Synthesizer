# 已解析业务命令邮箱 S1a

这是未选择的内部组件和 C API，没有生产实例、物理 APB 页、固件入口或 BLE hook。`ble_protocol_command` 的 CRC／nonce／session／精确 replay／线规字节、18-bit 音乐事件、外部能力和现有录音 owner 均不变。输入须来自既有 `DISPATCH` 验证后的命令，邮箱不再次解析协议、不分配任务或对象 ID、不搬运 PCM。

## 容量、时钟和身份

所有端口属于一个持续运行的控制时钟域；未来集成若跨域，必须另加已验证的保持字／APB CDC。一个不可变请求槽最多保存 16 个 payload 字节，一个完成槽最多保存 64 个字节。`request_offer_i` 是单周期尝试，`request_admitted_o` 只表示邮箱存入请求，绝不是业务 ACCEPTED。满槽、未 OPEN、无效上下文、超长或非零 reserved 返回拒绝脉冲，不截断执行、不分配 ID、不改变协议 high-water。payload 未使用的字节填零。

每条请求键为 `{外部 boot_id64, owner_generation32, session_generation32, ticket32}`。boot_id 必须由外部权威提供，`boot_valid_i` 只可在该管理者保证此业务启动身份未被复用时置位；不能证明时保持为零，邮箱持续隔离。组件不制造 boot ID。common reset 后没有恢复任务元数据的能力，必须保持 boot_valid 为零，直到外部管理者完成新身份／恢复检查；不能以重复的 boot ID 重新开放。

ticket 从 1 单调增加，CPU observer reset、断连、超时和槽释放均不归零。最后的非零 ticket 可使用一次，此后拒绝新请求。owner generation 在 observer reset 下降沿或 boot 身份变化时递增；32-bit 耗尽永久隔离，直到外部新 boot 的 common reset。零和回绕不作为可复用身份。CPU 用完整上下文键和 ticket=0 执行 OPEN；OPEN 不创建对象或后台任务。

## claim、任务与观察的分界

槽状态为 EMPTY → QUEUED → CLAIMED → RESULT → EMPTY。CLAIM 只取得请求。唯一业务 owner 在真实保留 operation_id 后才可以发布 `PENDING=1`，且 operation_id 必须非零；`APPLIED=2` 仅在真实存储／控制事实核验后发布；`FAILED=3` 为 owner 明确失败。status 字节和 payload 为既有业务层的透明数据，邮箱不编码或创造新的 wire 状态。每条请求只发布一次完成；PENDING 后的任务进度由新的查询请求读取同一个业务 owner 的表，不再用旧 ticket 重发完成。

CPU reset、session/control 失效、显式 fence、ABANDON／cancel、CLOSE 和期限到达都**不取消后台任务**，没有 backend cancel 输出。QUEUED 尚未 claim 时产生本地 `LOCAL_REJECTED=4`，可以确认没有通过邮箱分发执行；CLAIMED 或已发布但尚未消费时产生本地 `UNCERTAIN=5`，只表示旧观察失效。若旧完成已含 operation_id，该 ID 保留供任务查询；尚未公开 ID 的已 claim 请求同样可能已执行，不能当作撤销成功。

observer reset 后 OPEN 还要求真正的业务 owner 已恢复／核对后台任务和 ID 分配记录；无法恢复时必须保持隔离，按后续统一 owner 契约完成实际 drain、声明新的业务 boot 身份，不能在原 boot 下清零 C 计数器再开放。邮箱不保存任务表，OPEN 只是调用者确认此条件后的动作；S1a 不提供或证明这一恢复策略，不能单独接入生产。

本地 reason 为 cancel=1、owner reset=2、session=3、timeout=4、close=5、boot=6；这些不是 BLE 错误码。适配器须区分 reason!=0 的本地终结与真实业务响应，在失效旧会话中只排空旧观察，不能把它编成“任务已取消”。重新连接后按既有协议查询／恢复实际任务。timeout 从进入 QUEUED 起计算，默认 5,000,000 控制周期；不得阻塞音频。RESULT 保持到 consumer 消费，满槽不会分配第二条请求，也不自动覆盖未消费完成。

优先级为 common reset；boot／owner reset；session／cancel／timeout fence；完成消费；CPU 写操作。fence 胜过同拍 CLAIM／COMPLETE，写返回错误。关闭与新 offer 同拍时不 admission。CPU reset 低期间允许 consumer 排空已有本地终结。总线访问只等待本地固定 RAM 流水，不等待 CPU、无线、DDR 或后台任务。错误写无状态动作；合法写只在其单一接受边沿公开生效。

staging 和完成 payload 各使用一个 16×32 SDP RAM。合法 COMPLETE 先将 16 字 staging 复制到独立完成 RAM，并按 length 填零尾部；从首个合法、保持的 COMPLETE 采样沿到最终接受沿为 18 个控制周期，期间 command ready 为零，元数据和 RESULT 状态尚未发布。调用方须保持 command valid／地址／数据直到 ready。复制期间若 fence／reset／timeout 到达，停止私有复制，原 COMPLETE 返回错误，只保留既有本地终结语义；部分复制的物理 RAM 不得作为有效 payload 公开。common reset 中止在途访问，集成 CDC 同样复位。

0x09c..0x0d8 的 32-bit 读在本地 SDP 地址采样后返回 ready，其他合法访问仍立即 ready。内部 consumer 通过 byte 地址／ready／下一周期 data valid 读取同一完成 RAM；新 MMIO 读优先，byte 请求可在 MMIO 应答周期进入，复制期间暂停两者。完成消费后 payload 和元数据保留至下一次完成、本地终结或 common reset；EMPTY 中的 owner reset 仍只清 staging。parser 在构建一条回复期间不提供下一条请求，因此可消费槽后从保留完成 RAM 逐字节构建原有 wire 回复，无需第二份 512-bit 快照。

## 相对寄存器 ABI

所有地址以字节计，字对齐；写要求全部四个 strobe。未知地址、只读寄存器写入、非法命令／字段／键／状态均返回错误。ID=`0x424d4201`，CAPS=`0x00401001`（64 字节完成、16 字节请求、一个槽），没有外部 capability 声明。

| 偏移 | 语义 |
|---|---|
| 0x000 / 0x004 | ID / CAPS，只读 |
| 0x008 | STATE：低两位槽状态；bit8 OPEN、9 ticket 耗尽、10 owner 耗尽、11 boot valid |
| 0x00c..0x018 | 当前 owner generation、boot low/high、session generation |
| 0x01c..0x02c | 不可变槽键：ticket、owner、session、boot low/high |
| 0x030..0x03c | request_id、nonce low/high、`{reserved8=0, opcode8, length16}` |
| 0x040..0x04c | 16 字节请求，小端字读 |
| 0x050..0x068 | age、admitted、rejected offers、timeouts、rejected claim/complete/abandon writes、abandoned observations、last local reason；计数饱和 |
| 0x080..0x090 | CPU staging key：ticket、owner、session、boot low/high |
| 0x094 / 0x098 | 写：staging `{reserved8=0,length8,status8,phase8}` / operation_id；读：不可变完成 `{reason8,length8,status8,phase8}` / operation_id |
| 0x09c..0x0d8 | 写 staging 完成 16 字；读不可变完成 16 字，未用尾部填零 |
| 0x0dc | COMMAND：OPEN=1、CLAIM=2、COMPLETE=3、ABANDON=4、CLOSE=5，只写 |
| 0x0e0..0x0f8 | 最近发布键五字、完成 meta、operation_id；消费后保留，仅是观察事实 |

CLAIM／COMPLETE／ABANDON 必须匹配完整槽键，COMPLETE 仅限 CLAIMED。OPEN／CLOSE 要求 ticket=0 的当前完整上下文。写 staging 不授权业务执行。硬件保持未重写的 staging 字，短完成的尾部填零不修改 staging；common／owner reset 或 boot 变化使未写 staging 字读作零。C 调用者仍须完整重新填写描述符，不能把上一次失败调用的部分写入当成新描述符。

## C 调用与验证边界

`business_mailbox.h/.c` 使用调用者提供的窗口基址和 read/write 回调，MMIO 适配器保留 uncached mapping／fence 前提。回调非零只表示访问成功，零表示失败，写入仍可能已经生效。API 无重试、等待或动态分配。输出结构只在成功时改写；NONE、IO、STALE 不改输出。请求读在不可变字段前后复核完整 boot／owner／session／ticket 键、状态与当前 owner；观察读在当前槽及历史槽都复核完整键／meta，不以历史 PENDING 推导任务已完成。

一次调用不得在 common reset／总线身份中断后继续作为同一调用；集成必须中止该调用或使回调报告失败。完整键双读可检测所覆盖的身份变化，不把分离的 32-bit 访问升级成跨任意多次 reset 的全局原子快照。直接 volatile MMIO 适配器在访问正常返回时报告成功，不能自行恢复或报告 slave error／reset 中断；生产桥接必须另证 ACK／错误传播及 CPU fault 策略。

最终 COMMAND 回调失败可能已生效，返回 COMMIT_UNCERTAIN；只能观察同一键并查询真正 owner，不可自动重放。claim 前的 staging 回调失败返回 IO，未发出 COMMAND；下一次由调用者显式完整 staging。一次 complete 最多 24 次写访问，context 最多 8 次读，request 最多 21 次读，observe 最多 28 次读。逐函数实际 RV32 代码／stack 代价需单列证据；本组件未链接生产 UI，不能宣称现有 16 KiB ROM 预算或整机服务间隔已通过。

S1b 才接入默认关闭的 parser hook 和有界业务 pump；S2 才统一 CPU 录音／下载 owner、提交 CRC／元数据与数据任务后原子退役旧 BLE 录音 RAM。S1a 的任何通过都不代表 B01、长录音、完整 CDC、时序或硬件验收。
