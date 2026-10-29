# 输出时基驱动的 PCM 跨域桥检查点

日期：2026-10-30。新增 `rtl/audio/workstation_pcm_frame_bridge.sv`，将实际串行器的逐 slot 请求送入独立计算时钟域，再原子返回同一 rate／epoch／sequence 的 PCM。此阶段仅验证通道与有界渲染模型，尚未接真实 DSP、生产 profile 或硬件；A03／A05／A06 整项仍未完成。

桥使用一个请求邮箱、一个执行中的 render 和一个返回邮箱，不以独立 1600-cycle 节拍自由生产。新 slot 不能覆盖旧 render 身份；请求满、返回丢弃、quiesce 取消和非预期 done 均有分域的全局复位／32-bit 饱和计数。串行器局部复位不清全局握手，停钟期间计算域继续保留旧身份；返回必须待源时钟恢复后明确消费，不能提前确认排空。契约见 [PCM_FRAME_CONTRACT.md](../rtl/audio/PCM_FRAME_CONTRACT.md)。

验证命令为 `python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_pcm_frame_bridge.py`。真实 I2S 串行器与 76.8 MHz 计算模型分域运行，两种独立初相／±200 ppm 偏差均通过；BCK 上升沿独立逐 bit 解码左右 PCM，并核对完成 tap、采样率、epoch 与序号。所有源码及测试输入 SHA256、完整输出、账本和数值见 [pcm_frame_bridge.json](workstation_task_20261030/pcm_frame_bridge.json)。`verilator --lint-only -Wall` 无告警，Python 编译与 diff 检查通过。

| 模式 | 正常完整帧／每次运行 | 最短 render 间隔（计算周期） | 最大请求→返回 | 物理帧周期 |
|---|---:|---:|---:|---:|
| 48k，慢参考 | 160，零欠载 | 1600 | 18.721191 µs | 20.837500 µs |
| 48k，快参考 | 160，零欠载 | 1599 | 18.713704 µs | 20.829167 µs |
| 44.1k，慢参考 | 160，零欠载 | 1741 | 18.664154 µs | 22.680490 µs |
| 44.1k，快参考 | 160，零欠载 | 1741 | 18.656689 µs | 22.671420 µs |

正常模型每 render 为 1400–1416 周期，不能作为真实引擎预算。附加场景包括故意 3600-cycle 迟到、返回背压 2300 MCLK、renderer not-ready 积压 1100 MCLK、8000-cycle 慢渲染时 quiesce、MCLK 停高且仅串行局部复位、恢复后丢弃旧 reply、新 epoch 重启及非预期 done。两次运行各有 accepted407＝render401＋取消请求6；render401＝已交付399＋返回丢弃1＋取消 render1。请求丢弃10、显式 error 零帧20、正确 PCM 帧388、非预期 done1，均为故意施压结果，不记作正常无损输出。

真实模块所需的最坏计算延迟、最终音源选择／主音量、PANIC 内部流水排空、两率 DSP 系数与历史、真实 DCS 联合切换、路由后 CDC／时序仍待继续。输出出现 deadline 时明确零/error 与迟到拒绝，不靠重复旧样本吸收频差。回退仅需不将本独立模块选入组合；当前已接受来源、板上内容、SRAM 和 Flash 均未因该阶段改变。
