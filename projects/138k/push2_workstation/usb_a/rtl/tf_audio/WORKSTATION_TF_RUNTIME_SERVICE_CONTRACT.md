# TF 原生服务（显式 profile 选择）

`workstation_tf_runtime_service.sv` 包装真实 `tf_audio_ddr_path`、现有 reader／
DDR DMA／byte FIFO／WAV decoder，以及已提交的 85-bit 原子帧桥。
`custom138k-workstation-v1` revision 4 通过原生组合显式选入本服务；accepted、
pinned 和未指定 profile 的入口维持各自来源。源码组合与离线回归不是整机物理
验收。playlist、识别 owner 和 DDR 地址分配保持；没有第二路时钟请求，没有
重采样，也不宣告播放数据已经取消 DDR 中转。

## 接线与时钟域

| 接口 | 所属域和含义 |
|---|---|
| mode/run/restart/cancel/track、analysis 控制、runtime valid/rate/fault/busy/epoch | 常开 50 MHz；runtime epoch 作为不透明真值比较，允许 0，不推算增量 |
| SD、playlist/name、format/file/rate/card 状态、analysis PCM、failure/paused/busy50 | 50 MHz |
| DDR valid/write/address/data/ready/response | memory；地址继续为原生 32-bit word，沿用 TF 原 DDR 分配 |
| tf_active/busy/valid/error/PCM/rate/generation、expected_generation、media_quiescent | 连续 compute；直接接 runtime TF 输入 |

`rst_ni` 是两端共同断言的全局服务复位；组合根须同时遵守旧 DDR 通道的全局
复位／在途响应清理契约。`memory_reset_ni` 保留原 path 的独立 DDR 复位输入，
不能用 CPU preset 复位本服务或硬件音频。CPU 观察复位不撤销媒体事务。
本回归没有证明外部 arbiter 跨独立复位返回旧响应的行为；整机须显式验证。

替换旧 TF bridge 时保留现 `tf_audio_ddr_command_buffer` 的时序边界和 arbiter owner。
该 buffer 必须保持命令顺序：其接收 ACK 可以先于物理 DDR 接收，读响应仍须
对应此前接收的唯一读事务。这里记录的 read pending 从服务边界
`ddr_valid && ddr_ready && !ddr_write` 开始，到实际 `ddr_response` 结束。
不将写命令接收 ACK 解释为物理写完成。新服务不新增 DDR owner、地址或写掩码。
真实 buffer 与 direct 两种接线都已有逐帧功能回归；移除 buffer 没有功能上的必要。
定向用例先将真实 buffer 的下游停住，让服务接收读命令，再发取消或重启；关闸后
才允许物理接收，并继续扣住旧响应。队列驻留和响应等待期间均不能返回 quiet。
恢复响应后才重启，新文件完整 64 帧用独立 PCM／rate oracle 核对，不能把旧响应
解释成新文件首拍。另有响应产生与关闸同沿、响应消费在相邻 memory 沿的用例。
即使移除它，整机的 `basic_pitch_ddr_client_queues` 仍先以 slot 接收 ACK，再交给
实际 DDR，不能把上游 ready 描述为物理接受。独立 P&R 才能证明更改时序边界的收益。

原 playback service 的 `reader_track`、analysis enable/hold 和 PCM ready 保留；
`reader_restart_i` 只转发非 TF 模式的识别读取请求。`restart_i` 必须来自明确的
用户 TF restart，不能把拔卡恢复时自动产生的旧 reader restart 接到它。首次
TF 播放也需要 restart 或新 track。顶层只组合这些接口，不另建文件状态机。

`scope_tf_transport` 末尾新增 `explicit_restart_o` 和 `file_cancel_o`。新 top 将前者
接 `restart_i`，后者接 `cancel_i`；旧 `restart_o` 和 `cancel_analysis_o` 的行为不变。
进入 TF 可以同时取消分析和显式启动文件，但 `file_cancel_o=0`，不会取消刚启动的
文件。退出 TF 才发 file cancel。卡返回的旧自动 restart 保持，explicit 始终为 0；
失败文件不自动恢复。原 `playback_track` mux 仍是共享 reader 的选曲输入，不能直接
换成 TF track 而丢掉分析曲目选择。

## 准入、暂停、失败和恢复

显式 restart／新 track 先停止新 DDR 接收，排空已接受的唯一读响应，并等待帧桥
清流 ACK；随后才重启现 path。runtime 必须 valid、非 fault、非 busy。格式就绪后
仅接受实际文件率等于所登记输出模式的 PCM。不同率不改写 packet rate，不自动
请求 clock service。当前 rate/epoch/valid/busy 仍由 runtime 的唯一拥有者提供。

