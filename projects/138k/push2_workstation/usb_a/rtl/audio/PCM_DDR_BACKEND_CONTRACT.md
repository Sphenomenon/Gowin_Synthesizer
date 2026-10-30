# 未选择的 R00 PCM DDR 后端契约

本模块只实现一个有界、易失的存储槽。录音业务 owner 提交 `object_id/rate_44k1/epoch/first_sequence/limit_frames`，并消费存储事实；模块不生成业务对象 ID、不写公共采样率、不处理 BLE 命令或格式协商。PCM 固定为双声道 PCM16，`pair[15:0]=left`、`pair[31:16]=right`，DDR／下载均按小端字节排列。48 kHz／44.1 kHz 是内部描述符事实，**不扩展现有 BLE 格式 1 的 48 kHz 语义**。

所有端口均在持续运行的 DDR UI 时钟域。正式接入须使用既有最终 PCM 帧 CDC，并保留完整帧、序号、epoch 和实际采样率；本阶段没有实现/选择该 CDC 或音频 tap。模块没有采样 ready，调用方不得停止采样等 FIFO／DDR。默认 512-frame FIFO 仅保存 2 KiB，另有打包、已发布命令和两拍下载预取。默认容量 16,384 帧=64 KiB，在 48 kHz 为 341.333 ms，在44.1 kHz 为371.519 ms。

## 存储生命周期

`create_i && create_ready_o` 锁存由 owner 提交的描述符。ID/epoch 必须非零，帧上限为1..CAPACITY_FRAMES；错误描述符进入 ERROR。创建同拍 PCM 不计入，下一拍开始采集；采样序号从提交的 first_sequence 开始按32-bit模加1连续递增。描述符输入在接受后可以改变，已锁定对象不跟随变化。

| state | 值 | 允许行为 |
| --- | ---: | --- |
| EMPTY | 0 | 接受 create |
| CAPTURE | 1 | 无背压接收符合 epoch/rate/sequence 的 PCM；容量满自动进入 SEALING |
| SEALING | 2 | 禁止新采样，排空 FIFO 和 pack；提交不足8帧的最后 BL8及 active-low mask |
| READY | 3 | 所有 PCM 已被 native 写接口接受；对象数据和描述符不可变，允许下载引用 |
| ERROR | 4 | 保留首个错误原因，禁止发布/下载；已发布命令和读返回继续排空 |
| CANCELLED | 5 | 显式取消后的终态，继续排空在途命令／返回 |
| RESET | 6 | source/backend 的 soft_reset 终态，继续排空在途命令／返回 |

`seal_i` 的接受边界不包含同拍 PCM；已有 FIFO 内容继续排空。达到 frame_limit 的最后一帧计入后自动封存。READY 要求 FIFO空、pack空、无已发布命令／读，以及 `committed_frames==frames`。封存空对象允许0帧，不产生伪造的数据字节。READY 后来的 PCM、源就绪或错误变化不改对象。

`cancel_i/soft_reset_i` 优先关闭新采样／读，并作废本地 pack、FIFO、预取和下载。首个终态保持至 clear 或整域复位；重复取消不会重新创建对象。已发布的 native 命令保持 valid/address/data/mask 稳定，直到实际接受；已接受读无论超时或取消都必须等返回后丢弃，不能忘记账本后重用同一无标签返回通道。

新增 `TRANSPORT_FAULT_ENABLE` 默认0，默认路径忽略 trailing `transport_fault_i`。显式设1后，core/bridge的transport fault在CAPTURE、SEALING、READY及下载期间都关闭admission和输出，非终态进入failure9/ERROR，已有终态保持；不借用只在CAPTURE生效的source_error。sticky transport fault仍高时，终态也不开放clear/create，soft_reset不能重新arm。共同复位控制器、返回账本、native bridge和backend才恢复；原已发布命令和已接受读仍按下述规则排空。

`clear_i && clear_ready_o` 只在非采集中、无引用且所有 native 命令/读已排空时清除身份和局部缓存，回到 EMPTY。复用同一个 DDR 区域必须经过 clear；RAM 数据本身不擦除，只有描述符范围内已提交字节可下载。cancel/reset/fault 同拍阻止 clear。`quiescent_o` 表示无已发布命令和读，不表示任意旧 DDR 数据已物理擦除。

### 同拍命令与 admission 优先级

调用方可以同时提出命令；有 ready 的命令只在 `valid && ready` 为1的采样沿接受，不能先接受再由另一个命令静默覆盖。优先级针对当前状态，未接受的命令可由调用方保持或重试：

