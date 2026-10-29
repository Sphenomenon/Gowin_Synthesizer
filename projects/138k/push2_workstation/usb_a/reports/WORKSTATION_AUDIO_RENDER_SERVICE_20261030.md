# 48 kHz 请求驱动合成／矢量服务检查点

日期：2026-10-30。这是独立源码与离线验证阶段，尚未进入新整机 profile。它不证明最终音源选择、最终主音量、双率 DSP、CDC／时序或板上音频验收。

## 来源与接口

新增 [workstation_audio_render_service.sv](../rtl/audio/workstation_audio_render_service.sv) 复用真实事件工作站、oscillator／vector／effects 和原 [workstation_frame_delivery](../rtl/audio/workstation_frame_delivery.sv)。唯一公共参数 owner 仍是 `workstation_parameters`；18-bit 事件、PANIC／生命周期语义、held／deferred 和 delay DDR 接口沿用原实现。

服务只有一个请求槽。接受 48 kHz 请求当拍产生一次 sample-ce，原 pending 立即登记，等待已开始的 Note On load 后优先启动核心，不让持续事件流抢在该帧前面。取消只交付一次显式零响应；即使响应已经返回，槽也要等真实排空后释放。44.1 请求明确返回零／error 并计数，不触发 48 kHz DSP，不消费迟到旧帧。

`gw138k_event_workstation` 新增只读 `render_idle_o`，以及默认关闭的 `REQUEST_DRIVEN_RENDER=0`。原采样／事件调度在默认值下保持；只有 service 显式置 1 后，core-ce 才等待取消尾窗。原有 sample-ce→pending 优先权没有移到 wrapper 的 idle 轮询中。

实际 prepared revision 3 候选 `custom138k-workstation-v1-d23d498ea824c9f9` 用作旧源参考：event SHA256 `cd1da0ee40b5189b605a6c250618a8b0cc44bdbb4998ce4898a4bbd2ae59fc5f`，frame delivery `639fcc1496cc6a8c0f19f0979e4affdcfca34e1770d3b89c318dde3141f715c6`，实际资源适配 oscillator `7afb67e8b92828b50e42fbdfa259bf5c5ec0b39d1104bc263c5072e93067859e`。冻结和 vendor 字节没有修改。测试只在输出目录对旧 event 的唯一模块声明改名，允许三实例并行比较；其它业务字节不改写。

参考 profile 可从提交 `584e3816d4ab4e7e9e487cddaacdf54dfbf0c569` 重建。本次新 event SHA256 为 `9cce4d73faacb47d648e11bcc55c56ba4ef482bb14491f0e5c9bca2c15b28bd2`，service 为 `bc50de635f94b8c1b3d3b1f238dd0a87543ed262264799f87aa7a23189da264d`；完整回归的 44 项输入在运行前后均未漂移。

新的 event 源字节已不同于 revision 3 锁定身份，因此不能复用该候选作为改变后的构建身份。profile／顶层／旧输入锁暂不刷新，后续必须用新显式 revision 选择此服务。完整 API、取消尾窗推导和退役条件见 [AUDIO_RENDER_SERVICE.md](../rtl/audio/AUDIO_RENDER_SERVICE.md)。

## 最终 PCM 的边界

服务输出是合成／矢量 effects 及左右 route 后的 Q1.31 对，明确选择 `EXTERNAL_MASTER_VOLUME=1`；`master_volume_o` 只是已有权威参数的投影。TF／合成选择、一次最终 CC7、PCM16 量化、I2S／分析／录音 tap 的统一接入仍由原 owner 的后续工作完成。这里不增加第二个音源选择器，不把 service 输出称为最终 DAC PCM。

## 真实负载验证

`sim/audio/run_render_service.py` 直接编译上述 prepared 依赖和新 service。完整机器证据见 [audio_render_service48.json](workstation_task_20261030/audio_render_service48.json)。

