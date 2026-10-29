# 运行时效果链阶段 1：双率房间系数与数值审计

日期：2026-10-30。本阶段生成独立的 48／44.1 kHz 房间系数，5 项数值回归通过；**尚未实现 runtime Reverb、Chorus、DDR Delay 或效果链接入**。旧 generator、preset、冻结来源、profile／build／top 均未修改，也未操作硬件。

机器记录：[runtime_effects_coefficients.json](workstation_task_20261030/runtime_effects_coefficients.json)。源码是 [新生成器](../tools/generate_runtime_room_preset.py)，产物为 [JSON](../rtl/audio/runtime_spatial_room_preset.json) 和 [独立 SVH](../rtl/audio/runtime_spatial_room_preset.svh)，都尚未被 profile 选择。

## 实际接口与分阶段事务

固定 rev2 的实际 `legacy/rtl/audio/stereo_effects.sv` 通过 valid／ready 处理 signed 32-bit stereo，保存本帧 mask／order；未选效果仍执行维护帧。synth／PCM 增益 ramp 与各效果 wet ramp 均按样本推进，不能简单漏掉维护路径。

有效 Delay 是 `serial_delay_effect_ddr` 与 `delay_ddr_dma`：两条 65-bit 异步 FIFO，写向为 `{flush,right,left}`、读向为 `{marker,right,left}`；DMA 连接 owner6 req／ready／response。现有 marker 不含配置／事务身份，不导出 flush completion。DMA 只在 IDLE 取 flush，因此当前 outstanding read 会先返回并推送，不能只增加“44.1”标签就宣称旧事务排空。

后续独立原生模块拟采用 config_valid／ready、rate_44100、config_applied、history_clear／ready／done、quiescent／fault。私有 marker payload 绑定 rate 与事务号；DMA 真正 drain／丢弃旧 outstanding read、重置 ring 后才回送匹配 marker；audio 丢弃 marker 之前的 stale FIFO 项，收到匹配确认后应用新 rate 并开放下一帧。两个时钟域通过该屏障共同提交，在首个新帧之前必须已使用同一 8820／9600 长度。

owner6 只有 request-ready 和 read-response，没有物理 write-completion 引脚。下一阶段必须审计同 owner 的 posted write 顺序，不能将 request accepted 称作物理写完。history_clear 只作废历史／在途效果帧，不修改公共参数、held notes、mask／order 或 gain 目标；wet／sg／pg ramp 与 chorus phase 的保留由新命令单独约定。legacy clear 保留独立语义。

清历史期间关闭效果帧接受，上层继续按原采样节拍交付受控静音；超时／故障必须可观测，不能无期限停等或把未确认的配置报成已应用。后续按 DDR Delay pair、Chorus、Reverb、整条 chain 分阶段验证，不把本阶段系数结果当作这些实现已完成。

## 可复现系数

新工具校验旧 `generate_room_preset.py` SHA256 `87da227eb075569db4e80e2537fd224f42f3c3fed3ed7dadf593e244718a63c6`，直接复用其房间几何，不改旧脚本或数据。48 kHz 的 12 个 early taps、gain 与四个 FDN lengths 精确复现现有 preset。

| 项目 | 48 kHz | 44.1 kHz |
|---|---|---|
| FDN lengths | 1429／1789／1999／2131 | 1313／1644／1837／1957 |
| Damping old coefficient Q31 | 1073741824 | 1009899529 |
| Damping input coefficient Q31 | 1073741824 | 1137584119 |
| matched pole | 0.5 | 0.47027111472561955（量化后） |
| 半衰时间 | 20.8333333333 µs | 20.8333333352 µs |
| 理论 −3 dB 频率 | 5521.282948 Hz | 5566.477159 Hz |

Early reflection 由同一 image-source 物理超程重新按 Fs 量化，误差不超过半个样本；44.1 kHz 最大误差 10.624316 µs。FDN 在 nearest ±2 samples 搜索，要求 pairwise-coprime、保留原 48 kHz 最大 RAM 容量，按平方误差、最大误差、tuple 决定唯一结果。44.1 kHz 的最大 FDN 时长误差为 19.416100 µs，小于一帧。这里不使用先前未经验证的 nearest 组合。

Damping 选择 `alpha44=0.5^(48000/44100)` 匹配连续时间 pole，Q31 系数误差约 `3.25e-11`，两个互补系数之和精确为 `2^31`。它保留半衰时间；离散 −3 dB 频率仍提高约 **0.818545%**，不能声称频率响应完全一致。若后续产品选择匹配 cutoff 而非 pole，必须新建系数身份与回归，不能静默改表。

Chorus 尚未写 RTL：计划保留 1024-word 最大 RAM，48 kHz 使用原式；44.1 kHz 将 canonical instantaneous delay 转为物理时间后量化，LFO `349×160/147` 用余量累计保持 phase 和平均速率。gain slew 也必须按实际 Fs 推进，不能仅改延迟长度。

## 已完成的验证与范围

运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_room.py
```

5 项通过：精确再生成／48 kHz 复现、legacy generator 漂移拒绝、tap／FDN 物理误差和容量／互素性、Q31／时间常数／cutoff 量化、线性反馈收缩与双率 float64 冲激衰减。原 generator 与 preset 在测试前后哈希一致。

Hadamard／2 是正交矩阵，纯延迟是无损算子；本组正系数互补低通在 1025 个频率点的增益不超过 1，7/8 feedback 的线性环路范数上界为 0.875，小于 1。这证明所述线性模型的收缩；定点舍入、饱和与小 LSB 极限环仍需后续真实 RTL 验证。

仅对 FDN tail 建立 3 秒 float64 sample-domain 冲激模型，未包含 early reflections、wet slew 或饱和。T20 外推的 RT60 为 48 kHz 1.471012 s、44.1 kHz 1.470224 s，相差约 −0.053572%；末尾 0.25 秒能量约 `2.4e-12／2.6e-12`，远低于初始 0.25 秒。该数据不是实际 RTL T60、声学测量或听感验收。

下一阶段首先实现 DDR Delay 消费者／DMA 的同配置屏障、旧响应排空和独立 history_done，再验证 48 kHz 逐帧等价及 44.1 kHz 200 ms（8820 帧）真实回声。整条效果链的顺序、开关、wet／反馈、受控历史清除、deadline 和物理验收仍未完成。
