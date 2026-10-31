# M9 音频控制路径切分与离线验证

本阶段修改三份实际被 M9 准备工程消费的维护 RTL，并完成针对性离线验证。新源码尚未进行新候选 prepare、综合、P&R 或实板操作；物理资源、时序收益、DAC／HDMI、SRAM／Flash 和双板验收均未据此通过。来源、逐文件哈希、运行日志与失败记录索引见同名 JSON。

参考为 `custom138k-workstation-m-demo-v1-aa7abf5c6454a377`／`D2103107` 的真实 M9 P&R。`Prj1.gprj` 中三份旧输入均 enable=1，准备副本与修改前哈希相符。原始时序报告不改。全局 setup 表只列最差 2000 条路径，分类结果如下；它不是全部 6772 个违例端点的分类统计。

| 报告路径类别 | 条数 | 最差 slack/ns |
|---|---:|---:|
| config_state → 公共 PANIC admission 扇出 | 1708 | −3.625 |
| vector event／data | 141 | −3.494 |
| TF DMA | 51 | −3.643 |
| final PCM gain | 47 | −3.618 |
| 其他 | 53 | −3.218 |

实际最差音频控制链从 `config_state_2_s1/Q` 经过 service 的配置／自动配置选择、`runtime_config_block` 和 event dispatch，到 PANIC 清零逻辑。VO 中末级反相节点与 `panic_accept_Z` 同输入，扇出 1113；到 Delay 写 FIFO RAM CE 的路径共 9 级逻辑，数据路由占 12.814 ns。它不能仅按中间实例名误判为配置提交网。另一条 `panic_muted_s0/Q` 到 final PCM DSP B 输入有 11 级逻辑，首段路由 8.686 ns，随后进入增益比较／斜坡运算。

`gw138k_event_workstation.sv` 为完整 native 分支增加同域取消交付寄存器。原公共 PANIC 接受、epoch、held／deferred 和 frame／join 作废仍在接受边沿提交；真实 engine／effect clear 在下一计算边沿送达。该交付边沿禁止 engine sample、事件 dispatch、mode commit、配置接受，并通过只读 `cancel_delivery_pending_o` 关闭 service 的新 render ready。已经进入 session／FIFO 的普通事件保留。默认 legacy 分支的该状态为常零，旧清零路径保留。

这项改动有明确的周期合同变化：取消之后增加一个计算周期的 admission 保留窗，不能宣称 native 全输出逐拍等价。串行时钟与采样计划没有新增门控。`workstation_final_pcm_router.sv` 的 registered render valid 同时补齐握手：若 slot 接受后下一拍的 ready 因保留窗关闭，继续保持 valid 到真正握手，防止已承诺 slot 丢失。正常 ready 情况仍只发一个请求周期。最终完成前仍按原 slot 的 cancel epoch 检查作废。

final PCM 的纯数值修改把 mute 从 slew 的目标比较输入移到结果选择端。`sim/audio/prove_final_pcm_gain.py` 绑定维护源码中的精确表达式，用 Z3 证明任意 16-bit 音量、16-bit applied gain、8-bit 余数、rate 和 mute 共 42 个自由输入 bit 下，gain／余数下一状态相同。去 mute、去立即归零、静音时错误推进余数三个语义变体均有反例。运行该脚本需有 `z3-solver` 的 Python；本机验证使用 `/Users/sphenicidition/miniforge3/bin/python3`。

离线结果均绑定当前源码，相关输入运行前后哈希一致：

| 验证 | 实际结果 |
|---|---|
| 完整双率真实 render/service、生产长度 Delay 与有序 DDR 模型 | 48691 请求／48691 响应；独立整数效果模型比较 48k 24323 帧、44.1k 24322 帧 |
| 取消交付定向 | 1074 个交付边沿全查；两率各覆盖 request 与 response 的前／同／后边沿，共 12 case；紧接清零边沿及后续两边沿的 NoteOn／mode 共 12 case |
| 真实 bridge／I2S／fanout 整链 | 22532 帧逐 bit／身份／节拍检查，12 个真实 router 边界全部完成；最大 render 1204、slot 1229 个计算周期；同时保留 A/B/C 32 声部、vector、两率完整湿声、768 参数压力事件与故障隔离检查 |
| default／legacy 对照 | prepared 旧源与 current-default 逐拍对照通过；8650 请求／响应，960 正常 case、64 CC、64 lifecycle、205 load-cancel，取消扫描每源每类 16 phase |
| 最终 PCM 与旧输出路径／真实源 | 1293 数值／错误／握手 case；真实源 370 帧，含 128 legacy、64 render、64 WAV 对照 |
| 负控 | 移除 dispatch 交付屏障、移除 service ready 屏障各被真实 service 定向矩阵检出；真实旧 final PCM 源被新增 stalled-valid 测试检出 |
| 来源与静态检查 | `sim/test_current_workstation_sources.py` 17 项通过；增益证明脚本编译、`git diff --check` 通过 |

I2S `serial-v2` 曾达到 240 秒墙钟上限，不据此推断根因。`serial-v3` 使用同一已编译二进制，逐项核对原 compile 输入未变，在 611 ms 仿真时间、191.899 秒墙钟完成全部 12 case 和原整链断言。独立诊断 fixture 仅加阶段输出，记录了 startup／source 推进；原 fixture 已完整通过后停止重复诊断，保留其 partial log 与停止原因，不把该诊断计为接受证据。更早 `serial` 则因握手修正改变输入而主动停止，同样保留为 superseded。

三份冻结维护 RTL：

| 文件 | SHA256 |
|---|---|
| `rtl/audio/gw138k_event_workstation.sv` | `238d1274e1ad5d724632607374f08a8f03a8fe9d4df26c69613f7dbb26de2646` |
| `rtl/audio/workstation_audio_render_service.sv` | `148f0fb7b8976099d26bbf71025105c0d0df6f3b5e06ea90f1f75cdae0e46968` |
| `rtl/audio/workstation_final_pcm_router.sv` | `087a0e7a0323ae9e58c3479768145135d20d6765cfeb2e4343abaf075fa92e97` |

证据根目录为 `~/.cache/gw138k-dual-20261031/audio-control-pipeline-v1/`。下一显式候选由主任务更新来源锁和输入身份后重新综合／P&R；本阶段不修改 profile、配置、候选、冻结 baseline、TF DMA 或 reverb 主实现。回退只撤销本阶段三份维护 RTL 及相应合同／测试，按 JSON 中的旧消费哈希核对，历史 M9 准备工程与物理证据保持可用。
