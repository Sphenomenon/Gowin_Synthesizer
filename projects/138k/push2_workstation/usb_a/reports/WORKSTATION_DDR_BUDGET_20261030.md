# D01：DDR 分配、队列与服务预算调查

日期：2026-10-30。此检查点核对 M0 的分配和服务接口，**不勾选 D01，不代表并发、双采样率或实板验收通过**。没有改地址图、生产仲裁器、profile、冻结输入或板上内容。

调查绑定 F01 revision 1 候选 `custom138k-workstation-v1-2ed5155f12a6b585`，而非任意活动 `rtl/` 文件。实际 prepare 输入来自 `~/.cache/gw138k-task-20261030/f01-profile-candidate-final/workstation/Prj1`；逐文件 SHA256、与 F01 清单的比较、诊断命令和日志见 [ddr_budget.json](workstation_task_20261030/ddr_budget.json)。该候选实际实现 48 kHz；下述 44.1 kHz 数字是下一阶段的需求计算，不声称已接通。

## 1. 地址与 owner

地址权威仍为 [ddr_address_map.vh](../rtl/ddr_address_map.vh)。表内范围是 **DDR 物理字节地址**，`app_addr=byte_address/4`；一笔 BL8 搬运 32 B，起点按 32 B 对齐，native 地址递增 8。物理范围为 `0x00000000..0x3fffffff`，合法 native 地址保持 bit28 为 0。

| 区域 | 物理字节范围 | 容量／当前用途 | 实际 owner |
|---|---|---|---|
| 视频页 0／1 | `00000000..003fffff`／`00400000..007fffff` | 各 4 MiB；1920×1080 RGB565 有效像素各 4,147,200 B | 写 3，读 1 |
| 启动 BIST | `00000000..007fffff` | 与视频别名，运行前独占；不算并发客户端 | 0 |
| 显示保留区 | `00800000..00ffffff` | 8 MiB；当前 DSP2 记录范围 `00800000..008bffff` | 写 3，快照读 7 |
| AE350 页面 | `01000000..017fffff` | 两个 4 MiB 页面；CPU 虚拟字节地址 `10000000..107fffff` 经 AHB bridge 映射 | CPU 2，页面扫描 1 |
| TF bank 0／1 | `01800000..057fffff`／`05800000..097fffff` | 各 64 MiB，双 bank 流式重用，并非文件长度上限 | 4 |
| growth pool | `09800000..0fffffff` | 104 MiB 保留，未据此分配新增业务 | 未分配 |
| NN pool | `10000000..2fffffff` | 512 MiB 总池；现有 Basic Pitch 子分配见下文 | 5 |
| bulk pool | `30000000..3fffffff` | 256 MiB 总池；包括 delay 与 Basic Pitch 历史 | 5／6 |
| delay ring | `30000000..3001ffff` | 第一个 1 MiB granule 内使用 128 KiB，16384×8 B | 6 |

实际 `hdmi_display.v` 实例化 `basic_pitch_ddr_client_queues` → `basic_pitch_ddr_arbiter_pipeline`，**display reader 使用 tag 7，tag 0 仅为 BIST**。不能套用旧活动仲裁器中运行期复用 tag 0 的映射。

现有 `basic_pitch_ddr_map.svh` 在 NN 池的 `10000000..108fffff` 分别用九个 1 MiB granule 表示 activation、model、notes、onset、contour、reduce、note-post、onset-post、CQT signal；在 bulk 的 `30100000..304fffff` 分别保留 note、onset、analysis、backpointer 四个 granule。这些是现有子分配范围，不表示每一字节都已使用，也不是可再分给录音的空闲容量。delay 与 backpointer 已分离；CPU 的同值 `0x10000000` 是虚拟地址，不能与 NN 物理地址混淆。后续分配应在父地址图登记这些占用与新增范围，不另建第二个分配权威。

USB 像素消费、DDR 长录音和 D 音源尚无本候选中的独立 owner／已登记新区域。Push 当前消费摘要，不能把它计作已经接通的 DDR 像素读取器；也不能直接在仅剩的 tag 编码上隐式复用新业务。

## 2. 接受、返回和缓存

UI 标称 100 MHz，一周期 10 ns。队列入口 `ready` 表示一条完整请求进入本地槽，**不表示控制器已受理，也不表示写入已经对扫描可见**。现有路径没有逐写返回信号；发布需要明确控制器的写读可见性保证或另做屏障。

