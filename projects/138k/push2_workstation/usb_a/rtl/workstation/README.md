# 工作站原生装配边界

138K Host 与 25K Device 的无 HDMI／DDR 独立探针见 `USB2_HOST_PROBE.md`；直连电脑的 Device 回环探针见 `USB2_DEVICE_PROBE.md`。两者的 USB 角色不同，不自动切换工作站生产配置。

运行时双率的显式原生组合由 `workstation_runtime_audio.sv` 和 `workstation_runtime_controlled.sv` 提供；后者保留 CPU/APB、UART、USB 生命周期仲裁，并将真实物理帧送往 FFT／96-bit 录音／256-cue 乐谱及带上下文的显示观察。唯一事件／会话／公共参数 owner、媒体策略和时钟域见[运行时控制组合契约](RUNTIME_CONTROLLED.md)。完整工作站 profile revision 5 通过 `workstation_profile_runtime.sv` 显式选用这些组件及同一宏作用域内的 HDMI provider；accepted、pinned 和未指定 profile 的新板入口继续使用各自的来源。来源实现及离线验证不提升部署验收。

自定义底板 a23 物理实验另见 `../../reports/WORKSTATION_PHYSICAL_20261025.md`：原生 USB 的复位／参考故障同步位于 `rtl/usb2/` 所属模块，紧急引脚保护不反馈到同步 UTMI 数据通路；已有只读模型 Flash 加载与 UART 恢复通过 SOM 共享引脚 guard 接入。PLL／算术／声部控制的四份锁定输入适配有哈希、唯一锚点和迁回原生源的退出条件，原生矢量力度计算使用无延迟的精确位映射。它不切换任何已接受生产 profile；生成位流、时序／CDC／PLL 通过和 SRAM／Flash 部署仍是不同阶段。

这里是 `build.py --resource-rework --resource-timing` 开发候选的第一方整机源码入口，不是完整工程副本。锁定基线继续提供 CPU/IP、固件 ROM、约束和尚未迁出的组件；实际输入由生成工程的 `workstation_inputs.json` 和 `workstation_composition.json` 绑定。

新板任务的显式来源检查点为 `--prepare-custom-board --workstation-profile custom138k-workstation-v1`；revision 5 保留维护 AE350 固件、扫描窗口后台写 admission、双率原生音频、TF 原子帧服务和显示 minor1，显式启用先封存录音／停止 TF 再切换的媒体策略。固定配置、逐文件来源及未完成 feature matrix 见[完整工作站 profile](../../boards/custom_138k/WORKSTATION_PROFILE.md)。它复用现有准备路径；支持的源码配置为 48 kHz／44.1 kHz，仍须完成整机综合诊断、物理时序／CDC／PLL 和实板验收。

时钟请求使用独立 APB 页 `0xf8030000`；音频 `0xf8010000`、UI `0xf8020000` 和启动状态 `0xf8000000` 保留。顶层只组合、传递元数据、隔离存储事务并控制就绪，DSP、切换事务、TF 文件及显示发布分别保留所属 owner。首次启动须由[内存守护](../memory/RUNTIME_MEMORY_GUARD_CONTRACT.md)确认实际客户端就绪和时钟进展；之后 DDR／视频关联复位或计算 PLL 资格丢失会永久静音并隔离请求、接受和返回，直到 common reset。`started` 保持，不能以局部故障重置持音、公共参数或 stream epoch。DDR／视频复位尚未解耦。

minor1 显示消费带实际采样率、epoch 和序号的最终物理帧，见[显示组合契约](RUNTIME_DISPLAY.md)。上游观察丢帧单独撤销新图发布的可信资格，直到 common reset；音频不等待显示。TF 仍使用原 DDR 文件中转，其 EOF 尚无有序物理排空成功语义；即时播放去 DDR 属 M03。revision 5 的[媒体准备组合器](../services/MEDIA_PREPARATION_CONTRACT.md)等待受控 REC／score／TF 和 BLE 的真实终态后才允许切换，CPU observer reset 不解除后台 fence。BLE format 1 仍仅接收合法 48 kHz 帧；正常 seal 保留原对象 ID／帧数／CRC，不重标旧对象采样率，不能据此宣告双率录音或整机硬件接受。

