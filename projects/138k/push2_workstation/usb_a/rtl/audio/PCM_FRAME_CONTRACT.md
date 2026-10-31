# 双采样率 PCM 帧与输出交付契约

这是新板任务的内部接口，供 A03／A05／A06 逐步接入；现有 profile revision 2 尚不消费新串行器或此契约。18-bit MIDI、现有 128-bit 诊断 tap、BLE 格式 1 和显示布局 v1 均维持其原字段含义。以下字段不能被当作这些旧报文已经具备的新能力。

## 帧身份及权威

每个新音频流帧以 `{rate_44k1, stream_epoch[31:0], frame_sequence[31:0], pcm_left[15:0], pcm_right[15:0], error}` 标识。rate 为实际 48000／44100，epoch 由常开切换事务唯一分配，sequence 是该代次输出 slot 的模 2³² 序号。一个代次内不跳过 slot；正常欠载仍占自己的序号，输出明确的零／error 帧并计数，禁止重放上次样本来填满时间线。

公共参数仍由 `workstation_parameters` 提交；音源适配与效果在其所属音频模块。最终 PCM 边界负责音源选择后的主音量／静音，且只应用一次。`workstation_i2s_serializer` 输入已经是最终 PCM，不再乘主音量。I2S、默认分析、录音应消费同一完成帧及其身份；原音量前诊断须明确命名。当前 A/B/C／矢量／TF 的串行观察／旧 FPC 路由尚未迁移，不能依据本接口宣称 A03 完成。

录音遇 error／代次变化进入既定失败或封存流程，不把 error 零帧作为正常连续录音。分析遇 error／代次变化丢弃不完整窗口。显示发布须绑定实际采样率和分析代次。旧 48 kHz 线协议拒绝未经协商的 44.1 kHz 对象，不能只改标签。

## 输出时基与跨域桥

48 kHz 使用 12.288 MHz／256，44.1 kHz 使用 16.9344 MHz／384。BCK 分别除 4／6；每帧 64 bit，左右各 32-bit slot，标准 I2S 延迟一 bit，PCM16 后补零。选择后的 MCLK 是唯一输出时基。

串行器发出的 `request_o` 是 selected-MCLK 域单周期脉冲，附带固定的 rate／epoch／sequence。预填充首先请求 slot 0；开始发送 slot N 的同一完整帧边界请求 N+1。桥把请求原子送入常开的计算域，只为该请求触发一次 render，完成后把同一身份的最终 PCM 送回。不得继续用独立 1600-cycle 自由运行节拍生产，再依赖 FIFO 长期吸收两颗振荡器的频差。

计算域继续使用合规的 50 MHz 派生 76.8 MHz 时钟：一帧名义预算为 1600 或约 1741.50 个计算周期，实际最短间隔还取决于两颗参考的频差。请求同步、队列、引擎、效果、最终处理、响应 CDC 和输出建立时间全都扣在该预算内。后续桥必须量化最短间隔与最大渲染耗时，至少保留一个完整目标帧的预填充；此文没有证明现有所有 DSP 已满足两种模式。

桥需要有界请求／返回缓存、显式溢出计数和单个 render 的身份保持。若旧 render 未完成，新 slot 到期时不得覆盖其 tag；将新 slot 的缺失记录为 deadline／欠载，迟到响应只能丢弃，不得被套上新 tag。没有 backpressure 能推迟物理输出时钟。串行器本地只保存下一帧；`sample_ready_o` 仅表示可检查／接收一条响应，不表示其身份有效。rate／epoch／sequence 不一致的响应被消费并计数，不能占据预填充位置。

`workstation_pcm_frame_bridge` 实现上述有界请求／返回通道：一个尚未接收的请求、一个执行中的 render、一个尚未消费的返回。请求和返回均用保持数据加双向 toggle／ACK 跨域；payload 在 ACK 返回前不变。计算端仅在 render ready 且返回槽空时启动，整个 render 保留同一身份。邮箱满时新请求计入饱和 drop，不覆盖旧请求；物理 slot 仍由串行器按时前进，缺帧与迟到分别计数。

返回 payload 为 98 bit `{rate, epoch, sequence, pcm, error}`；`rendered_error_i` 与 PCM 一同锁存，经 `sample_error_o` 交给串行器。新的 tagged-frame 装配必须显式设置 `workstation_i2s_serializer.SAMPLE_ERROR_ENABLE=1` 并连接 `sample_error_i`；默认 0 保留既有无此位接口的行为。匹配身份的 error 样本仍占原 slot，物理输出零、完成 tap 的 `frame_error_o=1`，单独累加饱和 `source_error_count_o`；它不增加缺样的 `underrun_count_o`。过期／错代次的 error 样本与其他过期样本一样拒收，不污染下一帧。录音与默认分析应消费串行器的完成帧，不能把计算完成脉冲当成已按期送到物理出口的证明。

