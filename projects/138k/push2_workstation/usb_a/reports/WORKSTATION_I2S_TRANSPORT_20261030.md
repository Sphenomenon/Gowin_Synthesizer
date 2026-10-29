# A03／A05／A06 双率串行帧独立检查点（2026-10-30）

本检查点完成独立 `workstation_i2s_serializer`，并把真实串行器接到已经提交的双参考监测／官方 GW5A DCS／切换事务组合，在默认 1028 帧启动预算下完成双向切换和失钟恢复。**A03／A05／A06 整项仍未完成**：现有整机 profile、FPC、DSP、输出 tap 与约束尚未接入这些模块；没有综合、P&R、板测或 SRAM／Flash 操作。精确命令、输出、输入 SHA256 和状态见 [i2s_transport.json](workstation_task_20261030/i2s_transport.json)。

## 来源与实现

- 基础为 clock 检查点 `f5dc5e0f3c470377ab55cc36a94e5f1afb29037b`；本身份为 `a03-a05-a06-i2s-transport-offline-20261030-v1`，不是位流 UserCode。vendor／冻结 baseline 不改。
- 串行器：[workstation_i2s_serializer.sv](../rtl/audio/workstation_i2s_serializer.sv)；帧和桥契约：[PCM_FRAME_CONTRACT.md](../rtl/audio/PCM_FRAME_CONTRACT.md)。时钟输入与门禁继承[独立时钟报告](WORKSTATION_F03_CLOCK_DOMAIN_20261030.md)，不把该报告的外部 ACK 模型改写为真实 DSP 验收。
- 实际输出时基为选中 MCLK：48 kHz 用 12.288 MHz／256、BCK 除 4；44.1 kHz 用 16.9344 MHz／384、BCK 除 6。每帧 64 bit，左右各 32-bit slot，I2S 延迟一 bit、PCM16 后补零。
- 每个输出 slot 请求一次下一帧，保持 rate／epoch／sequence。过期、错率或错代次响应消费后计数，不能冒充下一帧。欠载输出明确的零／error 帧并占用其序号，不重放旧样本；完成 tap 对应实际发出的完整物理帧。
- 正常 quiesce 等最后一 bit 完成，再静音并清除下一帧；新的流必须经过局部复位。预填充完成后，resume 仅在帧边界启动；第一完整帧实际发送后才应答 running，常开事务随后提交实际 rate／epoch。

配置在局部复位释放至首个 selected-MCLK 边沿采样。新 staged 身份可能在旧帧排空时先更新，旧流仍使用自己的锁存身份。组合 TB 首轮错误地用 staged44 检查正在排空的旧 BCK，报 `BCK divider`；修正为独立锁存每个流的期望身份后，保持原有分频／PCM／标签标准并通过。串行器没有为此改动功能；随后仅修正接口注释和契约采样窗口表述。JSON 保留早先独立 TB／lint 版本与最终注释版 SHA256，并验证去掉整行注释后所有字节相同；最终增强组合测试使用最终注释版。

## 校验

从仓库根目录执行以下命令，均 exit 0；工具版本、完整 stdout／stderr 在 JSON：

```sh
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_i2s_serializer.py
PATH=/opt/homebrew/bin:$PATH verilator --lint-only -Wall --top-module workstation_i2s_serializer projects/138k/push2_workstation/usb_a/rtl/audio/workstation_i2s_serializer.sv
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_audio_clock_i2s.py
```

独立串行 TB 在真实 BCK 上升沿逐 bit 解码 48k epoch7→44.1k epoch8→48k epoch9，每流核对 15 个物理帧、9 个带身份完成帧、1 次明确欠载和 3 个错误标签拒绝。覆盖左右 PCM、I2S delay／padding、MCLK 分频、完成 tap、序号和帧中 quiesce；该快速测试缩短启动帧计数。first-party 串行器 `-Wall` lint 零警告，不据此声称整个 vendor 组合 lint 通过；既有官方 simlib 全包 lint 未通过的范围仍见独立时钟证据。

真实组合 TB 使用官方 `gw5a/prim_sim.v` 的 DCS，SHA256 `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`。quiesce／resume 先经过两级 selected-MCLK 同步；串行 quiet 和响应模型完成旧任务后的 idle 共同构成 quiescence；quiet／drain／prefill／running 再经过两级 50 MHz 同步，flush 清除旧 ACK。普通请求返回模型有 8～12 个 selected-MCLK 周期延迟并保持完整身份，切换前定向注入一个 512 周期在途响应；quiesce 不取消倒数，等全部延迟结束才丢弃旧结果。两次切换共完成并丢弃 2 个旧响应，串行已 quiet 但事务仍保持 QUIESCE／局部复位释放累计 1424 个参考周期，证明串行 ACK 不能绕过响应模型的真实等待。**没有把 ACK 绑高**；这仍是测试夹具，没有真实 DSP 或生产计算域桥。

组合保留实际默认 PDN=4、startup=1028 帧和每等待阶段 2,000,000 个 50 MHz 周期／40 ms 超时；只加速测频资格参数为 500 周期窗、3 连续窗、25 周期失钟、8 周期停低和 12-bit 计数器。生产默认 1 ms／4 窗资格测试仍由原 clock 检查点单独覆盖。

| 流 | 实际 PREFILL 等待 | 结果 |
|---|---:|---|
| 启动 48k／epoch0 | 21.416980 ms | 真实第一完整输出帧后 ready |
| 切换 44.1k／epoch1 | 23.311120 ms | 384fs／BCK 除 6 正确 |
| 切回 48k／epoch2 | 21.416920 ms | 256fs／BCK 除 4 正确 |
| 失钟后恢复 48k／epoch3 | 21.416960 ms | 重资格和显式恢复后新代次 |

四次预填充均低于 40 ms，最慢一次余量约 16.689 ms；这只是当前默认串行启动预算的证据，不是整机最大切换时长或 DSP 期限保证。88.555 ms 仿真内共核对 34 个真实完成帧；每个完成帧检查物理 BCK 解码 PCM 等于最终 tap 和期望身份，分频持续按旧流／新流各自身份检查。

故障路径在实际 48k 播放期间让参考停高，真实失钟监测触发 fault6；无需新源边沿即可异步断言串行器局部复位。源恢复并重新合格后，显式 recover 重新执行 DCS 撤选／停低／目标资格／默认启动／真实 running 应答，保留已提交 48k 并增加 epoch。未用 SELFORCE 强制切换，也没有用复位整个计算域替代取消旧任务。

## 剩余接入与回退

1. 有界生产请求／返回 CDC 桥、常开计算域的外部 render 节拍／排空接口、两率 DSP 系数和历史清理、最终 PCM 与所有分析／录音／显示 tap 尚未迁移。测试夹具不证明现有引擎的实时预算。
2. held-note、PANIC／Note Off、TF／录音和任务忙时切换策略、AE350 入口仍须按整机契约完成；没有新增产品 CC 或默认策略。
3. AK4493S 的正式器件／修订、384fs／ACKS 与 PDN／SMUTE 顺序及板级 strap／电气仍需单独有来源核对和物理验收；数字 I2S 仿真不能替代 DAC 锁定或发声。
4. 父候选的双来源生成时钟、Gray 首级数据／偏斜、请求／响应 CDC、reset recovery／removal、DCS 专用布线及完整 P&R 门禁尚未实现和验证。

本检查点无板卡状态变化，无位流或部署身份。继续保留已有 accepted／pinned／resource／新板 profile 及其部署证据；后续接入只能形成显式新候选，不能把本离线身份当作现板固件或复用旧硬件验收。
