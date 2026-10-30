# USB2 owner 音频复位链审计

`workstation_usb2_owner_reset.py` 只审核新增三拍链的来源、FF 结构、完整 Q 扇出和单行 CLEAR 对象。独立入口可显式选择 no-CNN、R00 或 `custom138k-workstation-r00-no-local-panel-v1`；成功不接受 R00 录音 CDC、整机 shared CDC、完整 reset 或物理时序。

runtime 安装层独立追加下列一行，不改冻结父 SDC、`shared_constraints()` 的 157→105 重建或旧 no-CNN 的 88 条 shared scope：

```tcl
set_false_path -to [get_pins {u_native_usb/audio_owner_reset.release_q_0_s*/CLEAR u_native_usb/audio_owner_reset.release_q_1_s*/CLEAR u_native_usb/audio_owner_reset.release_q_2_s*/CLEAR}]
```

每个选择器必须单独命中一个对应 FF 的 CLEAR；范围不能包含整个 wrapper、feedback_divider、D 或 CE。三 FF 的共同异步 CLEAR 由 `!(usb_reset_n && reset_n && memory_guard_started)` 产生。前两级 Q 只能分别驱动下一级 D；末级的逻辑组合扇出是 12 个音频反馈计数 FF，以及 `cpu_reset_n` 共同限定的 event/audio/feedback release 链。检查器逐项声明这些端点及其 Boolean 断言函数，不能根据当前扇出反推“允许”清单。级间 D 和末级到功能 CLEAR 继续接受时序分析；新增例外只覆盖新同步链自身。

两个 CLEAR 边界必须分别判定：

| 边界 | 源语义与约束 | 尚未证明 |
|---|---|---|
| raw qualified→三颗 `release_q` 自身 CLEAR | 原始条件可异步断言、异步撤销，与 audio 时钟没有固定相位；只对三颗接收链自身 CLEAR 加例外 | 最小脉宽、组合断言毛刺／flight、物理复位裕量 |
| `release_q[2].Q`→12 颗 `feedback_divider` 功能 CLEAR | 末级由 audio 边沿释放，目的端也在 audio 域；保留真实 recovery/removal，不允许追加 cut 或宽松 delay | 实际布线后的 recovery 和 removal 分项结果 |

前一边界可能报告异步撤销相位造成的 recovery/removal 违例，不能与后一边界的功能恢复／移除混为一个总 `passed`。报告以 `timing_boundaries` 分开记录例外端点和必须 timed 的端点，两个物理接受字段初值均为 false。两条级间 Q→D 保持 timed，不自动继承其他链的 2 ns max-delay 预算；还需单独核实级间放置与亚稳态裕量。Q2 经 `cpu_reset_n` 限定后到另外 11 颗既有 release 链的 CLEAR 沿用既有策略，本检查不重新接受这些链或其下游功能复位。

原约束已对 `cpu_release_q`、`session_release_q`、`feedback_release_q` 使用各自 CLEAR 的局部例外；新链按同一接收边界增加独立行。Gowin《设计时序约束用户指南》SUG940-2.0.1 第 67 页（PDF 第 77 页）的 `set_false_path` 规则说明，默认会关闭 setup、hold、recovery、removal；`-setup` 包含 recovery，`-hold` 包含 removal。因此更换为 `-setup`／`-hold` 不能解决范围问题，必须将例外精确限定为三颗接收链自身 CLEAR，保留功能 CLEAR 的物理检查。

RTL 无声明初值，异步断言后为 `000`，三个实际 audio 边沿后 `001→011→111`。Gowin DFFCE 的 INIT 参数可显式为 0，也可按其原语默认值 0 省略；输出记录采用哪种来源。INIT=1 或未知值拒绝。本机官方 gw5a `prim_sim.v` 的 DFFCE（第 471–496 行）及 `prim_tsim.v`（第 794–819 行）均定义 `INIT=1'b0` 和异步高有效 CLEAR。默认参数语义不证明板上启动或物理脉宽。

Gowin 新 VG 使用点号 generate 名，并将 Q2 通过 escaped `[2:2]` formal 传入 owner。独立的 `OwnerResetNetlist` 只适配 `u_native_usb/input_owner` 的这一个确切 formal、位号和范围；不改共享解析器、VG 字节或默认 shared 审计。位号、范围、绑定或路径变化都必须重新核查。

新 prepare 与综合结束后运行：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_usb2_owner_reset.py \
  --project /absolute/new/workstation/Prj1 \
  --synthesis-evidence /absolute/new/runtime_synthesis_evidence/process.json \
  --profile custom138k-workstation-r00-v1 \
  --output /absolute/new/usb2-owner-reset-audit.json
```

该入口核对实际已安装 SDC，不补写缺失约束。准备文件必须等于被审核的版本化源码；综合输入及 VG 在审计前后保持封印一致。也可将 `audit_reset_structure(n, graph, sdc)` 用作明确的对象级检查，但测试夹具或内存中拼接的 SDC 不代表实际安装通过。

no-local-panel 身份固定来源为 `boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json`，配置是现 R00 加 `local_panel_policy=disabled_local_lcd_touch_v1`，canonical JSON 配置 SHA-256 为 `fe57acb99ab96c773148a10bd41401eaa55ca069f2ff9d1def1daa254dd5d241`。该身份允许 prepared descriptor 使用已封存的 64 位小写十六进制历史摘要，不把后来更新 source locks 的整个 descriptor 文件与旧版本强行等同；配置和路径仍须精确一致，公共审计仍需自己的完整综合封印、真实 VG、已安装 SDC 和源码身份。旧 no-CNN／R00 validator 规则保持。b9a2 原 R00 不能改标签继承成 no-local-panel，通过策略夹具不等于新网表或面板退休验收。

no-CNN 整机 shared 审计可另外指定 `--precision-profile runtime-no-cnn-v1 --usb2-owner-reset`。默认不开启追加检查；generic 不接受这个 flag，R00 继续不属于整机 shared 精确范围。独立 reset API 是 R00 检查本条链的入口，不能据此跳过录音 CDC。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_owner_reset.py
```

回归包含真实源码变异、明确的合成网表夹具及其 D/CLK/CE/CLEAR/INIT/扇出/SDC 负控。完整 shared 的旧 525 实际 VG 回归单独执行。源码已有短断言和停高／停低仿真，仍须分别核实实际原语最小脉宽、组合断言毛刺与 flight、级间放置与亚稳态裕量、末级至所有功能 CLEAR 的 recovery/removal，以及 FIFO 写侧等独立复位缺口。所有物理与发布门禁保持 false。
