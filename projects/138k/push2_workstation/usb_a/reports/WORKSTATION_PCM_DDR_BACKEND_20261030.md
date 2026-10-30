# R00：有界 PCM DDR 后端首阶段（2026-10-30）

本检查点实现默认未选择的 `workstation_pcm_ddr_backend`：owner 描述符 → 无背压 PCM16 FIFO → 对齐 BL8写入 → 不可变封存前缀 → 持引用的按需下载预取。首阶段容量与现有64 KiB后备一致。**没有将旧 BLE PCM RAM 替换进完整工作站，没有新增实际 owner8，也没有完成 R00/R01/R02 或任何硬件验收。** 本轮不改变曲谱/CNN、profile、top、BLE wire或Android；不把内部44.1 kHz描述符当作旧格式1的新能力。

## 盘点与地址登记

任务依据为 `projects/138k/task.md` 的 R00/R02 和2.1节，运行边界见[模块契约](../rtl/audio/PCM_DDR_BACKEND_CONTRACT.md)。现有独立后备在 `projects/25k/example/RTL8723DS_PROTOCOL/rtl/ble_recording.v` 的 `live_capture.pcm_memory`，138K选定装配将其限制为16,384×32-bit=64 KiB。历史[2026-10-23物理盘点](BSRAM_NATIVE_DETAIL_20261023.md)中该对象占32块BSRAM；它是 dated B6 物理记录，不能直接套到本轮候选。

[DDR预算](WORKSTATION_DDR_BUDGET_20261030.md)已明确实际使用 `rtl/timing/basic_pitch_ddr_client_queues → basic_pitch_ddr_arbiter_pipeline`，display占owner7，TF为4、music为5、delay为6。旧 `gw138k_ddr_arbiter` 运行期复用owner0的映射不适用。原实际仲裁器、SDP、地址guard、Basic Pitch子图均逐字节匹配已push的参考提交 `728eac7a9888ef617dec0c05a57a8ea24f3ec521`，本轮不改这些已选输入。

`ddr_address_map.vh` 仍是唯一父分配权威。本轮只新增以下登记，原有每个宏值均由runner与该参考提交核对：

| 区域 | 物理字节范围 | 用途 |
| --- | --- | --- |
| 既有Basic Pitch bulk history | `30100000..304fffff` | note、onset、analysis、backpointer各1 MiB；与实际子图四个base和last核对 |
| 未选择的录音granule | `30500000..305fffff` | 独占1 MiB预留，不挪用delay/TF/NN |
| 首阶段实际使用前缀 | `30500000..3050ffff` | 最多16,384 stereo PCM16帧，64 KiB |

native app base=`0x0c140000`，app地址为32-bit word单位，BL8起点对齐8 words，每拍32 B。搜索当前模型、音频、波表及配置未发现305 granule既有使用；不是把未看见的301..304空间当空闲。分配初值、边界、对齐和范围有elaboration检查及重叠负例。新增宏不选择客户端，不扩展已接受runtime能力；后续若将新map输入纳入prepare，来源哈希会改变，必须新候选身份，不能复用当前物理候选。

## 实现与生命周期

新模块所有端口都在持续运行的DDR UI域。owner一次提交并锁定64-bit对象ID、实际rate、epoch、首帧序号和帧上限；后台不生成另一套业务ID或公共采样率真值。PCM为 `{right[15:0],left[15:0]}`，小端保存。采样没有ready，序号/epoch/rate/源故障/停帧/FIFO满均进入显式错误，不能通过暂停采样补救。

默认实时缓存是一个512×32-bit同步SDP FIFO。8帧打包成256-bit写；不足8帧的尾部用active-low byte mask保留DDR原字节。seal同拍PCM不计入，满容量最后一帧计入后自动seal。只有FIFO/pack空、已发布命令和读均排空、`committed_frames==frames`才进入READY。READY不再接收实时PCM，也不因后来系统rate/输入字段变化改写已封存对象。

`ddr_ready_i` 的契约是native命令和写数据真实受理，不能直接接本地client-slot ready。测试的控制器模型保证同一native通道先写后读可见；实际控制器的顺序/可见性仍需物理接入验证，没有伪造写完成返回。

取消、soft reset和错误先关闭采样/新读，丢弃未发布的局部内容；已发布命令保持valid和payload稳定至实际接受，已接受读必须等返回后丢弃。读超预算会报告ERROR，但不会清零在途位后让clear/复用越过旧返回。若返回永久丢失，需要DDR控制器/仲裁账本共同复位恢复；本阶段没有用超时冒充成功排空。`rst_ni`只用于这个共同复位边界，source-only取消走soft_reset终态。

