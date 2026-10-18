# 主会话模式 D 接入合同

这里给出接入 `rtl/audio/gw138k_event_workstation.sv`、workstation DDR arbiter 与 Push 显示的具体位置。该文件已有工作区修改，本交付不替换它。不得将已有 `tf_workstation_audio_bridge` 的文件 PCM takeover mux 接入模式 D。

## 音频／事件端口

`sampler_mode_d` 放在现有 `unified_oscillator_engine` 实例旁，全部控制使用 `clk_i=76.8 MHz`、`rst_ni`。下表列出接口组；完整位宽以 module 声明与 `sampler_pkg` 为 ABI。

| 端口组 | 接线 |
|---|---|
| clk/rst_n | clk_i/rst_ni |
| sample_tick | 精确48kHz的 sample_ce_i；每1600 clocks一次 |
| enable | 已提交的 `current_mode==2'd3`，切换 pending 期间仍保持旧模式 |
| event_valid/ready/data | 注册后的18-bit `{kind,a,b}`，D时用 sampler_ready 握手 |
| restart | mode commit、TF session restart、强PANIC；不能简单重复拉高每帧 |
| panic | `panic_accept`（CC120）硬清理 |
| pad_write/index/config | 主控制器写64个pad_t；原子写，不逐字段在演奏中拼接 |
| descriptor_slot/descriptor | 接 sampler_storage 的 query_slot/descriptor；纯组合查询 |
| referenced | 接 pool 的 referenced；占用中的采样禁止free或替换 |
| seq_start/stop/record_enable | 控制事件译码到单周期脉冲／状态，离开D先stop，再等待voice尾音 |
| bpm/swing | BPM30..300；swing0..50%，无效值显示E_BOUNDS |
| edit_*、chain_* | 原子控制写；live_event已在模块内从Push事件接入 |
| pattern/step/grid/group_select | 屏幕、灯光状态；运行pattern切换在bar边界 |
| storage_* | sampler_storage唯一写客户端；不与voice read争用业务数据线 |
| req_*/rsp_* | 整包CDC到DDR域，外层arbiter回传原tag，read与write都必须完成确认 |
| pcm_valid/l/r | PCM16扩成Q1.31，进入统一混音与P10效果，不直接抢DAC |
| delay_send | CC112瞬时绑定到现有P10 delay的wet/send控制 |
| active_mask/count | D状态／模式提交判断／屏幕，不复用legacy allocated数组 |
| deadline_misses,max_latency,ddr_beats,seq_jitter_samples | 状态和数值证据计数器，不能tie-off |
| voice_error/ddr_error/seq_error | 显式UI错误，必要时CC120；不能只看audio nonzero |

关闭不用的编辑／链／回录输入时，`*_valid`、start/stop、record_enable、metronome_enable固定0；地址／数值输入固定0（bpm仍给120、swing给0），`pad_config='0`；未连接输出用具名空连接或命名unused wire。测试中全部未使用输入已显式赋值。

## 模式提交语义补丁

当前文件在 requested_mode/mode_cycle_base 处已有2-bit模式；宽度足以表示D，但旧 `unified_oscillator_engine` 只认识A/B/C，不能把3直接写入它。

1. 在 workstation 加 `logic [1:0] committed_mode`，`mode_o=committed_mode`。旧core的current_mode单独改名 `legacy_current_mode`。CC80把`b<3`改为`b<4`；CC90循环边界2改为3。初始化保持C=2。
2. `mode_pending` 仍只记录请求，不立即改变当前音频路由。请求时撤销sequencer transport，给所有现存voice发graceful release（D用CC123可覆盖one-shot；A/B/C沿用现有逐voice release/sustain清理）。停止新的note-on并清held/sustain/deferred bookkeeping；NOTE_OFF/PANIC仍处理。允许新模式note-on必须等commit，不能排队无限延迟旧键。
3. 提交条件增加 `sampler_active_count==0`、legacy active_count==0、vec_active==0，且旧帧无pending、无held joined结果、effects可接下一帧。与原先`!pending && !sample_ce_i`边界结合。不要以只有held_notes==0代替voice尾音消失。
4. A/B/C目标继续走旧core `mode_set_valid/ready`。D目标无需向旧core发非法3，而在全部尾音结束且帧边界空闲时更新committed_mode=3。D离开时先stop+CC123，等D active_count=0，再对legacy提交A/B/C。每次提交给sampler一次restart清除缓存／队列和epoch。
5. mode_pending只在真正commit时清，不以“请求已发”清；保持同尾音等待期内新的requested_mode覆盖旧请求。PANIC可以立即归零各引擎／P10历史并完成待切模式。