accepted full83 和 pinned timing85 保留原来的来源策略与 CNN 保护。它们采用共享事件工作站及控制模块，但不隐式切换为这里的资源候选顶层。历史验收记录和冻结文件不修改。

## 维护入口

| 边界 | 源码 | 责任 |
|---|---|---|
| 板级装配 | `gw138k_push_workstation_top.v` | 时钟复位、引脚、组件连接、CDC 和平台就绪；不再持有 TF/识别播放恢复状态机 |
| 音频域适配 | `gw138k_controlled_adapter.sv` | 串口输入跨域、采样时钟、串行 DAC、采集扩展和状态观察 |
| USB/CPU 适配 | `gw138k_usb_controlled_audio.sv` | 设备/CPU 输入合并、服务寄存器和音频组件连接 |
| 会话控制 | `../control/workstation_session.sv` | 生命周期、旧事件作废、接入默认事件序列、初始化完成屏障 |
| 公共参数 | `../control/workstation_parameters.sv` | 已提交命令的唯一参数应用点；模式请求、音量/表情、音色、效果队列、矢量/TF 控制及状态投影 |
| 实时事件与数据通路 | `../audio/gw138k_event_workstation.sv` | 事件仲裁、音符/延音释放、声部调度、帧汇合、DSP 和 deadline；不再实现公共参数 CC 分支 |
| 播放业务服务 | `../services/workstation_playback_service.sv` | 模型就绪等待、选曲排队、取消、拔卡恢复/超时、TF 与识别的读取控制 |
| 串行帧交接 | `../audio/workstation_frame_delivery.sv` | PANIC/生命周期取消的显式零帧、每采样周期最多交付一次、丢弃已取消帧的迟到响应；普通缺帧与非预期重复继续报错 |
| 最终输出路由 | `../audio/workstation_output_router.sv` | 安全切换串行输出、最终输出观察和固定的 128-bit tap 快照 |

`tools/workstation_composition.py` 只选择和复制明确列出的源码，并验证编译清单与哈希；不生成业务 RTL，也不对这三份装配文件做字符串改写。新增公共行为应先确定所属边界，不把条件分支继续加到顶层。

## 控制与状态契约

- 18-bit 事件格式、现有 CC、MMIO、USB PL 和 BLE 线规不变；没有偷偷加入来源、会话号或 revision 字段。
- 只有事件被接受后，`workstation_parameters` 才更新公共参数。`mode_pending` 表示请求未提交，实际模式仍以声部引擎的 `mode_o` 为准。
- 会话模块拥有事件寄存器和初始化进度；断开/PANIC 优先，旧事件不得穿过重连。初始化必须等待最终模式实际应用，不能把入队成功当完成。
- 参数模块拥有延音开关；音频工作站拥有 held/deferred 音符表、释放游标、声部及实时统计。两者在同一音频时钟边沿提交，保持原先周期语义。
- Push 等适配器的相对旋钮缓存不是权威状态。现有 MMIO/显示投影的位布局保持兼容；尚未扩成新的完整跨设备状态协议。
- `TIMING_OPTIMIZED` 是编译期结构选择。资源时序候选显式启用已验证的调度结构与公共命令提交简化；普通整机保留原调度/提交表达式，不靠运行时推测 profile。公共命令的接受条件为有效事件、非延音释放扫描及可调度，不必再经过音符/逐音表情的 ready 选择器；音符类在参数模块不写公共状态。两种表达式均做完整逐拍对比。
- 引擎响应只有在当前 `frame_inflight` 有效时才进入汇合；PANIC 当拍不启动新渲染。已取消作业的迟到结果不能留下单边 joined，阻塞下一采样。
- 原生串行适配读取工作站已有的 PANIC 静音投影，不另存一套控制真值。尚未交付的取消帧以及 PANIC 静音期间每个周期交付显式零帧，音符恢复后按下一完整帧恢复；正常渲染不增加流水延迟。串行节拍保持 1,600 音频时钟，非取消缺帧不自动补零掩盖，非取消重复交付计入已有健康字低 16 位。

