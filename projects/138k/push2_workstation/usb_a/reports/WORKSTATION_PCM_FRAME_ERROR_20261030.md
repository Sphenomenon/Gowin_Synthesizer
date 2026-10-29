# PCM 返回错误位到物理 I2S 的离线验证

2026-10-30。此前帧契约包含 error，但桥的 97-bit 返回邮箱只携带 rate／epoch／sequence／PCM。现在 `workstation_pcm_frame_bridge` 返回 98 bit，原子锁存 `rendered_error_i`，经 `sample_error_o` 与原身份一起交付。没有新增公共参数状态、改选 profile 或操作板卡。[机器证据](workstation_task_20261030/pcm_frame_error_propagation.json)绑定输入哈希及实际测试输出。

`workstation_i2s_serializer` 新增显式 `SAMPLE_ERROR_ENABLE=1`：匹配身份的错误样本仍消费自己的 slot，输出完整零 PCM，完成 tap 保留身份并置 `frame_error_o`。独立饱和 `source_error_count_o` 统计这种错误，`underrun_count_o` 继续只统计没有及时收到匹配样本的情况。错误位与 PCM 一同预取，停钟、背压、串行器局部复位不会擦掉旧邮箱；旧代次错误响应也不能污染新流。

默认参数为 0，保留既有未连接此位的接口行为。新 tagged-frame 装配必须显式开启并连接；默认分析／录音应消费串行器实际完成的帧，不能把计算完成的结果提前当成物理输出。接口维护在 [PCM_FRAME_CONTRACT.md](../rtl/audio/PCM_FRAME_CONTRACT.md)。

四个现有验证入口已通过：

- `sim/test_workstation_pcm_frame_bridge.py`：两组无关相位及相反 ±200 ppm，每率 160 个正常帧；各有 463 个接受请求、453 次渲染、451 个交付响应，取消／丢弃账目全部闭合。两种采样率分别在 prefill 和运行中注入非零 PCM＋error，共四个物理零／error 帧；没有额外欠载，之后正常帧继续输出。旧错误返回在 MCLK 停高期间保持，恢复后丢弃。
- `sim/test_workstation_i2s_serializer.py`：默认参数下将错误输入固定为 1，原三流的实际 I2S 槽位、PCM、欠载、拒收和帧边界排空检查保持通过，source-error 计数始终为零。
- `sim/test_workstation_audio_clock_i2s.py`：官方 GW5A DCS、默认 PDN=4／startup=1028、48→44.1→48、失钟恢复和真实跨域握手通过，四流共 34 个实际完成帧。
- `sim/test_workstation_audio_probe.py`：三项探针仿真／来源闭包／漂移拒绝检查通过。

重放时从仓库根目录运行上述各文件；官方 `prim_sim.v` 的 SHA256 为 `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`。

本阶段仍用有界 renderer 模型，尚未接真实 DSP／最终路由，也没有 98-bit 邮箱的新路由后 CDC／时序证据。历史 B7 的离线及硬件记录仍绑定其原始 serializer 字节，不转移到本次源码。回退保持参数 0；本阶段无综合、P&R、SRAM 或 Flash 部署。