| 同拍条件 | 接受边界与结果 |
| --- | --- |
| cancel／soft_reset／fault 与新请求 | `create_ready/clear_ready/reference_ready/download_ready` 均为0，PCM及下载输出也关闭；已发布 native 命令仍稳定排空。非终态同时出现时 soft_reset 优先于 cancel，cancel 优先于 fault；已有终态保留 |
| EMPTY 的 clear + create | clear 优先，`clear_ready=1/create_ready=0`；回到 EMPTY，不宣称接受 create。create 保持至 clear 解除后才可能接受 |
| READY无引用的 clear + acquire | clear 优先，`reference_ready=0`，不产生 granted/error；对象清除 |
| release + acquire／download | release 阻止新引用及下载 admission；无旧引用时不产生新引用或 released。有旧引用时立即关闭输出并按原账本排空后 released |
| acquire + download，无旧引用 | acquire 可接受；download_ready仍为0，须在引用已持有后重试下载 |
| clear + release，已有引用 | clear_ready仍为0；release排空并释放引用后才开放clear，不能在释放前清对象 |
| create + seal，在EMPTY | create可接受；seal只作用于已在CAPTURE的对象，创建沿PCM和seal均不计入新对象 |

同拍 unexpected response 属于 fault，即使 READY且原本 quiescent，也不能同时接受新 download。释放、取消或错误与最后一个输出片段同拍时，不交付该片段、不产生该下载的done；已经在更早采样沿交付的字节不回滚。这里不要求调用方额外保证命令互斥。

`rst_ni` 是 DDR 控制器及仲裁返回账本共同复位的边界，复位后 EMPTY、ID=0。不得用它替代 source-only 取消：后者必须走 soft_reset并排空。若控制器永远不返回已接受读，后端已报告 ERROR/取消终态但不开放 clear/create，恢复需要共同复位控制器/账本；不能用超时清零读在途位冒充排空。

## 错误与期限

错误码1=FIFO overflow，2=序号缺口，3=epoch/rate不符，4=source不就绪/显式错误/停帧，5=native命令接受超预算，6=读返回超预算，7=无读账本的返回，8=坏描述符，9=显式启用的transport fault。失败不生成补零、不重复旧样本、不拖停音频。SOURCE_GAP_CYCLES、DDR_BUDGET_CYCLES 是 UI 时钟周期，正式候选必须按实际频率及仲裁上界配置；默认100MHz下分别4 ms和100 µs。它们是失败门限，不能当作已证明的服务保证。

命令／返回等待和 FIFO峰值可观测；等待计数在失败后的实际排空期间仍计时，32-bit饱和。存储 generation 只用来隔离返回，并非另一份业务对象身份或公共参数 revision。

## DDR 接口与真实接入口

唯一地址权威是 `rtl/ddr_address_map.vh`：已记录现有 Basic Pitch bulk 301..304 MiB granules，并为录音独占预留 `0x30500000..0x305fffff`。本阶段只用首64 KiB，native app base=`0x0c140000`，BL8每拍32 B，app address每拍加8；不借用 Delay、TF或NN区域。

`ddr_valid_o && ddr_ready_i` 必须表示 **native命令及写数据已实际受理**。DDR数据可见性依赖控制器保证同一通道先写后读顺序；本模块没有虚构写返回。正式物理验证仍须核对该保证。ready不允许直接接 `basic_pitch_ddr_client_queues` 的本地槽接受信号；后者还可能滞留在槽、registered grant和command buffer中。

实际已选链为 `rtl/timing/basic_pitch_ddr_client_queues → basic_pitch_ddr_arbiter_pipeline`，display已经占owner7，不能照旧 `gw138k_ddr_arbiter` 复用owner0的映射分配7。正式新增录音client需要独立owner8/4-bit tags、同提交身份的native接受通知，以及默认路径逐拍等价检查。本阶段不改复杂仲裁器、profile或top。

v1/v2的历史竞争fixture借用music口并替代NN，其证据不能代表owner8。当前v3 fixture显式启用未选择的 `workstation_recording_ddr_client_queues/core`，经native bridge把recording接owner8，music/NN仍在owner5，与scan/audio/display/delay/CPU/writer流量同时竞争。三层ACK、4-bit owner返回、mask和默认兼容见[新组件契约](../memory/RECORDING_DDR_NATIVE_CONTRACT.md)。原timing/music文件不改，当前生产profile也未选择新组件。这里的NN是有界client流量模型，**不能证明完整CNN算法并发、生产owner8／最终PCM已接入或任意竞争流量都不饥饿**；正式新增client仍须重新证明服务期限。

## 下载引用与预取

一次仅持有一个引用。`reference_acquire_i && reference_ready_o` 校验对象ID，返回 granted或error；成功后 clear受阻。`download_i && download_ready_o` 提交字节offset/length，必须非空且完全处于 `frames*4` 内。任意非对齐offset和结尾均允许；只读完整对齐BL8，通过skip/count向消费者给出连续字节。

`download_valid_o && download_ready_i` 交付一个最多32-byte的片段。只使用data最低 `download_bytes_o` 字节，其余位没有有效性承诺；last只在请求范围最后一个片段为1。两拍预取和最多一个已接受读限定片内占用，慢下载只暂停新读，不改变采样节拍、对象数据或元数据。最后一个片段接受后done单周期。

reference_release立即关闭下载输出／新读，丢本地预取，等待已发布命令及返回排空后released，才放开clear。取消、soft_reset、超时亦关闭引用并排空；旧读返回不得进入新对象、续传或后续预取。协议CRC、下载任务ID、断点／ACK和旧客户端格式协商继续属于原业务owner，本阶段均未迁移。
