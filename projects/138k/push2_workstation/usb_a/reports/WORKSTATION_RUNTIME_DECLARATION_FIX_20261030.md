# Native runtime 声明顺序修复

2026-10-30。真实 Gowin component 综合虽然退出 0，却报告 `core_ce` 和
`local_history_clear` 已隐式声明，以及 FDN generate 内的 `local_history_clear`
无驱动。Verilator 的解析没有暴露这个工具差异；旧 netlist 不能作为功能验收。

将 event workstation 的 `core_ce` 和 Reverb 的三个 config/history wire 移到
首次实例使用之前，保持所有方程、状态和接口不变。Reverb provenance 追加两个
精确可逆的移动步骤，仍能逐字节还原原 prepared SHA。未改 frozen baseline。

父级独立回归已通过：Reverb 六项（48k 逐周期等价、两率三秒 impulse 和独立模型、
切换及全部 RAM clear/write-tail 情形），current sources 十项，render service 的
48,652 请求／响应及 48,644 帧独立效果模型比较，完整音频 20,190 物理帧，含
八次帧中切率、真实 DSP、owner6 DDR 模型、官方 DCS 和 I2S。验证输入没有漂移。
修后完整音频 offline source-set 为
`108192b1849b1f81a9b412658e2d027ddd37257375122d2c45d85d887d802eb0`。

详细输入与回归身份见
[机器记录](workstation_task_20261030/runtime_declaration_fix.json)。旧综合快照保留在
本机 cache `runtime-audio-component-synth-29d0083e`，不能覆写或沿用其身份。
接下来用新快照综合，核对两类 warning 和实际 RAM clear 网络。

本阶段为源码与离线回归，尚非修后综合、物理时序、整机或板级接受；
没有切换 top/profile，也未操作 SRAM 或 Flash。回退为撤销此源提交，
旧候选与既有部署身份不变。