## 音频路由与观察点

| 路径 | 效果处理 | 最终输出 | 已有录音扩展 | 最终显示 tap |
|---|---|---|---|---|
| A/B/C 合成 | 合成支路串行效果链 | 合成 DAC | 合成支路输出 | 实际最终串行输出 |
| 实时矢量 | 现有矢量混入路径，模式行为不变 | 优先占用合成 DAC；静音时不回退 TF | 合成支路输出 | 实际最终串行输出 |
| TF 播放 | 仍保持原有独立支路，不声称经过合成效果链 | TF DAC，帧边界切换并等待稳定 | 未接入该录音扩展 | 实际最终串行输出 |

128-bit 快照从高到低依次是 PCM 左右各 16-bit、触发参考 32-bit、声部掩码 32-bit、健康字 32-bit。TF 被选中时参考和声部掩码为零；健康字仍是原合成支路的 serializer/core 计数，不冒充 TF 全链路健康。跨域传输保留在组合根的 `u_final_output_cdc`。

这次归位不强制改变采样率、效果作用范围或录音点。后续 D/BLE 接入必须显式选择 tap、位宽、背压/丢弃和存储归属，不能把“有录音模块”解释为“已经能录所有音源”。

取消补零发生在串行交接点，不向既有 render-complete 录音扩展重复注入采样。其连续录音/取消时长表达仍须按实际录音契约单独集成，不能从最终串行连续性推导录音文件已经连续。