`run=0` 是暂停。decoder 与桥保留位置，物理 TF route 继续，compute 侧提供明确的
零 PCM，不消费桥头。`paused_o` 只在这一暂停控制已经通过保持字／ACK CDC 后置位；
调用者要保证暂停成功，应等待它。`busy_50_o` 与 `tf_busy_o` 在暂停期间保持，
因此采样率切换应拒绝。恢复 run 不重启文件、不推进 generation、不跳过队列帧。

取消和退出 TF 会撤销 route、推进 generation 并保持 quiesce 直到真实 ACK。
错误同样一次 invalidate、锁存失败、关闭 route；失败后仅显式 restart 或新 track
重新准入。自动 reader retry 和卡重新出现不会恢复失败对象。失败状态独立于旧 APB
ACK，尚无 MMIO 映射，调用者必须正式接出并展示结果。

| failure_code | 原因 |
|---:|---|
| 1 | 文件实际率与登记模式不匹配，包括 32 kHz |
| 2 | decoder unsupported／格式错误 |
| 3 | path DDR 错误或 memory readiness 丢失 |
| 4 | reader card-lost |
| 5 | runtime invalid／fault／busy |
| 6 | 已登记的 runtime rate 或 epoch 改变 |
| 7 | 所属 transport 明确报错 |
| 8 | 等待 quiet 超时 |

quiet 默认 2,000,000 个 50-MHz 周期超时。超时报告失败并撤销待启动请求，仍保持
busy 和 hold 直到真正 quiet；它不能伪造清空证明。计算域停钟不能无限占用一个
没有结果的业务请求，也不能让未知的队列被当作空闲。源时钟停止后最后一次取消
由帧桥的独立 generation 发布继续可见；源域 ACK 本身必须等源时钟恢复。

`eof_seen_o` 只表示真实 path 的 `pcm_end` 已出现。桥中仍可能有尾帧；本服务没有
有序 EOS／最后物理帧完成协议，不产生成功完成或 drained 信号。EOF 不立即
invalidate，不丢尾，保持 busy/route 直到显式取消／退出；尾帧耗尽后 runtime 可报告
原有 TF underrun。整机不能把 EOF、静音帧或 quiesce discard 当作文件成功完成。

## 识别、CDC 和重启适配

播放与识别继续互斥。TF 模式不受 `analysis_pcm_ready_i` 影响；非 TF 的 analysis
仅在所属 IDLE 阶段握手，保持原 enable/hold/ready 语义。capture-on-analysis 继续
只允许被选中的分析或运行中的 TF 读取，playlist 扫描／名称端口不变。识别自己的
采样率 profile 独立于输出模式，本服务不宣告同时播放与识别。

36-bit 保持字 `{generation, registered_rate, active, run, busy}` 经请求／ACK CDC
发布。源在 ACK 前不覆盖 held payload；慢端可合并尚未发送的状态。compute 还用
帧桥 expected generation 核对控制快照；旧 active 即使在最后一次取消后源停钟也
会失效。busy 通过保守异步断言／本地释放后与保持快照合并，不能提前释放。DDR hold
在 memory 域两级同步置位和解除。`memory_gate && !memory_read_pending` 先经
memory 域寄存器，再经原两级同步器返回 50 MHz；跨域源不再是组合 aggregate。
该寄存器按 common reset 清零，关闸和末次读响应排空之后保守增加一个 memory
边沿，随后还有两级接收延迟；超时计数不替代这个 ACK。定向回归检查源只在 memory
上升沿改变，并用恢复旧组合表达式的临时副本确认会被拒绝。

这里的 quiet 只证明命令入口已关闭且所记录的唯一有序读响应已返回，不证明已确认
的写命令物理完成，也不覆盖独立 memory reset 后的迟到响应、响应重排或外部 arbiter
owner 丢失。整机内存守护仍负责 backend readiness／复位故障隔离；本地寄存器不提供
事务 tag 或独立复位恢复协议。源寄存和两级同步的源码检查也不能替代 routed CDC。

runtime 显式启用 path 的 `NATIVE_RESTART_HOLD=1` 和默认 0 的
`NATIVE_RUNTIME_PROTOCOL=1`，选择唯一命名的 `workstation_tf_runtime_byte_fifo`
及 `workstation_tf_runtime_dma`。旧两个 storage 模块字节保留，来源 SHA 和
迁移范围见 `workstation_tf_runtime_storage.provenance.json`；它们不是 vendor。

所有 restart、换曲、取消和故障先停止 source capture／decoder 准入和 memory
工作，并真实排空已接收的唯一 DDR read。service 只在此前 clear 已完成时发布
新保持 token；本次四 FIFO ACK 和 DMA restart ACK 都经 50 MHz 两级资格确认后
才撤 memory hold，再等待实际 gate-open 返回。**不使用固定 source 拍数证明
memory 工作完成**。memory 停钟不能提前 ACK；超时报告失败并保持 busy／hold，
恢复后完成清理也不把失败文件自动改为播放成功。