原 `mode_valid` 所在块、`dispatch` always_comb、CC80/CC90 switch 三处是patch点。原 `full` 与 `allocated` 只描述legacy；D不要让legacyfull提前吞掉采样事件。当前Cue注册事件已经18-bit，D可共用该边界，但主会话需决定cue与sampler pattern同时运行的控制优先级，不能双重派发同事件。

## 同一采样帧派发／混音

音序器在48kHz tick形成32-bit sample_time；四轨事件批（最多4 off + 4 on）在同步RAM读取后形成。`sampler_mode_d`保留16 clocks派发窗口，随后给voice一个voice_tick。这样当前timestamp的note-on在本帧voice扫描前应用，避免“时间戳正确但声音晚一帧”。端到端TB对此作了独立断言。

现文件 `held_synth/held_vec_l/r`、`synth_joined/vec_joined`与`effects_valid`合流处应加入sampler结果join：

```systemverilog
if (sampler_pcm_valid) begin
    held_sampler_l <= $signed({sampler_pcm_l,16'd0});
    held_sampler_r <= $signed({sampler_pcm_r,16'd0});
    sampler_joined <= 1'b1;
end
wire effects_valid = committed_mode==2'd3 ? sampler_joined : (synth_joined && vec_joined);
```

给 `stereo_effects` 的vector左右或独立新增stereo synth输入接D结果；D时legacy mono synth与外部PCM gain必须0，sampler gain与现有volume/expression串联。不要接 `pcm_left_i/right_i` 的TF媒体信号。FX有效后清sampler_joined，与原join一致，并把它加入core_ce/backpressure和commit条件。D对PANIC的清理同时清join、held_sampler、effect history。

D的BitCrush/Drive在 `sampler_mode_d` 内；delay仍进已有P10 delay。CC110/111/112原值0释放瞬时效果，非零深度；不要把CC112当作独立新delay历史。P10的CC83等排队效果逻辑不应吃掉这三项瞬时CC。

## DDR仲裁／CDC

地址唯一来源 `rtl/ddr_address_map.vh`。默认池为byte `0x09800000..0x0fffffff`，104个1MiB granule。NN／bulk／TF ring／UI不占用。pool reserve到commit之前 valid=0，guard逐beat检查32byte对齐、窗口含整个BL8、池上下界，并使用33-bit加法防32-bit回绕。

`req_addr`为native word（byte >>2），低3位必须0。外层FIFO tag需要扩展client类别SAMPLER，并保存本模块16-bit子tag；子tag=`{client[1:0],epoch[7:0],serial[5:0]}`，client0=voice、client1=storage。本模块仅一个outstanding，其内部round-robin保证storage不饿死。

restart时未发出的请求取消；已发出的读/写仍占busy，等待旧tag完成后只计stale不交给新客户端。**不能清外层tag FIFO或把旧response误当新请求**。257次restart的测试证明epoch回绕期间仍先drain，serial回绕同理由单outstanding隔离。若DDR不返回，E_TIMEOUT为粘性fault且不凭超时重用可能尚在写入的地址，主控制器显示错误并复位整条DDR链。

把请求完整的 `{write,addr,data,tag}` 放异步command FIFO；read response和write completion完整返回。Gowin写口`app_rdy && app_wdf_rdy`同时握手才算接受，不可只确认command。外层必须让sampler在视频scanout、TF、CPU、display持续争用下达到服务合同；原视频strict priority不能直接保证这一点。要么增加有界service slot/credit，要么上板实测并按voice帧预算调整允许的导入并发。默认客户端检查 `MAX_WAIT=18`（音频clocks，含仲裁、CDC与response）；超限有fault。仿真以周期性request stall与9..13 clocks响应、持续竞争客户测得最坏17 clocks。**这不是现有板上arbiter已经有17clock延迟的证据。**

带宽上界：每voice每帧最多2个32byte插值读，因此16voice为 `16*2*32*48000=49,152,000 bytes/s`。canonical导入按TF SPI实速写；回录48k mono仅96,000 bytes/s（末beat padding除外）。总容量与带宽须同时加上视频/CPU等现存负载。输出仅DMA beat为256bit；采样位置／计数／地址仍32bit，Q16.16 phase为48bit用于避免长采样整数部分回绕。

## TF导入／manifest控制

实例化 `sampler_storage`；连接它的query与referenced到mode_d，write与response到storage_*。控制元数据在load_start/capture_start前就绪并保持到busy撤销。slot与owner在模块里锁存；格式/时长/CRC/声明与limit需在事务期间稳定。

