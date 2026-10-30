# Decoder PCM 到 runtime 的原子传输

`workstation_tf_frame_bridge.sv` 是未被现有 top/profile 选择的组件。它只传输
decoder PCM 和取消身份；文件系统、DDR、播放路由、识别、录音、率切换授权及
格式状态仍由原 owner 负责。它不增加全局参数 authority，也不做重采样。

## 时钟与包

`source_clk_i` 对接现有 decoder 的 50 MHz，`compute_clk_i` 为持续运行的
76.8 MHz。两端共用异步断言的 `rst_ni`，功能 FIFO 在各域三拍本地释放。
不支持把某一个 FIFO 端独立复位。只有协调的 common reset 会重置 FIFO；
invalidate、曲目变化、card-lost、quiesce 和 rate 变化均不复位它。

源握手为 `source_valid_i && source_ready_o`。同一 source edge 一次性取样
`{source_generation32,actual_rate20,error1,left16,right16}`，共 85 bit；所有字段
通过现有 `music_async_fifo` 跨域。队列默认 16 帧，另有一个 compute held slot；
满时关闭 source ready，decoder 必须保持 valid 和全部 payload。不能以旧的
`sample_ce` 抽取 valid，也不能另外同步 rate 或二进制 generation。

compute 握手为 `tf_valid_o && tf_ready_i`。普通背压期间 valid 和整包保持；
取消或 quiesce 是显式撤销例外。每个送出的包都满足
`tf_generation_o == expected_generation_o` 且 expected identity 有效。
桥的 source/compute 接口分别属于对应时钟域，不能裸接到第三时钟域。

只有 48,000 和 44,100 Hz 被视为 runtime 支持率。其他实际率仍被接受并消费，
包保留真实 rate，PCM 变为零、error 置位，source unsupported 计数增加。
不会把 32 kHz 等数据伪标成 48 kHz，桥本身也不以 unsupported 锁死状态机。输入的 source
error 原样置入包并计数，左右 PCM 保持原值，由现有 final router 实现错误帧零输出。
没有 PCM valid 的坏格式／I/O 错误依然通过原来的格式和文件状态契约上报，
本组件不凭空制造文件完成或成功。

目的包的消费仍以 `tf_ready_i` 为准。实际 `workstation_final_pcm_router` 对错率
输入输出零/error，但**不会消费**该 TF 头；其后 FIFO 满时会背压 decoder。
因此文件 policy 必须在发现实际率不支持／不匹配时使本次文件播放失败，并显式
invalidate（或执行经过定义的退出事务）清除该代数据。不能把 zero/error 诊断帧当
EOF，不能把桥单体可消费 unsupported 包扩大为整机 decoder 绝不阻塞的保证。
回归已连接实际 router 验证这一保留头、错误结果和 policy-cancel 恢复边界。

## 取消 barrier

`invalidate_i` 是 source 域显式事件；每个采样为高的 source edge 都独立将
32-bit generation 加一，包括 common reset 后的第一拍。调用方应把 restart
上升沿、track change、card-lost 上升沿和协议取消转换为事件；不能把保持为高的
card-lost level 当作单次事件传入。多个原因同拍可合并为一次传输身份变化。
generation 仅是本传输 owner 的取消身份，不代表 event18 已携带该字段。

源在计数变化的**同一拍**注册 Gray 值。compute 独立同步该值，不依赖 FIFO
后续入包或 source 返回 ACK。源即使在最后一次 invalidate 后立即停高／停低，
compute 仍可观察最终 generation。首个 source edge 独立宣告 source 存在，
因此在本地 FIFO release 尚未完成时发生的首 clear 也不会丢失。

compute 看到身份变化后撤销 held 帧，旧 generation 的 FIFO 帧自动出队丢弃，
不等待 `tf_ready_i`。`expected_generation_valid_o` 区分未观察到源的启动状态，
`generation_change_o` 在首次发布或 identity 更新时脉冲。每个源事件都会更新
源计数；compute 可跳过中间 identity，最终 identity 会取消所有先前帧。
它不是需要逐事件消费的业务命令队列。

取消从源到 compute 有 CDC 延迟。源事件前已被 compute 接受的旧帧不会被追溯
撤销；承诺是观察取消 barrier 后不再交付旧帧，而且旧帧始终保留旧标签。
上层 final router 必须继续比较 packet generation 与独立 expected generation。