## 构建与验证

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --resource-rework --resource-timing --prepare-only
python3 projects/138k/push2_workstation/usb_a/tools/build_resource_rework.py --timing-fixes --flow all --place-option 2 --route-option 0 --max-fanout 128 --user-code <新的八位十六进制标识>
```

高扇出物理实验可显式加 `--replicate-resources`（统一入口同名选项）；该选项写入实际 Tcl 和构建元数据，默认关闭，不改变时钟或 CDC 例外。不同物理配置分别产生候选和门禁结果，不能复用已有验收身份。

本轮全局复制实验虽改善音频 setup，却引入复制复位节点的 recovery/removal 失败和 FIFO CDC 拓扑失败，未形成可下载候选；该选项仅保留复现用途，不能用来绕过门禁。只有相应复位/CDC 独立证明及整机门禁均闭合后才能进入可用配置，否则后续应退役该实验。`--place-option 0..4` 是另一项显式物理配置（统一入口同名），记录实际算法，不改时钟、同步器或例外。

`--max-fanout <1..10000>`（统一入口同名）是 Gowin 的综合扇出选项，独立于上述 P&R 全局复制；实际 Tcl、元数据和输入哈希均记录其值，未指定时保留工具默认。上面的 place2/route0/max_fanout128、关闭 P&R 全局复制是本轮通过配置；64 的实验虽时序非负，PLL 门禁仍失败。通过候选 `0xC110210A` 的配置、442 项输入及位流身份见[本轮证据](../../reports/architecture_refactor_20261021/verification.json)，不保证不同源码或工具重跑自动通过，更不能复用该编号。实际 setup 余量仅 9 ps，仍须继续改善稳健性。

PNR/all 必须显式给新的 `--user-code`，不再默认套用历史编号。工具流成功但时序、CDC 或 PLL 门禁失败时入口返回非零；`resource_all_result.json` 的工具成功与 `resource_readiness.json` 的离线可用性仍分别记录。离线通过也不会自动下载或写 Flash。

`--resource-rework` 与 `--current-workstation`／`--cnn-timing85` 混用会直接报错；不会按分支顺序忽略其中一个来源策略。

验证入口：

- `sim/architecture/test_workstation_composition.py`：源码选择、重复/禁用输入、缺源及漂移拒绝。
- `sim/architecture/run.py --project <新Prj1> --reference <重整前Prj1> --output <新目录>`：播放服务对照原顶层状态机，以及输出引脚/PCM/tap 的逐周期对比。
- `sim/architecture/run_serial_delivery.py --project <新Prj1> --output <新目录>`：真实引擎/效果/PT8211，A/B/C 与矢量各扫描 CC PANIC/生命周期的 1,600 相位，验证真实发声/清音符，并用不补零的独立串行端作负对照；不能只测空闲期 PANIC。
- `sim/run_workstation_attach.py --baseline <重整前Prj1> --event-reference <原事件工作站> --timing-optimized --out <新目录>`：真实 USB/CPU 仲裁、控制参数、接入/取消、PANIC、held/deferred 与 PCM 对比。
- 综合、P&R、时序/CDC/PLL 门禁独立执行。离线通过后仍需设备身份读回、明确授权的 SRAM 下载和实体检查；不能把 UART 内核快照当作模拟音频或 HDMI 验收。
- 授权后的核心 smoke 可用 `tools/capture_scope_smoke.py --seconds 5 --exercise-controls --exercise-polyphony --exercise-live --output <新JSON>`，此前须确认目标身份与 DDR 模型就绪。它不下载位流；只做带 CRC 的状态与离散快照，不保存音频流。快照须匹配新 token/完成计数/采样序号，并等待另一条新鲜完成记录后取数，避免把第一次完成状态与尚未稳定的 MMIO 数据混为一谈。

## 仍需继续收敛

这里完成的是开发候选的组合根与主要控制边界，不宣称所有历史构建器已退役。底层仍有带哈希/锚点约束的时序与 IP 适配；公共显示位域、Push 专有交互和 Android `Workstation` 协调职责仍可继续拆分。D 模式、138K 实际音频 BLE 录音及完整多端状态同步没有因这次重整而自动完成。

## 新板 USB2 组件

显式 `workstation-input` 接入原输入 owner；[workstation-audio](USB2_AUDIO.md) 再复用本目录会话／参数／DSP／串行帧交接和原 delay DMA。它们是独立组件验证入口，不是这里完整 resource-timing 配置的新来源，也不自动选择新板 IO 或替换部署。

板级快速迭代选 `--usb2-component workstation-hotplug`，见[高速热插拔独立诊断](USB2_HOTPLUG_DIAGNOSTIC.md)。该配置复用同一生产固件和输入 owner，提供新板时钟／ULPI 引脚及 UART 状态快照；不编入 DSP、DDR、CNN 或 HDMI，USB 与显示各自稳定后再回归完整工作站。

电脑直接连接 138K、验证其 USB 设备侧 480 Mbit/s 收发时，使用[独立设备回环探针](USB2_DEVICE_PROBE.md)，不要混用上述 Host 配置或 25K 设备身份。

## 显式新板装配

原生工程只启用一个 `constraints/custom_138k.cst`，由位置、音频、蓝牙、HDMI 和原生外设五份可审查约束合并；Gowin 打开工程时会在多份 CST 中选择一份，不能依赖多文件同时生效。`display.cst` 保留参考核心板的 LVCMOS33D 差分标准，与同 Bank 的 3.3 V HPD／CEC 一致。`peripherals.json` 锁定远端已核对的音频排线、振荡器和 LCD 依据，来源漂移必须失败，不修改独立 pinout-only 配置的历史接线假设。

`build.py --prepare-custom-board` 是独立的新板源码组合入口，仅准备工程并允许离线综合，不改变 accepted、timing85 或原 resource-timing 配置。它从锁定的资源时序父配置重建依赖，逐项禁用旧 USB FS CPU／Host、旧装配顶层、旧 DVI 输出 provider 和旧板约束，改选原生 USB2 输入及新板位置规划。禁用的历史文件保留原字节，替换关系与完整编译闭包写入 `integration_inputs.json`。

新板的 DDR 自检由 `../memory/workstation_ddr_bist.v` 提供；锁定父输入 `src/memory/ddr3_bist.v` 保留但禁止编译。读请求被接受时保存对应的完整预期数据，等待响应期间保持，不再在响应比较／失败寄存器路径重新展开当前地址的模式计算；响应按 32 个字节独立比较后归约，避免映射为一条 256-bit ALU 比较链。接口、两遍测试模式、请求／响应节拍、超时与饱和错误计数不变。冻结参考逐拍比较覆盖背压、逐 lane 损坏、计数饱和、命令／响应超时及在途复位，形式归纳和实际综合网表的失败寄存器输入锥检查分别约束功能与映射结构；实际物理改善仍须用各候选的路由后时序证明。

`workstation_custom_138k_top.sv` 只为共享的 `gw138k_push_workstation_top.v` 选择 `WORKSTATION_CUSTOM_138K` 板级分支；不复制 DSP、DDR、TF、识别、播放或显示工作站。未定义该宏时的预处理 token 身份有独立回归保护。新板分支继续只有一个公共参数应用点和最终输出路由，不把 USB 服务 ACK 当成音频命令已经应用。

原生 USB 输入显式选择 `FEEDBACK_AUDIO_DOMAIN=1`，将 `u_managed` 的音频域原始完整反馈接到 owner 自身的快照 CDC。UART 遥测仍独立运行，但其较慢的缓存不能再次作为输入初始化的“新反馈”：两级缓存可能让旧 PANIC epoch 在新 Note On 之后抵达并清除本地 pad latch，随后丢弃 Note Off。默认参考域组件接口和旧板分支不随之改变；综合审计核对该 mailbox 的实际源时钟为音频域、目标为 USB CPU 域，不以此替代物理 CDC／时序验收。

新板 DVI provider 在 OSER10 的十位并行输入处补偿四对反相，OSER10.Q 直接连 ELVDS_OBUF，不能在专用串行输出路径插入 LUT 反相。AUDIO 采用远端 AK4493 链路的反序排线：主板 `FPC2.n` → 功放 `FPC1.(25-n)`；仅原生装配按网表推导并交叉核对远端约束，不能沿用同序排线的位置。`workstation_fpc_audio` 从最终输出路由的完整 PCM 对取数，输出 48 kHz、每声道 32-bit slot 的 I2S，16-bit PCM 左对齐补零。K18 的 12.288 MHz 振荡器直接驱动串行工作域和 MCLK（256fs），分频产生 3.072 MHz BCK 和 48 kHz LRCK；不把低于器件 PFD 下限的参考送入 PLL。50 MHz 域监视参考时钟心跳，停钟后 2 µs 内静音／复位，恢复后重新执行启动序列：PDN 低 4 帧，再静音至启动第 1028 帧。SSLOW／SD／SLOW 固定为零；采用远端 AK4493 的并行引脚控制模式，不虚构 SPI 音量寄存器。

主音量仍由 `workstation_parameters` 唯一提交：Push 的 CC71／CC79 相对旋钮和 25K 编码器 1 的绝对 CC7 都进入既有控制链。原生装配显式选择 `EXTERNAL_MASTER_VOLUME=1`，合成器／矢量效果链仅保留 CC11 表情增益，CC7 在效果及 TF／合成音源选择之后、最终 I2S 和 BLE 取样之前只乘一次。其它构建默认参数为 0，保留原行为。音量和完整立体声对原子跨域；每帧最多变化 256 个 Q1.15 单位，零音量立即归零并拉起 SMUTE。Push 旋钮缓存消费主音量状态，不能将表情乘积反馈为新的主音量。

其它 TF 采样率以最新完整立体声对保持／抽取到 48 kHz，不等待或反压原音频调度；连续超过 16 帧没有新观察值后输出零并静音，不无限重放旧音频。它不是高质量带限重采样器。`custom_138k.audio.cst` 单独提供 AUDIO 的 3.3 V IO 标准；实际 Bank 电压、排线和出声仍需板测，`amp_fpga_det` 保持输入，不驱动其模拟检测网络。原 PT8211 串行链留在内部供原输出路由及观察使用；CEC 高阻释放。

新板蓝牙使用 `workstation_bluetooth`：vendor 传输输入选择远端新导入的 `example/RTL8723DS/vendor/rtl8723ds_ble`，并验证与 25K 业务项目 vendor 一致；业务层继续使用 `projects/25k/example/RTL8723DS_PROTOCOL/` 的 GATT、短录音和 second40 可靠下载，不换成 BTST 诊断服务。广播名称为 `GW138K-MAIN`，沿用原服务 UUID、命令和下载扩展。T14 发送到模块，W12 接收，AA9 驱动 BT_DIS#，AA13 将 Wi-Fi 保持禁用；FPC3 到蓝牙板反序接线，编号依据见 `boards/custom_138k/bluetooth.json`。原版 vendor 字节不修改，业务源码及适配脚本单列输入哈希；不使用本机 generated 或 builds 目录。保留业务初始化 115200 → 921600 baud 策略，不因远端单模块诊断采用 115200 就降级业务协议。

录音从 FPC 串行器的最终 48 kHz 帧取样，包含主音量和静音效果，通过已有保持字 CDC 传递 PCM 和连续帧号；TF 与合成／矢量都可作为当前输出来源，正常音源切换继续记录最终输出及切换静音。独立 RAM 保存最多 16,384 帧（约 0.341 秒），容量满封存，下载读取实际 PCM；录音和 BLE 无法反压采样。断连继续录音，帧号缺口或停钟超过 4 ms 进入 ERROR，拒绝下载并允许清除。REC_START 保持 `format=1, source=0, flags=0`。已有短录音／下载能力位保持不变，不宣告参数写入或 DDR 长录音。`BLUETOOTH_DIAGNOSTIC_UART=1` 可将现有调试 TX 选择为 BLE1 只读状态，默认仍输出工作站诊断；它不新增排线信号。前序限制见[蓝牙接入记录](../../reports/CUSTOM_BOARD_NATIVE_BLUETOOTH_20261023.md)，本次整合来源与验收缺口见[整合记录](../../reports/WORKSTATION_INTEGRATION_20261024.md)。

`workstation_lcd` 复用 Push 的性能页渲染器，消费公共状态的 290-bit 原子快照，在帧边界更新，不另建参数副本。采用远端 LCD 的 31.5 MHz、800×480 时序；隐藏当前快照没有提供的末音／力度字段，背光等待三个完整帧。LCD 停钟、快照丢弃和刷新均不能阻塞音频；不接入触摸输入，也不新增 DDR 客户端。D 模式、长录音和 Wi-Fi 网络服务仍不在本次装配范围。

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-custom-board \
  --netlist-dir "$HOME/Documents/fpga补充文档" \
  --custom-board-output /tmp/custom_138k_new_candidate
gw_sh /tmp/custom_138k_new_candidate/workstation/Prj1/scripts/custom_board_synthesis.tcl \
  > /tmp/custom_138k_new_candidate/synthesis.log 2>&1
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_custom_board_audit /tmp/custom_138k_new_candidate
```