新 FIFO 的 clear 第一级只进入第二级，不扇出功能逻辑。hold 下本地指针归零，
Gray 接收链持续采样，看到远端第二级指针稳定为零后才为当前 token 回 ACK。
四端都完成前禁止读写；非 unit 的跳零只发生在这一隔离窗口。新 DMA hold 同时
关闭 emit、请求和旧 FIFO 回填，accepted 旧 response 可以退休；处理 restart
且私有缓冲／等待状态稳定归零后才 ACK，不把收到请求当作完成。

service 保留 path_track 快照，只在受控 restart 时提交。native path 的换曲／
reader_fault 不再直接翻转 clear；先交由 service 关闸、排空和发布 token。
分析读取共用该握手，保留原 enable／hold／ready。取消／故障可执行内部清理，
不重臂 TF route；显式 restart 或新 track 的准入语义保持。没有局部 reset DMA
来清 capture/EOF toggle；新 DMA 在处理 token 时消费旧观察并复位自身事务状态。

path 新参数和端口都追加在末尾，默认参数 0。回归从不可变
`resource_rework_route0` baseline 读取原 path；移除精确适配后逐字节相同，默认常量
折叠回原实例及表达式，并用双真实 path 对照完整输出逐拍比较。baseline 和 accepted
来源策略未改。新源码 SHA 只能由后续显式候选登记。

专用 `run_workstation_tf_runtime_clear.py` 覆盖 memory stopped-high／low、旧
read_buf、重复 token 请求、选曲快照、reader fault、取消超时及 analysis 首帧，
对首 capture／playback byte、完整 PCM／generation、四端 token ACK 和非 unit
跳零隔离分别设 oracle。绕过 ACK 的临时副本必须失败；这些理想时钟检查不模拟
毛刺／亚稳态，也不替代新网表或 routed CDC。

## 外部媒体停止事务（显式 opt-in）

`EXTERNAL_STOP_PROTOCOL` 默认0。新 owner 显式设1后，以下端口全部为50 MHz：

| 端口 | 契约 |
|---|---|
| `stop_request_i` | 单拍请求；pending期间的重复请求合并 |
| `stop_pending_o` | 本事务清理及最终控制确认仍未完成；超时后继续保持到实际清理完成 |
| `stop_done_o` | 单拍成功，只在实际清理和最终 inactive／busy=0 mailbox ACK 后发出 |
| `stop_failed_o` | 每个接受事务至多一次单拍失败；该事务恢复后不再补发done |
| `stop_failure_code_o[3:0]` | 本事务失败码；下一次接受stop时清零，失败时保持 |

stop优先于同沿restart。接受stop后锁存停止，先走已接受DDR read排空、四FIFO及
DMA clear ACK、frame bridge sourcequiet、memory gate-open返回；进入IDLE且busy
下降后，还必须等`control_pending_o=0`，确认最终inactive／busy=0控制快照已被
compute域接收。没有直接把异步compute控制状态拿回50 MHz组合判断。compute停钟
或memory停钟均不能靠source时间经过获得done。总事务watchdog也覆盖末次控制
mailbox等待；到期发失败8，继续清理，恢复后只撤pending，不把失败改为成功。

已经停止且全部证据完成时，新的stop可幂等返回done，不重新翻转clear token或
generation。停止锁存期间，track仅作为下一次显式restart的当前选择；run、mode、
reader restart、卡恢复、transport状态变化均不自动重臂，也不重启分析读取。
只有不在pending中的`restart_i`新边沿解除停止；同沿stop仍优先。TF不请求或改变
采样率，外层owner负责先封口录音、等待本stop结果，再启动时钟事务，并单独维持
其媒体hold；释放外层hold本身不是TF的restart。

失败码沿用1采样率、2格式、3DDR/readiness、4卡、5context、6epoch/rate、7transport、
8清理或mailbox超时。与stop同沿或pending中发生的实际physical context故障会失败
该事务一次；已有停止对象的历史sticky文件故障不妨碍新的幂等清理确认。

`run_workstation_tf_runtime_stop.py`复用真实path、DMA、FIFO、WAV、frame bridge和
控制mailbox，覆盖direct及实际command buffer；单独覆盖默认0忽略stop请求、
accepted-read等待、停钟／恢复、在途合并、失败不补done、末次mailbox停钟及
显式restart恢复。移除最终mailbox ACK条件的临时副本必须被拒绝。本地stop通过
不等于录音封口、AE350命令、完整时钟切换或板上验收已经完成。
