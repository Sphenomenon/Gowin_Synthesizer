# 显式非零 stream epoch 配置

2026-10-30。A07 display v1.1 要求非零 stream epoch；已有音频默认从零开始
且自然回绕。新增 `RESERVE_ZERO_EPOCH` 和 `INITIAL_STREAM_EPOCH` 配置，
由唯一音频 owner `workstation_sample_rate_switch` 在初始流、成功切换与
恢复时执行。显式非零配置初始为 1、`0xffffffff → 1`；默认配置仍从 0
开始并自然回绕。相同率不改代次，失败不提交，观察器不加一或改写真实 tag。

clock domain、runtime audio、controlled composition 只透传配置。可选时钟
命令服务按同一配置相关联预期结果，并通过 feature 寄存器 bit3 公布非零策略；
实际 rate/epoch 仍只读 runtime。新选项尚未由任何 top/profile 选择。

[owner 契约](../rtl/audio/STREAM_EPOCH.md)说明 common-reset incarnation、
有限身份空间与外部对象身份边界；[机器证据](workstation_task_20261030/stream_epoch_policy.json)
包含所有 source/configuration、验证及日志哈希。

父级独立验证通过：

- 真实 switch + 官方 GW5A DCS 的全部双向切换、同率、busy、缺源、停高、
  quiesce/prefill/resume/运行故障及恢复工作负载，在默认 0、非零 1、近回绕
  `0xfffffffe` 三组均通过，包含实际跨 `0xffffffff`。
- 命令服务通过真实 APB CDC 与真实 switch，在上述三策略×三异步相位共九组
  通过；每组 146 APB 事务、最多 9 bus cycles。验证 no-op、恢复、超时锁定、
  CPU reset 中硬件继续、实际快照与回绕结果相关联。新服务 lint 零 warning。
- 完整 native DSP→final PCM→官方 DCS→I2S 的非零配置通过 20,190 物理帧，
  20,184 good／6 预期错误／20,057 非零、八次帧中切率及五次故障注入。
  最终实际 epoch 为 13（默认配置对应 12），所有物理帧仍与唯一 final PCM
  owner 的完整上下文和样本匹配。最大 render 1,184 compute clocks。
- controlled wrapper 默认／非零两配置均通过 1,070 物理帧与 1,069 显示快照、
  双率 384 FFT bins。测试将 rate 与真实物理帧逐包比较，移除了旧 fixture
  把 rate 误当 epoch 最低位的偶然假设；实际接口从不由 epoch 推算采样率。
- 默认 clock-domain 两项（三异步相位与生产监测参数）及 current sources
  十项通过；验证期间输入哈希均未变化。

本阶段没有重新综合、P&R 或实板验证；先前综合 netlist 不含本次选项。
尤其不能把 skip-zero 状态总线当成单步 Gray 计数器来跨域，现有上下文
继续使用 held payload。回退为保持默认配置，既有部署不变。