`--usb2-full-speed-only` 可显式准备 FS 业务固件配置；默认允许 HS 协商，不保证实物链路速率。输出目录必须不存在，不可混入整机发布参数。生成的旧通用 `build.tcl` 主动报错，不能沿它进入 P&R；完整 IO、时序／CDC／PLL、电气和实板门禁必须先补齐。当前来源、综合、实际 25K 仿真及剩余阻断见[新板原生装配记录](../../reports/CUSTOM_BOARD_NATIVE_INTEGRATION_20261022.md)。

新板时钟声明由 `boards/custom_138k/clocks.json` 单一生成，显式保留 50／60／12.288 MHz 三个输入和十个派生时钟（含 LCD 时钟；FPC 直接使用 12.288 MHz 主时钟）；视频 CLKDIV /5 使用 `{1 7 11}` 边沿描述实际 60/40 波形，不能按默认 50% 占空比代替。独立源网表审计检查可见 PLL 的来源连接、分频、相位、使能及 PFD 合法范围；DDR 不透明 IP 内部 UI 分频仍留待实现后验证，不把它算作已解析。时钟声明本身不添加 false path 或全域异步时钟组，FPC 音频／LCD 保持字邮箱另有定向约束；不因此解除部署门禁。原生准备入口仍仅允许综合，显式物理实验必须另外记录输入、新 UserCode、授权和实际物理结果；不能通过修改原候选状态来冒充发布。时钟声明的前序记录见[显式时钟记录](../../reports/CUSTOM_BOARD_NATIVE_CLOCKS_20261022.md)。

