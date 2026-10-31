# M8 显示分析入口逐拍等价验证

日期：2026-10-31。阶段：RTL 离线验证。完整来源哈希、命令与结果见 [verification.json](dual138k_display_analysis_20261031/verification.json)，原元数据门禁的完整结果见 [metadata_verification.json](dual138k_display_analysis_20261031/metadata_verification.json)。本报告不代表新候选的综合、P&R、实体 HDMI／I2S 或 SRAM 验收。

## 被验证的修改与独立参照

维护源码 `rtl/display_data/display_data_analysis_source.sv` 将 epoch、序号、波形／分析身份比较改为带 `syn_keep` 的四位 XOR 归约，把 `previous_sequence+1` 移到帧接收边沿保存为 `expected_sequence`，并去掉已被独立 context_changed 撤销条件吸收的序号比较前置限制。

旧源码保留为 `sim/display/fixtures/display_data_analysis_source_pre_m8.sv`，与提交 `ec223df` 的原文件逐字节一致，SHA256 固定为 `a8f1a948370a464d6ed609d275075e2ff936a01e62bc915074914a1193d9736c`。runner 在任何仿真前校验该哈希，临时副本只改参考 module 标识符；生产源码与旧参考各自实例化真实 waveform、2048 点立体声 FFT 和 XY 链。既有五份 prepared writer／reader／capture／alignment／ROM 哈希门禁原样保留，参照变化必须失败。

此次验证工作只新增／扩展 `sim/display` 的 fixture、checker、runner 与 TB，并保存报告。生产 RTL、native helper 和 runtime profile 由主线程维护。

## 全输出比较与功能用例

checker 逐一比较模块全部 21 个外部输出，包含 source／wave／analysis 有效标志、采样率、epoch、generation、分析序号／丢弃数、峰值／gain、完整 256-bit metadata、discarded 计数，以及未由 valid 掩盖的 read_data。比较发生在两个时钟边沿与异步复位断言后的稳定时刻；runner 还检查当前／旧版端口名清单一致，并确认每个输出在 checker 中恰好比较一次。

原真实场景继续覆盖 48 kHz → 44.1 kHz、FFT 运算中切换 epoch、同 epoch 观察丢失、非可信源拒绝、三次真实发布，以及全部波形、XY 位图和 FFT 谱列校验。新增 79 个物理帧身份用例包含：

- 同 epoch 下 `fffffffe → ffffffff → 00000000 → 00000001` 连续回绕、重复序号、跳号及后续恢复。
- 以 `89abcdef` 为底值逐位翻转全部 32 个 epoch 位，再还原；序号保持连续，使高位比较必须单独触发撤销。
- epoch／采样率和序号间断同时变化，验证只撤销一代；同一高 epoch 的后续连续帧继续被接受。
- 无 frame strobe 时的持续 trust／loss 撤销与恢复、有效帧错误、epoch 零拒绝。
- 任意高位 epoch 的真实 48 kHz FFT／XY／波形完整发布，以及另一个真实 FFT 运算中的复位。

新增断言独立检查撤销在接收边沿前即生效、连续帧不误撤销、一次故障只递增一次 generation／discarded，以及复位后没有残留上下文。

## 结果

| 项目 | 结果 |
|---|---|
| 新旧全部外部输出 | 5,645,819 次比较完全一致，21 个端口全部覆盖 |
| 真实完整发布 | 4 次；2,048 个波形样本、262,144 个 XY 像素、2,048 个谱列校验通过 |
| 真实立体声 FFT | 两采样率的峰值始终为 bin 32／64；高 epoch `2309737967` 保持实际 48 kHz 标签 |
| 新增身份边界 | 79 帧、32 个独立 epoch 位、4 帧回绕、repeat／skip、trust／loss／error 全部通过 |
| 复位 | 2 次，其中 1 次发生在真实 FFT_MULT 状态 |
| 原 minor0 精确兼容 | 615,641 个周期、1,098 个默认写 beat 一致 |
| 原 minor1 传输 | 14 次全 cache 校验，6 次 commit、3 次 abort、5 次拒绝、6 次首读校验通过 |
| 原最终 WRITE 撤销负对照 | 正确拒绝移除最终比较 drain 的实现 |
| 错误序号预测负对照 | `expected_sequence=frame_sequence+2` 在第 70 次比较即触发公共 source_context_valid 失配 |
| 参考身份负对照 | 旧文件追加任意字节后被固定哈希门禁拒绝 |

错误预测的实际失败输出保存在 [negative_sequence.txt](dual138k_display_analysis_20261031/negative_sequence.txt)。所有输入在最终运行期间哈希保持不变，无 fixture／维护源码警告或 UNOPTFLAT。

## 复现

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_display_analysis_equivalence.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev5-v1/workstation/Prj1 \
  --output /tmp/dual138k-m8-display-analysis-equivalence-v2
```

输出目录已存在，重跑时选择新目录。默认执行原 `run_display_metadata_v11.py` 全套回归，再执行新旧全输出比较及错误预测负对照；原 metadata runner 单独调用时继续使用原有三次真实发布场景。`--reference-source` 也必须符合固定旧版哈希，不能借该参数替换独立参照。

最终离线身份为 `display-analysis-equivalence-v1-1f6a905843fd40af`。新的真实资源、路由时序、板上声画和部署身份由后续整机候选记录，不能从本次等价验证推断。
