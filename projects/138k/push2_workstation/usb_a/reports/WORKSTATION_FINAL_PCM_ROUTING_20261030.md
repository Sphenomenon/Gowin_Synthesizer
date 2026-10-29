# A03／A04 独立最终 PCM 与物理帧 tap（2026-10-30）

本阶段新增两个独立 owner 组件：计算域 `workstation_final_pcm_router` 选择 render 或同率 TF，在选源后只应用一次最终主音量／静音；selected-MCLK 域 `workstation_pcm_frame_fanout` 从串行器实际完成的完整帧分发默认分析与录音。计算完成仍明确命名为 pre-serial 诊断，不能在桥迟到／串行欠载时冒充已发送音频。

旧 `workstation_output_router`、PT8211、FPC、accepted profile、top 与 locks 均未修改或选择新路径；A03／A04 整机项保持未完成。公共参数的唯一 owner 仍为 `workstation_parameters`，无第二份 CC7／路由权威状态。

## 来源和数值合同

源码基点为 `e2d59c5`，其中父代理已单独提交桥和 I2S 的 error 位传播。本组件消费该显式接口：bridge `rendered_error_i`→`sample_error_o`，serializer `SAMPLE_ERROR_ENABLE=1`／`sample_error_i`，源错误有独立计数且不冒充 deadline underrun。

| 组件 | SHA-256 |
|---|---|
| `workstation_final_pcm_router.sv` | `ff2c8612ec9f5ae32f4fb753d1b0cc671a91699ab3a7f55e819d56ce29573d6e` |
| `workstation_pcm_frame_fanout.sv` | `e6f82fd255460e91a0fee6bbdbe1053558f1b50009c3ed384aba1709557c971d` |

以上表格身份以 [final_pcm_routing.json](workstation_task_20261030/final_pcm_routing.json) 的 `source_identity_sha256` 为可机器复核权威；文件和所有实际消费依赖、ROM、WAV fixture、编译参数、日志哈希均记录于其中。接口矩阵与失败策略见 [FINAL_PCM_ROUTING.md](../rtl/audio/FINAL_PCM_ROUTING.md)。

render 输入为 `EXTERNAL_MASTER_VOLUME=1` 服务的 Q1.31 stereo，保留既有 expression／mix／effects／左右 route，最终 CC7 在新边界执行一次。Q1.31→PCM16 的 nearest／ties-away／saturation 与旧 PT 相同；之后一次 Q1.15 乘法及算术右移／饱和，保持旧 PT→FPC 的稳定增益数值次序。TF 是已解码 PCM16，保持旧直接 TF 源旁路 synth effects 的语义，不再量化成第二份源。

保留原 FPC 的增益限幅：48 kHz 每接受 slot 最大 256，44.1 kHz 为 160/147 带余数换算，0→unity 分别 128／118 slot；目标 0／mute 对相应 slot 立即为零。跨 rate／epoch 不复位 applied DSP gain，不复制公共参数。新组件没有用 latest-sample 保持或抽取来填时间线。

## 已通过的验证

| 验证 | 实际结果 |
|---|---|
| 独立路由／算术／身份 | 1292 accepted = 1292 responses；1024 组有符号随机／边界和 gain 检查，正负半格／满幅／饱和，64 个 clip 帧 |
| 选择、控制与失败 | 整帧锁定 route／gain；scope 优先于 TF；静音及零 gain、忙时拒绝、旧 epoch／cancel、迟到／意外 render；异率和旧 TF generation 不消费，TF 无数据／错误显式零帧 |
| 真实源与旧路径 | 370 个最终帧，其中 128 帧逐帧对照实际旧 PT→pin selector／observer→真实 FPC；A/B/C 各 32 声部、vector 8 声部共 64 帧，真实 WAV TF 共 64 帧；含实际 CC7=64 的半增益比较 |
| 实际 WAV 两率 | 原生 WAV decoder 消费真实 RIFF 字节，48000／44100 stereo PCM16；160 对 TF 样本被接受；48→44.1→48 文件异率请求明确拒绝，随后正确同率文件恢复 |
| 新桥→I2S→物理 fanout | 48→44.1→48 三代次，独立逐 bit 解码 255 个物理帧、检查 243 个完成帧；186 正常、57 error；所有完成 PCM／rate／epoch／sequence／error 与分析和录音完全相同 |
| 真迟到与源错分开 | 刻意延迟 3 个桥返回越过 deadline，得到 3 个 underrun；54 个 TF 欠载／异率源错误经 bridge error 位到实际 I2S 零／error 帧，独立 source-error 计数 |
| 慢 tap 不反压 | 分析 drop 81，录音 drop 144，gap／fault 同时可见；实际 I2S sequence 连续、三个 epoch 可见，没有为慢端重放旧 PCM 或停音频 |
| 来源与编译 | 每阶段和最终输入 hash 复核通过；`test_current_workstation_sources.py` 10/10，Python syntax、diff-check 通过；新实现警告 0、`UNOPTFLAT=0`，继承的旧源／TB 警告保留在机器记录 |

旧链比较严格保留原 1028 帧 FPC 启动过程，没有强制内部状态或改源。逐帧对照只针对 48 kHz 正常供给且两侧 gain 已到目标的样本；不把旧 latest 保持、源切换 settle、gain slew 相位差或新的显式错误帧混为逐拍等价。两率 gain 限幅和取消语义由独立单测核对。

物理联测先等常开桥全局 reset-release／quiesce 同步稳定，才释放 serializer 本地 reset 并请求 slot0。若跳过该 readiness 顺序，首请求会早于桥就绪，预填充不能完成；未来整机组合必须保留该顺序。

## 重放与剩余工作

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_final_pcm.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output <不存在的新目录>
```

真实源 fixture 与物理 I2S fixture 是两个独立验证，尚未把真实 render、production TF CDC、完整双率 effects、最终桥／I2S、显示与 BLE 录音装配到同一完整工作站。现有 `tf_workstation_audio_bridge` 仅有 `pcm_active` 和独立同步 rate，缺少原子的 PCM／实际 rate／transport generation 事务；本次使用真实 WAV decoder 在 coherent compute clock 中验证准确边界，不能宣称旧异步 TF 桥已迁移。

默认分析和录音消费者还须接物理完成帧的完整 payload CDC，源 error／sequence gap 废弃分析窗口、封存／失败录音对象；44.1 格式协商与旧 48 kHz BLE／显示协议保持独立。新 router 自己空闲不能替代 service 实际 tail、effects history、TF FIFO、bridge、serial 的联合排空。

源 fixture 的最大完成延迟为其测量边界下的 1182 计算时钟；它不是全桥／I2S预算，也不能与其他 harness 的 1183 时钟直接相减来声称性能改善。新算术流水的附加成本仍需进入完整 12 μs 预算、综合／P&R 与物理 CDC／PLL／资源审计。没有生成 bitstream，没有操作板、SRAM／Flash 或验证模拟音频。回退无需改板：现有 profile 仍使用旧路径；未来显式组合可移除这两个新组件并恢复其旧连接。