原生准备可显式增加 `--hdmi-mode 720p30`，默认仍为 `1080p60`，accepted full83／timing85 和资源入口不接受该选项。720p30 使用 1280×720 有效区、3300×750 总时序、74.25 MHz 像素和 371.25 MHz OSER10 时钟；这是实际 PLL 输出分频和扫描模式改变，不是单独放宽 SDC。仅视频两条派生时钟变化，其余音频／DDR／USB／LCD 时钟和 CDC 例外保持。渲染器在 1280×720 背缓冲内采样原 1920×1080 逻辑画布，保留完整界面范围；DDR 行步长随输出宽度改变，帧 bank 仍使用 `ddr_address_map.vh` 的原分配。适配由 `tools/workstation_video_mode.py` 校验锁定输入和唯一锚点，原 PLL 包装源码保持不变，独立生成改频版本；后续原生归位时替换该适配，不向 accepted 默认传播。验证入口为 `sim/test_workstation_video_mode.py` 和 `sim/display/run_scanout.py --hdmi-mode 720p30 --native-queues`；候选、实板支持与闪烁验收单列于[720p30 记录](../../reports/WORKSTATION_HDMI_720P30_20261026.md)。

也可显式选择 `--hdmi-mode 720p60`：有效区、逻辑画布映射、DDR 行步长及 74.25／371.25 MHz 时钟与 720p30 相同，水平总长改为 1650、HS 为 1390–1429，垂直仍为 750 行、VS 为 725–729，输出 60 Hz；界面标签同步更新。扫描有效读带宽为 110.592 MB/s，不再沿用 30 Hz 的 55.296 MB/s 估算。该配置保留单独来源身份，不修改默认或原 720p30 配置；硬件兼容性和完整界面需单独验收。使用 `sim/display/run_scanout.py --hdmi-mode 720p60 --native-queues` 检查实际宽度扫描，`tools/workstation_video_physical.py` 对两种显式 720p 配置绑定实际时钟／PLL，再执行哈希固定的原物理门禁；不改变历史检查器或放宽门限。实施与验收范围见[720p60 记录](../../reports/WORKSTATION_HDMI_720P60_20261027.md)。