三实例职责分别为新 service、current event 默认参数分支、未改 prepared event。默认分支在整个测试里逐拍核对事件 ready、held、active、applied、PANIC 状态、mode、delay DDR 握手／数据以及完整 Q1.31 PCM；正常 service 在同样的 1600 周期请求节拍上逐帧核对 guarded 旧源。新 opt-in 取消调度的隔离合同单独核对，不要求复制旧的不安全尾部行为。

| 路径 | 真实声部／音色 | 正常接受请求到响应最大计算周期 |
|---|---|---|
| A | 32 声部，五音色 | 222 |
| B | 32 声部，五音色 | 249 |
| C | 32 声部，五音色 | 1145 |
| vector | 八声部，五音色；旧 C 扫描仍参与汇合 | 1145 |

正常组合为 4 路径 ×5 音色 ×8 effect mask ×6 顺序，共 960 组。另在全部效果开启时填充 4096 帧，覆盖实际 chorus 和四路最长 2131 帧 FDN，再测试六种顺序；三路湿声及 FDN 返回必须实际非零。delay 测试明确使用 `ECHO_SAMPLES=32`，让短用例经历真实 FIFO、湿声与反馈；生产默认仍为 9600。存储侧是有序 history／flush marker 模型，不是 DDR 时序证明。

取消覆盖 A／B／C／vector 各 1600 个触发相位、CC PANIC 与生命周期两类；另以五音色扫描 41 个 loader 取消偏移，共 205 例。没有尾窗的状态判据作为负对照，必须观测到“看似 idle 但旧 valid 仍存活”；正确 idle 必须等这些 valid 全部消失。最终还有 4096 条持续控制事件压力、无请求不生产、held／参数保持、忙时 44.1 拒绝及 idle 44.1 显式错误响应。

最终完整运行通过：**59,378 次接受各返回一次响应，6400 次 CC PANIC、6400 次生命周期取消及 205 次 loader 取消全部通过**。共有 31,192 次显式取消／静音零响应，25,636 次已经响应之后的内部结果被排空；不支持的速率与忙时额外请求各计数一次。旧尾部最长观测为 33 计算周期，短于 40 周期尾窗；无 fence 的负对照累计 18,551 个“看似 idle 但旧 valid 存活”的周期。真实三路湿声和 FDN 反馈均非零，memory-side 共交付 7395 个延迟湿声历史项。持续事件压力下没有产生核心 deadline／MIDI overflow／note-drop／delivery duplicate，服务未以重复响应或无请求自动生产来填满节拍。

包含 Note On load、取消等待及持续事件压力的本次最坏请求到响应为 **1183 计算周期，约 15.404 µs**；正常 C 为 1145 周期，约 14.909 µs。一帧名义 1600 周期为 20.833 µs，最坏观测后剩 417 周期，约 5.430 µs。请求同步、队列、返回 CDC、后续源选择／主音量和串行建立时间尚须从余量中扣除，不能只凭核心耗时宣称整条链路满足两颗实体参考的频差预算。

`test_current_workstation_sources.py` 的 10 项来源边界测试通过；最终编译没有 `UNOPTFLAT`，service 实现本身无告警。旧依赖及测试台的既有宽度／未接观察端口告警保留在编译日志，不把它们写成全项目零告警。Python 编译、输入／日志哈希、报告链接与 diff 空白检查分别完成。

## 剩余接入与回退

legacy 的 40 周期取消尾窗只保护固定来源的已知 valid 流水；下一步用独立 runtime oscillator 的真实 `quiescent_o` 接入，避免把来源相关尾窗作为长期通用调度机制。vector／effects 的运行时 rate、历史清理、held／参数保持以及实际最坏耗时仍需同一新分支的证明。

本阶段没有综合、P&R、时序／CDC／PLL 签核、SRAM／Flash 或板卡操作。回退为不选择新 service，保留事件工作站 `REQUEST_DRIVEN_RENDER=0`；原 profile 的锁定身份及旧准备结果继续保留，不能用改变后的源字节覆盖旧证据。