下载一次持一个对象引用，ID不符拒绝；引用未释放时clear不接受。按需读取对齐BL8，经两拍预取给出任意字节offset/length的连续片段，消费者只使用最低 `download_bytes` 个字节。慢消费者不修改对象、不反压采样。release关闭新下载并丢本地预取，仍等已发布命令/返回排空后才放开引用。协议CRC、任务ID、续传/ACK和格式协商继续留给原业务owner。

## 来源、验证与负控

```text
identity: native-pcm-ddr-backend-v1-66ecd8645a54c7af
source_set_sha256: 66ecd8645a54c7af44106388256cf911e3dfddc5f52cfa1543b570f8e179dd34
```

完整源码/契约/fixture/runner/原实际仲裁输入哈希、配置、命令和日志见 [JSON证据](workstation_task_20261030/pcm_ddr_backend.json)。代码不是从私有generated staging生成；原实际依赖由`git show`固定提交核对，仿真输出、临时突变和编译文件留在checkout外cache。

17项全部符合预期，包括10组正向配置及7个行为负例；另有严格Verilator lint零warning和当前来源边界10项测试通过。正向矩阵合计46次封存前缀核验、22个明确失败、8次取消/soft reset，以及140,984个下载字节的非零左右声道参考对照。

- 两种rate各测试519帧的真实100 MHz UI时间基准：48 kHz周期分数累加，44.1 kHz也独立按其真实分数周期产生，不只改标签。序号从`fffffff0`跨回绕；输入描述符在接受后改变，已锁定metadata保持。两种rate均直接连控制器和接实际timing queues/core竞争测试。
- 两种rate均做完整64 KiB容量和下载：各16,384帧、2,048次写和2,048次读，按字节逐一比较。此容量压力用每4 UI拍一帧加速，不把它描述成0.341/0.372秒的实物录音。另逐一覆盖尾帧数1..7，检查未使能的DDR字节仍为canary；seal同拍的下一PCM帧被排除。
- 每种rate覆盖512-frame实际FIFO overflow、序号缺口、epoch/rate不符、source错误/不就绪/停帧、native命令超预算、读返回超预算、坏描述符。故障门限使用显式测试配置，不将其当作测得的板卡服务保证。
- 每种rate覆盖有pending写时取消/soft reset、读已接受但返回延迟时取消/soft reset、引用release后排空、共同复位后旧返回拒绝、新对象和下载重启。输出片段在消费者背压时保持稳定，READY前缀不受后来实时PCM影响。

竞争边界是**未修改的实际queues/core，加仅测试用的提交观察适配器借music口**；该fixture替代NN client，未分配新的生产owner。scan/audio/display/delay/CPU/writer持续周期竞争和native周期停顿均按实际app_en记数，不能把本地slot接受当成已服务。两组519帧竞争中最大native命令等待22 UI拍、返回等待11拍；64 KiB竞争中分别为12/11拍。该流量模式下通过不证明任意scan洪泛或NN并发下都不会饥饿，正式owner8接入仍需D01预算。

| 负例 | 实际检出点 |
| --- | --- |
| 忽略最后写受理提前READY | seal故意stall时拒绝提前发布 |
| 取消尾mask | canary字节被覆盖 |
| clear绕过引用 | 清除引用中的对象被拒绝 |
| 取消时忘记已接受读 | 旧返回丢弃/排空断言失败 |
| native app地址每拍错加1 | 非BL8对齐拒绝 |
| 把实际queues本地ready接后端 | 同样检出seal早于native接受 |
| 新分配与304 granule重叠 | allocation检查拒绝 |

复现（output须不存在）：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_pcm_ddr_backend.py \
  --output /tmp/workstation_pcm_ddr_backend_fresh
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

## 缓存清单与剩余接入

新增默认数据缓存清单为：2 KiB同步capture FIFO、32 B pack、32 B已发布命令、64 B下载预取，以及4 B FIFO同地址转发；描述符和控制计数另计。这里只列原始位容量，不推算新的物理BSRAM或净节省。旧64 KiB RAM仍由当前完整装配使用，本阶段未删除，也没有释放其历史32块。32-bit SDP实际映射、预取/byte-skip移位的逻辑成本和时序、净资源变化都须在替换旧后备后的同配置综合/P&R核对。

下一阶段还需：显式新增独立owner8与4-bit返回tag及native接受通知；默认仲裁逐拍等价和全客户端竞争；最终PCM CDC/tap接入；单一录音业务owner选择后端、封存CRC/身份/下载引用及旧RAM退役；BLE/Android真实格式协商；时钟切换/断连策略及两种rate非静音实录；同候选P&R和板测。本阶段未运行EDA/JTAG，没有SRAM/Flash操作，不据模块测试勾选R00、R01或长录音任务。

回滚撤销新增backend、契约、fixture/runner、报告/JSON及map新增登记即可；原复杂仲裁器、协议、profile和部署状态没有迁移。