原生新板装配通过明确的层次参数绑定，将延迟效果两条 65×512 偶／奇预取 FIFO 选择为 BSRAM；`music_async_fifo.RAM_STYLE` 默认仍为分布式 RAM，accepted 配置及其它 FIFO 不随之切换。只改变存储原语选择，不改变容量、ready／valid、头部预取、Gray 指针、PANIC／flush 或 DDR 分区。综合审计必须核对实际原语、容量、双时钟与读模式，防止参数路径漂移导致静默退回。物理拥塞、存储映射等价验证和后续实现结果见[2026-10-25 物理记录](../../reports/WORKSTATION_PHYSICAL_20261025.md)。

原生配置同时保留锁定资源父配置中仍适用的 157 条 CDC／复位约束。旧 Dock 端口、已移除 MIDI 数据和另行审计的事件 FIFO 约束共九条不沿用；共享输入 owner 和 TMDS 串行器按实际新层次改名，处理清单进入 `integration_inputs.json`。父 SDC 字节哈希不符即失败。可见端点必须命中综合网表，DDR 不透明 IP 内部端点留待实现后审计，不能以补齐源约束宣告物理时序通过。

## R00 显式生产组合

`--workstation-profile custom138k-workstation-r00-v1` 单独选择 no-CNN＋owner8 的原生录音源策略，在真实 HDMI DDR 仲裁中新增录音并接实际完成 PCM 和 AE350 `0xf8040000` 服务。默认／其他 profile 的仲裁和 BLE 短录音保持原选择；本路径尚未经过物理资源、完整 CDC、时序或硬件验收。容量、正常切换封存、读引用与回滚边界见[录音服务契约](../services/RECORDING_DDR_SERVICE_CONTRACT.md)。