| 边界 | 实际容量／行为 | 当前有限等待依据 |
|---|---|---|
| 共享仲裁 | 每个 owner 一个请求槽；一个 registered grant 预留引用；一个 native command buffer；预留引用不另存一笔 payload | 理想控制器下 native 稳态启动间隔 2 UI 拍；固定优先级不提供所有 owner 的上界 |
| 返回账本 | `TAG_BITS=5`，最多 32 笔已 native-issued 未返回读；按发出顺序返回；额外寄存一拍 data 与 owner | 无 tag 的响应置 sticky fault；不能接收乱序、重复、丢失或发出同拍返回 |
| scan | 双行 RGB565 RAM；8×256-bit response FIFO；每 beat 分 4 UI 拍入行 RAM | `issued-received<8`，received 在四拍完成后推进，故 **8 个总额度** 包括在途、响应队列和正在写入项，不是额外 8+8 |
| TF | capture／playback 各 4096 B 异步 FIFO；打包／解包各 32 B；DMA 一笔 read outstanding；另有请求缓冲 | 写 pending 先于读；读完并搬入 playback FIFO 才释放 ring 位置；无总线服务超时上界 |
| delay | 双向各 512×65-bit FIFO；每 4 个 stereo32 帧组成一笔 32 B；最多一笔 read | prefetch 目标约 448 样本；DMA 在等待读返回时不能继续排写；失去响应可能使 flush 永久等待 |
| AE350 | 一个 64-bit AHB transfer／一个读；mailbox CDC | native 写数据复制四份，active-low byte mask 只开目标字节；AHB 可无限等 ack，无 DDR 服务超时 |
| CNN／model | 16×49-bit 请求 CDC FIFO、单条 command buffer、4×16-bit 返回 CDC FIFO；pipeline 与 DDR16 port 分别限制一笔读 | 单个 16-bit 访问消耗整笔 32 B native 事务；写掩码只开 2 B。读未完成会停后续分析请求，不应停实时采样 |
| 显示 writer／reader | raster 一笔 256-bit pack、merged bridge 一条 pending；snapshot reader 一笔读，片内缓存 512×32+2048×32+512×16 bit | writer 背压 renderer；reader 可无限重试无效或变更记录；不拖停音频，但无 UI 完成期限 |

普通 video／TF／delay 写全 32 B；CPU 与 CNN 使用 active-low byte mask。当前诊断仅检查 native 发出数与无意外返回，不覆盖任意 mask、tag 深度、队列峰值和 reset/cancel 正确性；这些仍是 D01 的验收缺口。

TF 的 DDR 已写入 2048 B 后可开始流播放；decoder 的 playback FIFO 起播门槛通常为 1024 B，小文件降为实际文件长度。这里计的是原始文件字节，包含容器头；不能将 1024 B 直接宣称为始终可用的 PCM 储备。CNN 使用 22.05 kHz 分析、`WIN_LEN=44100`、8 个时刻、hop=22050/4、16 列 feature tile；DAC 切到 44.1 kHz 不等于更改分析模型采样率，也不能由“4 Hz 时间网格”推出每秒可完成四次推理。实际分析总请求量／峰值仍需逐阶段计数。

## 3. 需求与期限

下表是需求算式，**不以平均值证明服务上界**。TF 限定双声道 PCM16；其他 WAV 格式／头部／突发传卡开销另计。显示按目标每秒完整更新 60 次计算，实际 renderer 刷新率未在本检查点测量。

| 业务 | 48 kHz | 44.1 kHz | 计算口径 |
|---|---:|---:|---|
| HDMI scan | 248,832,000 B/s；7,776,000 beat/s | 相同 | 1920×1080×2×60 |
| 60 Hz raster 写 | 248,833,920 B/s | 相同 | 完整 RGB565 加每帧 32 B metadata |
| compact snapshot 每方向 | 700,800 B/s | 相同 | 每次 365 beat×32 B×60；写另有启动时 3 beat |
| TF 单向有效 PCM | 192,000 B/s | 176,400 B/s | fs×2声道×2 B |
| TF DDR 中转读＋写 | 至少 384,000 B/s；12000 beat/s | 至少 352,800 B/s；11025 beat/s | 双向各一次，未扣除 M03 将来的流式迁移 |
| delay DDR 读＋写 | 768,000 B/s；24000 beat/s | 705,600 B/s；22050 beat/s | fs÷4×32 B×2；48 kHz 的 384 KB/s 只是单向 |
| 未来 R00 录音单向写／下载单向读 | 各 192,000 B/s | 各 176,400 B/s | 尚无分配与 owner；必须另计突发、mask 和预取 |

上述现有显示＋TF＋delay 的 60 Hz 需求约 500,219,520／500,125,920 B/s，仍未含 CPU、CNN、USB 像素、录音或 D。理想无停顿 native pipeline 上限 50 Mbeat/s，即 1.6 GB/s，不是物理控制器可保证带宽。读写方向切换、刷新、bank 冲突、返回延迟和扫描仅 8 额度决定期限；剩余平均带宽不能替代这些约束。

