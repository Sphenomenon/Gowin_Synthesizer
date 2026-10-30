# 当前 HDMI owner8 来源的显式校验入口

日期：2026-10-30。机器记录：[hdmi_recording_owner8_provenance.json](workstation_task_20261030/hdmi_recording_owner8_provenance.json)。本阶段只维护离线回归入口，不改变生产 RTL、构建选择、四个 profile 或历史接受状态。

## 失败根因

`524f533` 在 `workstation_hdmi_display.sv` 加入两处录音条件编译：`WORKSTATION_RECORDING_DDR` 的接口，以及实际 owner8 DDR arbiter。该源码 SHA256 从 `cfa1121ee24fb9cebf95edea03639297d8e63af28d57a5cc32481d702f97980d` 变为 `724f23fdbd9f97f1fb16c79f0876eff7e5c317365d737adfc9392b924a515fc4`。原 provenance 最后更新于 `84206b4`，仍描述此前 native composition，因此旧完整 runner 的 checksum gate 正确拒绝当前源码；不是计数器优化引入的错误。

原 provenance 是包含精确变换的来源记录，完整 runner 原来按记录逆转、核验 parent 和 pre-runtime 输入；本次不修改其 native 预期、exact changes、parent 或任何历史报告。原 manifest SHA256 仍为 `2da2802f233a7286d7f728d48b62b4bd6327a954ab833b1784ede035e3924426`。

## 显式桥接与严格失败

新入口必须显式指定 `--hdmi-adaptation recording_owner8_v1`。独立 manifest `rtl/workstation/workstation_hdmi_display.recording_owner8_adaptation.json` 固定原／当前 source、原 provenance、来源提交和两处 exact changes；manifest SHA256 为 `10a442a465bf51b23a332e8deb3742dc392fb347b99ffefd9ca3dd7fc0883ded`。helper 同时固定原 manifest 与新 manifest 的字节身份，不接受修改预期值来消除漂移。

校验先从当前 724f 源精确逆转两处 owner8 修改至 cfa1，再按原 provenance 的 19 处逆变换还原 pre-runtime `607f30dd...` 和 parent `900914bb...`。每次正／逆锚点必须唯一，变换必须逐字往返。宏关闭时仍与 pre-runtime 的 3,210 个 HDL tokens 完全相同。

生产 RTL 继续直接编译当前版本。桥接只在内存中检查来源，输出目录只写原有 pre-runtime 测试夹具；没有把生成或改写的 HDMI 文件接入生产。未给参数时仍走旧 native checksum gate，当前 724f 源被精确拒绝，独立失败证据已保留。

## 实际完整回归

适配后的完整 runner 已通过，身份 `native-runtime-display-offline-v1-b99640485f53f966`，58 项实际输入 hash 均在结束后复核一致：

- default 与 runtime 的官方 GW5A 完整 HDMI elaboration 保留；新增 runtime＋owner8 模式，连接当前录音接口并编入实际 prepared queue／core，核对 GPRJ 启用项、profile hashes 和 current owner 字节。
- 实际 elaborated owner 为 `workstation_recording_ddr_client_queues`／`workstation_recording_ddr_arbiter_pipeline`，两层 RECORDING_ENABLE=1，九个真实 `basic_pitch_ddr_client_slot`。没有用 dummy arbiter 或仅用 token 比较替代 owner8 elaboration。
- 三模式继续检查单一 FFT owner、两页 analysis 开启、runtime reader 双 cache bank 与当前 provider 来源。
- 真实显示流水线通过 128702 次原子 tuple、1024 波形点、131072 XY 像素、1024 FFT 列及 60 次 CDC 丢包，尾部／reader 取消和 idle-cache lease 均通过。
- Verilator 的 53 项继承 warning 保留（timescale12、截断31、扩展10）；owned 非 timescale warning 和 UNOPTFLAT 均为零。未放宽原告警范围，新 counter 也纳入 owned 检查。

八个定向单测包含 30 项拒绝检查：显式策略要求、source／原 manifest／适配 manifest 漂移、两处缺失／重复／反向重复锚点、禁用／缺少／重复／错误 GPRJ owner，以及 prepared／current／profile 的独立 source 身份。完整 default 命令也实跑并保留预期失败。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_hdmi_provenance.py
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_display_runtime.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-counter-prefix-prepare-v1/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/hdmi-owner8-review-fresh \
  --hdmi-adaptation recording_owner8_v1
```

## 退出与接受边界

退出方式是另行审查一个明确拥有 owner8 及后续变更的 canonical native provenance chain，再退役本命名桥接；原 manifest 与历史证据继续留存。在此之前，新 source 或 manifest 漂移一律拒绝，不自动选择“最新”。其他历史 provenance consumer 未被隐式迁移。

本次只证明 source provenance、当前接口与实际模块 elaboration，以及既有显示功能回归。owner8 的录音事务、完整 DDR 业务行为、物理资源／CDC／PLL／时序及实板声画验收继续依各自候选证据，不能由 elaboration 继承。未执行综合／P&R，未产生位流，未烧 SRAM／Flash，未改变部署或硬件接受状态。
