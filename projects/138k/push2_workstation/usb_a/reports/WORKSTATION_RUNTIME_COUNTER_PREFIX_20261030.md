# Runtime 计数器 Gray 解码深度收敛

日期：2026-10-30。范围：显式 native runtime 的 `gw138k_counter_cdc` 源码与离线回归。机器证据：[runtime_counter_prefix.json](workstation_task_20261030/runtime_counter_prefix.json)。

新 BLE DDR 整机综合暴露了 `u_runtime_display/drops/sync_value` 至 producer／analysis 状态机的长组合路径。本阶段只把 Gray→binary 的 31 级串行 XOR 改为 5 级并行前缀 XOR，原 module、端口、source Gray 寄存器、`meta/sync_value` 两级同步、两侧三边沿 reset release 和目的侧组合观察完全保留，新增目的时钟延迟为 0。最高位直接使用 `sync_value[31]`，保留原实现对 Z 的四态行为。

## 生产输入与候选

新版本源位于 `rtl/migration/workstation_runtime_counter_cdc.sv`，SHA256 为 `c921ff58a2204dee35972d960a98d6820803155b89c090fdcb3d111137521f5c`。四个显式 native runtime profile 通过既有 `SOURCES/REPLACEMENTS` 选择它，保持各自原 configuration、policy 和 revision。源码／构建工具 hash 产生新的候选身份，没有复用旧候选身份。

原 `src/migration/gw138k_counter_cdc.sv` 仍以原字节暂存，SHA256 为 `1b6ff697ccd951995b7331ac483f3c7672a959a9a767465eb57d92d80f3afa8c`，其编译项明确关闭。`runtime_audio.counter_cdc` 记录新源、父源、实现和延迟；解析器同时核对 GPRJ、replacement/copy 绑定、integration 与 prepared profile 的 enabled/staged hashes。新源缺失直接失败，不回退到禁用父文件。旧 serial stage 仍显示为 `compiled_locked_serial`。未选 runtime profile 的新板、accepted full83、pinned timing85 与 resource parent 的编译选择不变。

实际完成一次全新 prepare：`custom138k-workstation-r00-no-local-panel-v1-47fbf548eef54f47`，269 项启用、593 项暂存。profile artifact SHA256 为 `255d273cbfb6159e58620162adb75fa4d7ef0d478297e5cf105b77116d5e1e68`。新 SDC 与 root277／FF 逐字一致，SHA256 `06e9739cf9b6dc73352c0dd161095d298dba32c08311c5e233bd29c02fc3f5cc`；这不代表旧 CDC 证据自动接受新 VG。

## 校验

- 精确解析真实旧／新 RTL，以 32 行 GF(2) 基矩阵证明全部 2^32 个二值输入等价；每个后缀变量恰出现一次，sequential token 前缀相同。缺高跨度、source binary、同步级旁路和新增延迟四个负例均被拒绝。
- 三组异步频率／相位进行 499／851／520 次比较，每组包含四次最终值送达、停源／停目的时钟、双停钟复位、三拍释放及回卷。单 bit X/Z、基向量与其他组合输入比较通过；native Verilator lint 零 warning。
- 源选择／隔离单测 7/7；current workstation sources 17/17；profile 单测 6 通过、14 项可选 prepared 检查跳过；实际新 prepare 的 no-local-panel 6/6、BLE DDR integration 5/5。
- 真实 PCM observation 三个相位组合通过，每次 offered72／accepted51／dropped21／checked50、default_checked63、saturation7。
- 真实末次 physical FIFO 丢包且无下一 MCLK、末次显示 mailbox 丢包且无下一 compute、两次停源、四次公共复位与 wrap 均通过；联合 controlled runtime 的 1078 physical＝1078 observed、两次实际 rate switch 和 1077 次原子显示 effect tuple 检查通过。
- 实际显示流水线 TB 通过：publications6、commits9、atomic tuples128702、waveform1024、XY131072、FFT columns1024、CDC drops60，tail cancellation、reader cancellation 与 idle-cache lease 均通过。完整新编译保留 53 项继承 warning（TIMESCALEMOD12、WIDTHTRUNC31、WIDTHEXPAND10）；按现有 runner 的范围加新 counter 审查，没有本次拥有范围的非 timescale warning，也没有 UNOPTFLAT。

完整显示 runner 仍因既存 `Native HDMI provenance checksum changed` 提前失败，原失败记录和来源未修改。实际 HDMI source SHA 为 `724f23fdbd9f97f1fb16c79f0876eff7e5c317365d737adfc9392b924a515fc4`，历史 provenance 期待 `cfa1121ee24fb9cebf95edea03639297d8e63af28d57a5cc32481d702f97980d`。上述 focused TB 使用真实显示 owner、204-bit mailbox、2048 FFT、DDR writer/reader/cache 及原 TB；不构成完整 HDMI provenance／elaboration 通过。

## 复现与后续门禁

源等价和负例：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/cdc/run_runtime_counter_cdc.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/counter-prefix-proof-fresh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_counter.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

机器证据提供四个完整 `build.py --prepare-custom-board --workstation-profile ...` argv，供合并 TF／media CDC 改动后重新 prepare；本阶段不把单一 prepare 扩称四路实际完成。focused 显示执行脚本、命令、完整 warning 文本、日志与输入 hash 位于 cache 的 `runtime-counter-prefix-display-pipeline-v1/`，精确路径／校验值在机器证据中。

源码 XOR 深度不是物理延迟或 LUT 用量。前缀重排可能改变面积、扇出和布线；新 VG 仍须核查 Gray source、同步端点、组合路径和源身份，再做综合资源、P&R、setup/hold、reset recovery/removal、CDC／PLL／功能保持及独立实板验收。本阶段未执行综合或 P&R，未产生 bitstream，未烧 SRAM／Flash，所有物理与部署接受标志为 false。

回退须选择原 serial 候选及其完整 source hashes／配置／原验收范围；仅保留禁用父文件不构成回退。冻结 baseline、vendor、历史证据与约束均未改。