为避免新代 PCM 先于新 identity 到达，compute 另维护 ACK counter，逐拍最多加一
直到追上已发布的 expected generation，并在同一拍注册对应 Gray。返回源域后，
只有 ACK 与当前源 generation 相等，且 compute identity valid 已返回，才开放
source ready。ACK 不复制可能跳步的多 bit Gray 字；其自身始终单步。
该回程只控制后续新包放行，不是最后一次取消可见性的前提。

所有 binary、Gray、ACK 和预期身份使用同一 `INITIAL_GENERATION` 起点，默认零。
near-wrap 回归用 `0xfffffffd` 同步起点，正常覆盖 `0xffffffff -> 0`。
集成要求 compute 持续运行且能跟上 50 MHz source 的单步事件；不得在一个
未观察区间内绕完整 2^32 次并复用仍在途的身份。这是有限 32-bit 标签的边界，
不以延长队列或同步二进制总线掩盖。

## 媒体 quiescence

`source_quiesce_i` 是 source 域保持 level。调用方从发起请求起保持到 quiet ACK，
期间立即禁止新入包。compute 同步该 level 后撤销 held、排空剩余 FIFO，
再留五拍稳定余量，使最后 write pointer 与 generation 同步先完成。
`media_quiescent_o` 是 **compute 域**证明：请求仍有效、身份已发布且稳定、
FIFO 和 held 均为空。它能在 source 停钟后完成；该输出不能裸接 50 MHz 策略。

`source_quiescent_o` 是返回 source 域的 ACK，额外要求返回 generation ACK 与
当前源身份相同。source 停钟时这一回程不会更新；源恢复后会完成。正常 50 MHz
调用方应使用它，并保持 request 到事务结束。恢复时 source ready 还等待 compute
quiesce 状态的回程解除，避免第一帧到达时 compute 仍在排空。快速未握手的
quiesce 脉冲不构成受支持的媒体事务。

quiet 回程从 compute 域的独立发布寄存器进入两级 source 同步器，不把 Gray 解码、
身份比较和 FIFO 排空的组合锥直接送到异步首级。发布寄存器使回程 ACK 至少多一拍
compute 延迟；compute 域的 `media_quiescent_o` 仍保留当前身份和 quiesce 的组合
撤销条件。source 在 invalidate 当拍及 generation ACK 尚未追上期间禁止确认 quiet，
因此旧的 quiet 发布值不能为新 generation 提前确认排空。取消判断直接比较已经过
两级同步的 Gray generation 与已提交 expected generation 的 Gray 编码；Gray 映射
为双射，这与先解码后二进制比较在全部 32 位二值输入上等价。输出 expected 身份的
32 位解码使用五级并行前缀 XOR，身份、ACK 的单步 Gray 跨域协议保持不变。

取消丢弃与 quiesce 丢弃分别饱和计数，单帧不会同时计入两者。
global reset 丢弃独立于这些 session 计数。桥不会背压物理音频 sample schedule；
缺帧／错误／不匹配由 runtime final router 和 serializer 按已有零／error 契约处理。

## 现有 TF 出口与保全要求

未来适配点是 `tf_audio_ddr_path` 的 **50 MHz** `pcm_valid/pcm_ready`、
`pcm_left/right` 和 `sample_rate_hz`，在同一个源握手点建立包。该出口来自实际
`tf_audio_decoder_ip`；WAV header rate 和 stereo PCM 已处于同域并支持背压。
旧 `tf_workstation_audio_bridge` 的 audio 域 `pcm_active`、独立 `rate_sync` 和
旧 TF DAC sample tick 不满足本契约，不能直接改名接入。

现 reader、playlist、recognition 分支和 owner3 TF DDR 客户端保留。识别是否与
播放共享 decoder ready 需要单独缓冲／丢窗策略，不允许慢分析停止实时输出。
EOF、曲目数、播放完成、媒体 busy 和格式状态均继续由相应 owner 提供。
本组件尚未改接这些实际分支，真实 SD/FAT/DDR 播放验收仍待集成。

## 物理接入门禁

离线仿真不证明物理 CDC。新 profile 必须锁定源码和实际实例，逐一约束双向
32-bit Gray 的 source register 到首级同步器：max delay 和 bit skew 以各自产生
周期为界（source 20 ns、compute 约 13.0208 ns）；保留 ASYNC_REG、精确首级
异步路径例外、本地 reset release 和现 FIFO pointer/payload 稳定性门禁。
不得用跨整域 false path 隐去这些证明，不能从本测试推定 routed 通过。

新 profile 还需证明真实 TF rate/PCM 取样、取消／媒体事务、识别保全、源身份与
位流身份及板级音频行为。回退为继续选择旧路径；该 owner 可以保持未选中。
