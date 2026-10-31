# 双 138K：W8 实测 PCM owner 描述符长路径修复

2026-10-31。W8 `D2103108` 实际 P&R 的最差 setup 为 −9.674 ns：`cpu_pcm.owner/staged_frames_2` 到 `cancel_epoch_o_17/CE`，实际数据延迟22.474 ns；同一组合锥还到达 `active_generation`。路径明细先经过32位 `128-staged_frames` 减法、128位 `required_mask` 桶移位，再经过完整128位串行 ALU 比较链。另一路 `compute_epoch_1` 到效果 DSP 输入为 −9.672 ns，前段包含 owner 的32位等值链；后段的 service／音源 gain／量化／混合路径另行处理。

本次只改实际被完整候选消费的维护源码 `rtl/audio/workstation_ae350_pcm_owner.sv`。将 `required_mask` 写为明确的1–128范围与逐位8位常数阈值，缺帧判定写为 `|(~written & required_mask)`；key／session／physical epoch 等值判定明确使用 XOR 后归约。没有引入流水寄存器，没有改变受理或采样时刻，没有改 RAM、队列、SRC、命令返回、失败语义或同拍撤销优先级。未修改其他 agent 负责的 service／音源／效果源码。

掩码的等价关系覆盖全部无符号32位帧数：原移位量是 `(128-frames) mod 2^32`；仅 frames=1..128 时位于0..127，其他所有帧数均令128位结果为零。因此第 i 位恰等于 `1<=frames<=128 && frames>i`。此外 `(written & mask)!=mask` 与缺失位 OR 归约精确等价。这里给出组合逻辑的代数关系，资源与时序收益等待新整机综合／P&R 实测，不预记收益。

`sim/audio/fixtures/workstation_ae350_pcm_owner_before_descriptor_mask.sv` 封存完整 W8 修前 owner，SHA256 `e1823ee42fb94a2bf2f1d8600881a0c401b95853766778878cecee13556adf2e`。新回归逐周期对照7190个周期、65项状态／输出、512个 RAM 字、4组 written／frames，包含6000随机命令及同拍 TF revoke／RAM write／COMMIT consume；新增115011组实际 owner 掩码／受理向量，包括全部16位低域、32位高位／回绕边界、随机32位帧数、16384组合法前缀×单缺失位，以及256个逐位许可／key错配。阈值错一位、缺帧误用 AND、高帧数低8位混叠、physical epoch 错误比较四个 mutant 均在对应 oracle 拒绝。

已有8项 owner 功能测试通过，其中48/44.1 kHz 各以±2000 ppm运行576000帧，覆盖0/1/2消费、块所有权、欠载、CPU／session／rate／TF撤销及命令身份耗尽。真实 native runtime 再次通过1454个最终物理帧：1436个有效帧与18个预期合同错误；覆盖真实 APB／CDC owner、DSP／chorus、仅一次音量、I2S、MIDI保留、CPU／session fence、TF及双采样率，所有输入 hash 在前后封口。它使用理想时钟与有序 DDR 模型，不构成持续速率或硬件接受。

[机器证据](dual138k_pcm_descriptor_gate_20261031.json)包含原物理路径、代数关系、完整正负控、runtime 输入身份与测试范围。初次新 runner 的 source／bench 同名输出错误保留原失败 JSON，修正输出名后全门通过，未放宽 RTL 或 oracle。`git diff --check` 通过。当前新源码尚待新整机综合与 P&R；原 W8 封存输入和位流保持原身份，未操作板卡、SRAM 或 Flash。