1080p60 的 pixel clock 为 148.5 MHz，水平总长 2200，单行周期约 **14.8148 µs**。scan 在行 N 的 x=1919 发送 N+2 请求；到目标行 x=0 约 2481 pixel clocks，即 **16.7071 µs**，仍须扣除请求 CDC、完成 CDC 和行标签检查。启动一次请求连续预取两行，需单独覆盖 vblank 与首次帧发布。正常每行最多 120 beat、3840 B；入行 RAM 的绝对下限为 120×4=480 UI 拍，即 4.8 µs，另加首笔返回、队列、仲裁与 CDC。源码的 100000 拍（1 ms）计时是无活动看门狗，不是合格的行截止期限，持续慢返回甚至可不断复位它。

扫描 admission 集成诊断进一步明确第二条期限：请求 mailbox 只有在完整取行 ACK 返回 pixel 域后才接收下一次 x=1919 触发，因此还须在约 **14.8148 µs 减去请求／ACK 往返 CDC** 内重新可用。仅早于目标行 N+2 的像素期限仍可能错过下一行触发。后续最大耗时应同时核对 RAM／tag 完成和 mailbox 可重新接受，见 [扫描 admission 证据](WORKSTATION_SCAN_ADMISSION_20261030.md)。

[D5 历史证据](WORKSTATION_HDMI_SCAN_WINDOW_20261028.md)测得独立配置在有后台写时取行 20.50／20.51 µs，无后台写常见 5.63 µs、个别 5.93 µs。这证明应观测整行最坏耗时及限制扫描窗口内的新后台写；它不是本 F01 的硬件测量。F01 共享同一 scan 模块，但 `fetch_busy` 没接写入门控，不能继承 D5 验收。

4096 B 纯 PCM16 FIFO 理想上限对应 21.333／23.220 ms；1024 B 为 5.333／5.805 ms，均未扣容器、CDC、预留和最低水位。delay 的 448 样本约为 9.333／10.159 ms，512 项满容量约 10.667／11.610 ms；这些是容量换算，不是可容忍任意长连续停顿的证明。当前 delay 固定 `ECHO_SAMPLES=9600`，在 44.1 kHz 会成为 217.687 ms，尚需 A07 适配。

## 4. 实际仲裁的结构压力证据

保存的 [ddr_budget_tb.sv](workstation_task_20261030/ddr_budget_tb.sv)直接实例化上述 prepare 的实际 queues/core。控制器恒 ready，读发出下一拍返回；scan／display 为读，其他有效客户端连续写，地址低位区分 owner。统计 **native app_en**，不把进入本地槽当作服务完成。Icarus 13.0，七阶段共 180000 UI 拍，无 response fault。数组按 owner 0..7：

| 有效 mask／窗口 | native issue 数 0..7 | 观察含义 |
|---|---|---|
| `fe`／20000 拍 | `0,5000,0,0,4999,0,0,0` | scan 与 audio 持续生产时，其余等待到窗口末仍无服务 |
| `fc`／20000 拍 | `0,0,0,0,5000,4999,0,0` | 去掉 scan，audio／music 仍可阻挡 CPU、writer、delay、display |
| `6c`／20000 拍 | `0,0,1666,1667,0,3333,3333,0` | 去掉高优先级组合，CPU／writer／music／delay 均推进；本次观测最大间隔 14／12／6／6 拍 |
| `68`／20000 拍 | `0,0,0,3333,0,3333,3333,0` | writer／music／delay 均推进 |
| `60`／20000 拍 | `0,0,0,0,0,5000,4999,0` | music／delay 均推进 |
| `fe`／40000 拍 | `0,10000,0,0,9999,0,0,0` | 无服务者等待从 200 µs 延长到 400 µs |
| `fc`／40000 拍 | `0,0,0,0,10000,9999,0,0` | 同上，控制器完全无停顿仍不能给出通用服务期限 |

有限仿真本身不证明数学上的无限等待。结构依据是 core 在 BIST 后依次选择 scan、music_turn、audio、display、条件 music、delay、轮换 CPU/writer；无年龄／水位／deadline 升级。高优先级请求可以无限继续，低优先级没有强制轮到的分支，因此不存在仅由仲裁器给出的全客户端有限界。延长压力窗口使无服务者等待同步增长，与该结构一致。

**压力输入故意超出真实 scan 的 120 beat 突发和 TF 的实际到达率**；这不是本候选在真实媒体负载下已发生无限饥饿的结论。要证明受约束业务的上界，必须把各生产者最大突发／最短间隔和控制器假设一并冻结，而不能引用源码“占比很小，因此不饥饿”的注释。