启用 `SOURCE_HOLD_ENABLE` 的音源历史切换会撤销旧预取并保留两个完整帧的保护窗口。已经开始的串行帧完整结束；其后的受阻 slot 继续输出零、发布带原 rate／epoch／连续 sequence 的 error 完成帧，并累计 `source_error_count_o`。这属于明确的源撤销，不累计缺少按期 render 的 `underrun_count_o`。MCLK／BCK／LRCK 不停，显示／分析／录音仍能观察真实零帧及错误身份；保护窗口内不发新 render、不报告 running 或 prefill，过期返回继续消费并拒收。窗口结束后重新请求下一 slot，只有新返回能恢复有效 PCM。未受阻 slot 真正缺样仍按原约定累计 underrun。

桥的握手、tag 与计数只接受全局复位。串行局部复位或停钟不清除执行中的旧 render；恢复时旧返回在局部 reset／quiesce 条件下被消费并计 discard。`quiescent_o` 属于计算域，须同时满足已同步的串行 quiet、请求双向 ACK 完成、render 结束及返回 ACK 完成，再同步给常开事务。停止高电平的源尚未恢复时，不能伪造此排空确认；常开事务超时负责隔离故障。

`request_drop_count_o`／`return_discard_count_o` 属于串行域；`cancelled_request_count_o`／`cancelled_render_count_o`／`unexpected_render_count_o` 属于计算域，均为全局复位清零的 32-bit 饱和计数。整机不能直接裸采跨域计数。此桥尚未进入生产来源，bundled payload、首级控制同步、复位释放及跨域位间 skew 必须在实际组合的 SDC／routed 审计中逐项约束，独立仿真不能代替该物理证明。

## 完整帧切换与故障

`quiesce_i`／`resume_i` 必须先同步到 selected-MCLK 域。正常请求 quiesce 后继续完成已经开始的左右声道帧，在最后一个 bit 的 BCK 落沿静音，清除下一帧并应答 `serial_quiescent_o`。该应答只证明串行端；常开事务的 `frame_quiescent_i` 还须合并跨域桥的排空／旧 render 结果清理，不能只接串行 ACK。

不复位公共参数、held／deferred 音符、USB、DDR 或 AE350 来完成切换。正常切换停止新 render 请求，排空旧 render 后再撤选 DCS。故障时立即局部静音／复位；常开计算域仍须独立记住旧 render 身份并排出迟到结果，新 epoch 的预填充必须等旧渲染彻底隔离。整个计算引擎若还没有独立取消／排空接口，不能直接把串行复位接到它上面。

新 mode／epoch 在局部复位释放前至首个 MCLK 采样边沿保持稳定；串行器该边沿锁定配置，运行中不改变分频。下一次请求的 staged 身份可以在旧帧排空时提前变化，旧流继续使用已锁存的身份，不能用新 staged 数值解释旧 BCK 或 PCM。PDN 保持 4 帧，启动静音持续到至少第 1028 帧，再等第一目标样本预填充。`prefill_ready_o` 只证明串行器已准备，需合并桥／DSP 配置就绪。`resume_i` 仅允许在完整帧边界启动输出；第一完整帧实际发送后才产生 `output_running_o`，常开事务随后原子提交实际 rate／epoch。首帧已经使用 staged 身份，不能沿用旧 active 标签。

quiesce 应答／prefill／running 均须原子同步回 50 MHz，并在每次新事务清除。正常 quiesce 后必须经过局部复位才开始新代次。故障异步复位会立即隔离物理输出；它不提供外部振荡器任意停振时仍完整输出残帧的保证。`underrun_count_o` 和 `rejected_sample_count_o` 为每局部流复位清零、32-bit 饱和计数；整机诊断须在复位前保存／累计终态，不能让重置计数抹去故障。

## 当前独立验证与剩余接入

`sim/test_workstation_i2s_serializer.py` 在实际 BCK 上升沿独立逐 bit 解码，验证 48→44.1→48 的三个局部流、256／384 MCLK 帧周期、左右 PCM16、I2S 延迟／padding、完成 tap 等价、预填充、序号连续、旧序号／旧代次／错误采样率拒绝、显式欠载、帧中 quiesce 后整帧停止。此测试使用有界响应模型，尚无真实引擎、跨域桥或板上 DAC。

后续必须完成：真实请求／返回桥与 DSP 外部节拍、双模式系数与历史清理、统一最终 PCM／各 tap 迁移、持音与释放跨切换、AE350 请求及任务忙时策略、AK4493S 的 384fs／PDN／SMUTE 手册核对，以及同一整机候选的 SDC／CDC／P&R／SRAM／真实音频验收。