TF的 `sampler_tf_source` 实例化vendor FAT reader，输出只接storage in_valid/in_byte/in_last/in_ready。source overflow转换为 `E_OVERFLOW`送source_error；卡／文件错误从card_status/filesystem_status/file_found映射并显示，控制器需有找文件超时。先reserve并使import就绪，再enable source，避免吞掉header。`FILE_NAME_LEN`须与8.3字符串长度一致（例S00.WAV为7，SAMPLE.WAV为10）。session restart同时作用source/storage/mode_d DDR epoch。任一错误使provisional descriptor abort，不给voice可读valid；不支持格式与CRC不符禁止降级。

工具manifest地址只用于空池按序首次导入校对。每次done后查询descriptor，核对owner/base/capacity/frames/gain/crc，更新JSON。duration=frames/48000、format固定PCM16_MONO_48000，granularity和review字段沿用审核声明。硬件不解析JSON：主控制器须把这些字段送入事务端口并导出查询结果。参赛部署需保留真实manifest，不把示例声明当作对未知素材的批准。

Resample只连接经volume/FX的实时乐器母线，主控制器要证明音序器停止、active_voices=1并冻结新note-on/媒体/click路由，approved_single_note在capture期间不得撤回后又绕过检查。范围固定为一个已审核单音/单打击点，禁止录pattern。没有麦克风／line-in/ADC接口。

## UI与切片接入

在 `push2_surface_pixels.sv` 原frame_start快照路径旁实例化sampler_grid；`dirty && mode_o==3`汇入P26“状态变更→新帧”请求。`ink && mode_o==3`时覆盖像素rgb，其余走旧panel。dirty在frame_start后清；不要tick逐像素改状态。grid为track0..3每行16bit、step为当前游标、底条为pattern号、组选中行为蓝色边。灯光也按同一主pad/组选pattern映射；主会话将状态接入已有LED队列，不新增USB传输器。

切片配置先用sampler_slice查询均分或manual marker，valid为1才原子写对应pad_config trim。每个采样的手动marker需要主控制器保存并在选择时装载；此小模块只保留当前编辑采样的16个marker。reverse是pad_config.reverse；normalize是import元数据操作，不对已在读的样本原地改PCM。

## 验证范围

本目录TB覆盖voice全键盘／root极端、逐样本八度与半音对照、周期loop seam、reverse、ADSR/one-shot/gated、16voice竞争DDR；pool guard/owner/commit/free/cursor wrap；wrong tag/stale/257次restart/饥饿报错；swing样本精度/BPM余数/运行变速/live gate/chain/panic；WAV packing/CRC/长度/违规素材；完整storage与mode-D事件到音频；Push/FX/slice/frame snapshot。`evidence.json`给固定输入hash与数字、原CPU和P23回归位置、独立Gowin综合结果。

没有板上下载、没有ADC，没有整段媒体播放接线。主会话尚须完成上述顶层接线、外层tag/CDC、实际DDR仲裁服务测试、整机资源与76.8MHz P&R后，才能宣称板上模式D交付完成。

## 本次固定测量（2026-10-01）

| 项目 | 仿真或综合结果 | 条件 |
|---|---:|---|
| 并发 voice | 16 | 第17声部E_CAPACITY显式拒绝 |
| 最大采样读 | 32 BL8/frame | 所有voice同时跨beat |
| 读带宽上界 | 49.152 MB/s | 32×32×48000，十进制MB |
| voice最慢帧 | 1405 audio clocks / 18.2943 µs | 16voice高音、短循环迭代wrap、竞争客户端 |
| 发给DDR后完成 | 17 audio clocks / 0.22135 µs | 含周期stall与模型response，非板测 |
| voice等待仲裁grant | 17 audio clocks / 0.22135 µs | 持续请求竞争客户端 |
| voice读请求到收到response | 35 audio clocks / 0.45573 µs | 包括内部grant等待 |
| deadline miss | 0 | 帧1600clocks；D预派发16clocks+PCM注册仍须纳入整机 |
| swing偏移 | 1500 samples | 120BPM、25% swing |
| 事件jitter | 0 samples = 0 beats | 120/137/180/300BPM；集成端到端起音同帧 |
| sampler_mode_d综合 | 23,675 logic / 16,904 regs / 9 BSRAM | Gowin 1.9.12.03，估算Fmax81.269MHz |
| sampler_storage综合 | 11,128 logic / 10,080 regs / 0 BSRAM | Gowin 1.9.12.03，估算Fmax100.091MHz |

这里的最大值属于已执行的多样化激励模型。`MAX_WAIT`只报告单事务超时，不能单凭18clock配置推导外层全部请求同时达到最坏延迟时仍有1600clock帧界。顶层必须用真实arbiter、refresh、视频/CPU/TF持续负载和完整CDC复跑上述极端声部测试，测量每帧完成界与公平性。独立综合的Fmax不是布局布线结果；source FIFO/vendor FAT与顶层CDC资源还需加上，9块BSRAM只描述mode_d核心。