## 5. M0 可冻结的接口与待验证预算

先冻结测量端点：`request_pending → local_slot_accept → native_issue → ordered_read_return → consumer_commit` 分别计数；每 owner 记录读写数、最长 pending age、local queue 峰值、native 未返回数、最低预取水位、最大无服务间隔、超时／丢弃／旧代次计数。scan 另记 mailbox 到完整行入 RAM、到 pixel 域 tag 有效的最大值，启动两行单列。`ready`、native issue、写可见、记录发布不能合并。

以下是 **下一实现的建议预算**，尚非实测保证或已通过的门禁：

| 条件／消费者 | 建议可测门限或约束 | 关闭条件 |
|---|---|---|
| 控制器 | 分别冻结待发读的最大 `app_ready` 空档 Gread、待发写的 `app_ready && app_write_ready` 联合空档 Gwrite、native read 到 return 的 Lread；包含刷新、最坏地址序列、读写切换和最多 32 read outstanding | F03 实板／IP 规格给值，长随机及针对性停顿模型不得超过；单独 ready 有界不推出联合写 ready 有界 |
| scan | 正常完整 120 beat 从 memory 域开始取行至最后四分组入 RAM先以 **≤1200 UI 拍（12 µs）** 为候选 SLO；两次 CDC 后 tag 必须早于目标行 x=0 | 12 µs 是为约 16.707 µs 原始余量留空间的设计目标；实际 CDC／控制器实测不足时重做缓存／策略，不延长行时钟掩盖 |
| 后台写 admission | 扫描窗口暂停新的 raster/shared/CPU 后台写；不撤销已接受事务；先审计本地槽＋reservation引用＋command buffer 的尾部及控制器内部队列 | 接入 D5 策略后覆盖满尾部、首行、换帧及长刷新；TF／delay 紧急访问另有有界额度，不能一概暂停 |
| TF／delay 实时储备 | 引入明确 byte／sample 水位；初始以 TF 有效 PCM≥1024 B、delay wet≥128样本作为可用储备门限；紧急请求 pending→consumer commit 先以 **≤1 ms** 为目标，并验证任意滚动窗口的补给率不低于消费率 | 门槛必须在真实 parser／FIFO／CDC 处测量；容量减去 packet、chunk、在途与取消余量。只限制单次等待而补给总量不足仍失败 |
| 其他已接受后台请求 | 初始以 pending→native issue **≤1 ms** 为公平性上界，采用有界轮转／年龄或额度；CNN 模型装载与分析分阶段统计，CPU 还需另定总线错误返回期限 | 连续 scan、音频紧急、CNN／CPU／writer 混合突发下仍满足；不能靠永久取消后台请求来使统计好看 |
| cancel／失钟／DDR 丢就绪 | 采样节拍继续；delay 欠载 wet=0＋sticky、overflow 丢新反馈＋sticky；TF 终止旧流；读账本排空或全域一致复位，明确旧返回隔离；后台任务进入可观察失败／取消终态 | 现有 delay 流在 underrun 后会相对错位直到 clear，不能把 dry fallback 记作音频正确；当前无响应的 flush／AHB 无限等必须补终态 |

水位门限不是对现有 RTL 的描述。1 ms 相对以上储备有余量，但还必须证明 1 ms 内能补回足够 beat，并包含读响应、分四拍写、解包和 CDC；不得仅测到“偶尔轮到一次”。scan 1200 拍与所有实时储备约束必须在同一并发模型下同时满足。

## 6. 下一实现和验收缺口

下一步应先把全客户端计数／最大等待／水位接到可观测诊断，并在现有版本化仲裁边界中实现扫描 admission 与有界公平策略；给控制器 stall／return 假设配置和超限 fault。修改来源必须产生新 profile revision／候选身份，不能覆盖这里的 F01 输入或转移 D5 的验收。

随后用实际 scan＋TF＋delay＋CNN＋CPU／writer RTL，同时测试正常和恶意最大突发、最高 outstanding、任意写 mask、受控返回延迟、ready 联合停顿、复位／取消／迟到返回，两种音频模式分别核对消费者水位与 frame 连续性。USB 像素、R00 和 D 的分配与新增 owner／复用调度必须先登记，再加入同一预算。M03 去除播放 DDR 中转后应按请求账本确认 owner4 对应路径归零，并重新量化片内预取净成本。

本检查点仅完成来源调查、需求计算和结构诊断：没有物理 DDR 最大延迟、全客户端 mask／峰值覆盖、44.1 kHz 整机音频、P&R 或实板并发证据；没有新位流、SRAM／Flash 操作及部署身份。回退不涉及板卡，删除本报告与诊断证据不会改变任何生产输入。
