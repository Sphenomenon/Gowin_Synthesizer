# USB2 交替接入、完整传输帧与原生音频续接

日期：2026-10-27。开发验证记录，不是物理 USB／音频验收或部署记录。

## 本轮推进

在[交替接入验证](USB2_MIXED_HOTPLUG_20261027.md)基础上，保持一个生产 CPU、一个共享 USB3300 模型和一个输入 owner，继续验证 `25K → Push → 25K → Push`，不在各次连接间复位 CPU。

`sim/test_workstation_usb2_hotplug.py` 新增两个可选维度：

- `COMPLETE_FINAL_FRAME`：第一次 Push 仍在部分帧中拔出，最后一次 Push 必须重新从头传完 327680 字节，且 owner 恰好接受一次 0x30 帧提交；不是只证明重新枚举或收到了帧头。
- `AUDIO_CORE`：把输入接到实际 `gw138k_usb_controlled_audio`、会话／公共参数、DSP、帧交接、PT8211、最终输出路由和 FPC I2S；反馈使用实际 `gw138k_push_performance_uart` CDC，而不是全零状态。四次连接逐项核对 13 个默认参数提交、10 个音符实际应用、每次接入的非零串行 PCM、拔出后的 held 清零／静音以及不中断的采样节拍。

原生音频输入由 `sim/workstation_usb2_audio_inputs.py` 从显式指定、通过独立整机综合审计的候选中选择。复制被选中的 28 份编译源、递归 include 和实际 ROM 数据，不重新生成 DSP、不缩减声部／延迟环、不回落到私有历史工程。USB 组件提供的 stream CDC 与原生整机所选版本字节相同。DDR 延迟 DMA 是实际模块，只有其既有 128 KiB 环的存储响应采用行为模型，不能据此宣称验证了物理 DDR 控制器。

## 已取得的完整交替帧证据

证据根目录：

`/home/sphenicidition/.cache/fpga-usb2-mixed-audio/20261027-163324/`

`hs_1_complete_frame/hotplug_evidence.json` 和 `execution.log`：

- 实际返回 0，`complete_frames=1 real_audio=0`，`full_frame_validated=true`。
- 10 个映射事件、4 次 attach／初始化屏障、3 次 detach；第二次 25K 使用新的 PL 会话，最后一次 Push 从头完成帧。
- 仿真约 3 秒，执行报告 walltime 945.586 秒；不是仅编译通过。
- 执行日志 SHA256：`b4657b3e04a62f1be48d98ec1b08ea29867fa016af28e616523a99bef7e7640b`。
- 原始源码、仿真副本、USB 组件和 prepare 输入的哈希检查均通过。
- 极性修正后再次核对该用例当前源码、prepare 输入和组件仍匹配，见 `complete-frame-current-revalidation.json`；新极性位于此事件检查模式不实例化的原生音频装配分支，不把此用例解释为音频证明。
- Push 是合成 EP0／EP1／EP2 设备；25K 使用实际 MIDI／PL RTL，但 tile 完成由模型提供。传输完整不等于实际 Push 图像或 25K SPI 屏幕验收。

## 原生音频发现与修正

首次 HS／FS 原生音频运行在 48000 个采样 tick 时均已提交 3 个音符、完成一次默认参数初始化，但独立串行解码仍是 `serial_nonzero=0`。检查发现实际新板装配把 `pa_en` 直接接到 `workstation_fpc_audio.enable_i`：

- 实际 `pt8211_tx` 的 `pa_en` 是旧 NS4263 **高电平关断**语义，预热后变低。
- FPC 的 `enable_i` 是**高电平允许**语义；直接连接会在正常播放阶段把目标增益置零并保持 SMUTE。
- 修正只在共享顶层的 `WORKSTATION_CUSTOM_138K` 分支反相，即 `.enable_i(!pa_en)`；旧板输出及非新板预处理 token 不变。不改 ULPI 球位、锁定网表、18-bit 事件或公共参数权威点。
- 仿真装配同步采用相同极性。增加 held 音符持续 4096 帧没有非零串行 PCM 的显式失败检查，不再让这种阻断等待完整长仿真超时。

确认根因后，仅终止了本任务的两个错误配置仿真进程。原证据保留：`hs_1_audio`／`hs_0_audio` 均记录返回 -15、`timed_out=false`、音频验证为 false；`polarity-diagnosis.json` 记录准确命令、PID 和终止原因。它们不是通过的回归，也不是因观察超时而重启。

## 新候选与验证状态

修正后独立输出：

`/home/sphenicidition/.cache/fpga-usb2-mixed-audio/20261027-165544-polarity-fixed/`

通过现有 `build.py --prepare-custom-board` 从三份哈希锁定网表和资源父配置重建。该输出是新的开发候选，不复用旧综合网表作为新接线的证明，不更新任何 accepted／latest／部署身份。配置标签仍是开发配置 `custom138k-native-integration-20261027-a26`；具体候选由此独立输出及输入／产物哈希区分，不是已接受发布身份。

新候选已完成实际 Gowin 综合，随后独立 `workstation_custom_board_audit.py` 返回 0。综合资源口径为 Register 54185、Lut 73426、Alu 15284、Bsram 272、Ssram 419、DSP 46／41／45，不是物理 BSRAM／P&R 验收计数。`electrical_blocked=false`，但 `hardware_tested=false`、`deployment_allowed=false`、`release_ready=false`，没有生成或部署位流。

候选身份：

| 文件 | SHA256 |
| --- | --- |
| `native/integration_inputs.json` | `320db16a44053215ce4083c570045e4e564590bd3ae94743f54f6cd27b2b4282` |
| 原生共享顶层 | `004200b50a1705ba3bde84dd5a42a31460b904fcc9bbba0f766d037c2a09c2dd` |
| 新综合 `.vg` | `196aacb7bb2ea537c491f6173e0e6941ed65c4d8c7e30a3408e0d43be468ccd8` |
| `native/synthesis.log` | `ee201e5b51866bd6df19d514e2949fdb1e8342a2c83485500527295806e05d05` |
| `audit.json` | `21f76a4b51fe9f53bdc614c80013c8abb30b3145a07b1b27cfc8de9312b4ccf6` |

`polarity-input-comparison.json` 证明 230 个直接选择文件的列表和顺序保持；不能据此宣称完整编译闭包字节相同：递归 include 的共享顶层及被禁用的父配置副本有同一处使能反相，另有 BLE patch 文件名的候选绝对路径变化，而实际 patch ROM 字节不变。约束、其它 staged 输入保持。旧候选的审计已按预期拒绝，错误为共享顶层 source snapshot changed，见 `old-candidate-audit.stderr`。

该阶段完成 19 项针对性测试：音频输入选择的 5 项正／负例、accepted 来源边界的 10 项、FPC 音量／I2S 的 2 项、旧板 token 保持和新板 prepare／反相接线的 2 项，均通过。修正后的 HS／FS 原生音频交替长仿真从上述候选启动，证据子目录为 `hs_1_audio`／`hs_0_audio`，但未通过，不能把完整传输帧用例算作真实音频通过。

两者均通过首次断开后的 held／串行静音与采样连续性检查，进入第二次默认参数初始化。48000 个采样 tick 时，HS 已解码到 466 个非零立体声帧，FS 为 9067 个；这证明极性修正恢复了实际串行输出，而不是只有事件 ACK。随后两者停留在首个 Push 的 4 个已提交音符。经只读诊断确认 Note Off 被映射器抑制后，显式终止这两个失败运行；两者最终返回码均为 `-15`、`timed_out=false`、`real_audio_validated=false`，不是观察等待超时，也不再运行。诊断证据为该目录的 `feedback-fence-diagnosis.json`。

## 第二个根因：延迟 PANIC 反馈覆盖新持音

原生输入原先消费 UART 遥测 CDC 的 `push_snapshot`，再进入输入 owner 的反馈 CDC。第一次 CDC 每 65536 个音频时钟采样，第二次每 4096 个参考时钟采样；owner 的两次预热确认可能只是同一份旧的上游快照。接入 PANIC 的 epoch 迟到后清除了已经接受新 Note On 的本地 held 状态，随后合法 Note Off 在映射阶段被抑制，真实音频核心仍持音。实际 HS 诊断中，两包 MIDI 均已 ACK，owner 共受理 5 次演奏写入，但仅 4 个音符提交；显示已收到 `0x50000` 字节，不是显示或 DSP 卡死。

修正只改变反馈采样边界：`workstation_usb2_input` 新增默认 0 的 `FEEDBACK_AUDIO_DOMAIN`，保留参考域兼容接口；新板原生组合根显式设为 1，将 `u_managed` 的音频域 `performance_words` 直接接到原有 owner 反馈 mailbox，其 source clock/reset 使用 `clk_audio`／`audio_reset_n`。UART 遥测独立保留，不新增参数权威、held 副本或 18-bit 事件字段。`snap_sequence` 是软件写入的快照字段，不能当硬件心跳或新鲜度序列。

快速回归 `sim/test_workstation_usb2_feedback.py` 使用真实 owner／CDC 和建模音频状态：旧双级链路受理 3 个 MMIO 写入但只映射 1 个音符、核心 held 未释放；直接音频域链路同样受理 3 个写入，映射完整 On／Off 2 个音符、双方 held 清零。两者均有断言；这是刻意复现旧故障的负控，不是真实 CPU／DSP 长回归替代品。首份证据：`~/.cache/fpga-usb2-feedback-fence/20261027-180241/fence/feedback_evidence.json`。

独立综合网表审计新增 mailbox 实际 CLK／寄存器库存检查：source 必须是 `audio_76m8`，destination 必须是 `usb_48m`，错误源域、目的域和缺少 held 寄存器均拒绝。第一次新综合还准确暴露了旧 reset 审计仍将 `feedback/source_release` 固定为 50 MHz；其失败证据保留在 `20261027-180649-direct-audio/`。审计现对 a26 显式选择音频反馈源域，对历史配置保留参考域默认；三阶段释放、CE、CLEAR、D→Q 拓扑和首级扇出检查不变，SDC 不放宽。

据第一次真实新综合，精确资源快照为 Register 54184、LUT 73423、ALU 15284、BSRAM 等价 272、SSRAM 419、DSP 46／41／45；综合用例更新为该精确快照，而非删除断言或改成宽松范围。特性、资源层次一致性及损坏负例仍须全部执行；不是物理 BSRAM 或时序通过。修改审计工具后重新 prepare／综合新候选，不改写旧候选 manifest 来绕过来源检查。

最终快速回归共 27 项通过（含原生 timing 7 项、反馈负控与严格域／库存检查 2 项、accepted 来源 10 项、音频来源 5 项、FPC 2 项、service adapter 1 项）。旁路另有引脚 32 项、新板／实现准备 26 项通过；pinout-only 的 101 个现有端口、retired／保留脚、HDMI／BLE 和生成 CST 与 HEAD 的旧解析结果逐项及逐字比较保持，不拿扩展 LCD／BLE 的 native integration 端口集合做这个比较。

第二份候选 `20261027-182611-clock-audit` 的 reset 审计通过，新增 mailbox 库存检查发现综合网表使用 `destination_data_*`／`destination_valid_*`，不是顶层导线名 `snapshot_*`。检查改为严格覆盖实际寄存器名，并补缺少目的数据、valid 和未知寄存器负例；实际网表预检为源 158 个、目的 160 个寄存器，时钟分别是 `audio_clk`／`usb_clk`。预检不是全候选审计通过；第二份候选的完整审计保持失败。工具也属于锁定 recipe，修正后再次新建 `~/.cache/fpga-usb2-feedback-fence/20261027-184109-verified-inventory/`，未覆盖前两份失败证据。最新完整综合、独立审计、损坏负例及 HS／FS 真实串行音频长回归均已取得最终通过证据；这些都是离线证据，不是硬件验收。

最新候选仍使用显式开发配置 `custom138k-native-integration-20261027-a26`／`explicit_native_board_on_resource_timing`，允许 HS；626 项源码／工具完整输入哈希见 manifest，板外三份锁定网表哈希与原配置完全一致。来源和产物身份另存该目录 `candidate-identities.json`：

| 文件 | SHA256 |
| --- | --- |
| `native/integration_inputs.json` | `17d6e12be041c4c311636f522dbb4a7a85f731c55e23ee9e5efa486fc572078f` |
| 原生共享顶层 | `cf5d89d3a6fd76e0406275500322233c42d8a010290695d8eef50f498716aa6d` |
| `workstation_usb2_input.sv` | `8b5617e7e173e7b3c71ecd5ac8deaeaf2620dfecd6f10bf8fe8dacd924b3f206` |
| 新综合 `.vg` | `e791bd7410ee1027fea0a63e109797fca81bc0bd83aa7776e28e94244bbde988` |
| 综合资源报告 | `28930fa2422f45b07fe546b413b872e935d2f653215114f39dca9417f6de5837` |
| `native/synthesis.log` | `b8a53935f6c20d9efaa0158c38052ecc025a17b4469d3e5b97322408612b128e` |
| 独立 `audit.json` | `92e48e135b3c099c55fc1c2f7e4bb2f12fca06ca566ad50dca471f2f1e5a3617` |

本候选没有位流身份，`bitstream_sha256=null`；不是已接受发布，不继承早期配置的物理证据。`release_ready=false`、`deployment_allowed=false`，未上板或写入 SRAM／Flash，回退产物和原部署证据不变。

完整综合损坏负例专项随后通过，1/1、204.036 秒，见 `custom-synthesis-final.log`。此前全套运行准确暴露另一处旧测试夹具：UART／shared CDC 负例及额外 SDC 的配置列表只列到 a24，a26 会漏掉 LCD／shared CDC／timing／Flash 约束，导致 DDR 时钟破坏负例先撞上 SDC 全文不一致。现补列 a25／a26、区分 a20 timing 与 a21 起的 Flash 约束，并先用未破坏网表验证完整时钟审计等于正常结果，再做特定破坏。没有修改实际 SDC、时钟或 false path；原先遗漏的 UART／shared CDC 负例也重新执行，157 条约束／145 个已解析 selector／13 个 opaque DDR selector 计数保持。最终单次 27 项整套重跑全绿，651.929 秒，见 `custom-board-all-green.log`；其后的独立 `audit-final.json` 退出 0。引脚回归 32/32 与追加针对性回归 27/27 同样通过，汇总见 `final-validation.json`。

## HS／FS 真实音频交替长回归最终通过

最新候选下两次实际执行均返回 0、`timed_out=false`，`full_frame_validated=true`、`real_audio_validated=true`。单个真实生产 CPU 不在连接之间复位，依次 25K→Push→25K→Push；两者都检查 10 个普通事件、4 次接入／初始化完成、3 次断开和新 PL 会话，最后完整 Push 传输帧 327680 字节。4 次连接均取得真实 DSP 经 FPC I2S 独立解码的非零音频，3 个断开窗口的静音／held 清除及 48 kHz 采样连续性均通过，不再只检查输入 ACK。

| 用例 | sample ticks | 串行帧 | 非零串行帧 | 执行墙钟 | execution.log SHA256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `hs_1_audio` | 139294 | 139285 | 39838 | 1577.401 s | `c66a3d5ccd981b46fa34c4d135600ac3e416ade475fb3a65a91d9cce705970fb` |
| `hs_0_audio` | 142665 | 142656 | 62376 | 1604.603 s | `761ccfb8616bdd5a6cd3f60f6b2fed4e0db6955d1c27da6f36bf8940c68fe777` |

两项 unittest 各 1/1 通过，总时长含准备／编译分别 1618.182 s／1646.568 s。每项的原始输入、仿真副本、component、准备清单、原生音频输入及其副本、626 项 native source snapshot 和 BLE 输入不变性检查均为 true。音频来自独立审计候选中逐字相同的 28 个编译源和 57 项选中源／递归依赖／ROM 身份。延迟存储仍为既有 128 KiB ring 模型，不是物理 DDR 控制器；Push 为 EP0／EP1／EP2 合成 peer，25K 使用实际 MIDI／PL RTL 加 tile 完成模型，不是物理设备或显示图像验收。所有 hardware／release／deployment 标志保持 false。

当前 bench 的 HS 完整传输帧混合热插拔另已重跑通过：`20261027-182611-clock-audit/hs_1_complete_frame/`，实际返回 0，单 CPU 不复位、4 次连接／3 次断开、10 个普通音符事件、最终完整 Push 帧；`full_frame_validated=true`、`real_audio_validated=false`，所有输入不变性检查均为 true。执行约 3 秒模拟时间、705.751 秒墙钟；日志 SHA256 为 `3af29b40ac9d1e92ef25388f7d23f39bba937d1d1a85125cd60c4334b7fdcfea`。该用例仍是事件检查 sink，不替代 DSP／串行音频。

复现原生音频长仿真时，显式设置 `GW138K_USB2_AUDIO_INPUT` 为完成独立审计的候选根目录，`GW138K_USB2_HOTPLUG_EVIDENCE` 指向新的证据目录，并使用有空间的 `TMPDIR`，运行：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a/sim python3 -m unittest -v \
  test_workstation_usb2_hotplug.MixedHotplug.test_high_speed_alternating_devices_with_real_serial_audio \
  test_workstation_usb2_hotplug.MixedHotplug.test_full_speed_alternating_devices_with_real_serial_audio
```

未提供显式音频候选时，这两个长用例会标为 skip；这不构成原生音频验证通过。每次输出拒绝覆盖，实际运行日志实时写入；超时、返回码、完整帧、真实音频以及输入／副本不变性分别记录。

## 仍未完成

- 本项电气实测仍是 USB3300 ULPI IO 是否确由 3V3 供电；`no_voltage_domain_conflict_detected` 不是电气或硬件验收。
- 新候选仍需独立 P&R、时序／CDC／PLL／物理资源检查和实际 25K／Push 热插拔声画验收，不能继承历史候选的物理证据。
- 未操作板卡、未写 SRAM／Flash；保留现有已验收部署作为回退，不把新开发候选自动部署到板上。热插拔源码与离线验证已完成，实板收尾仍未完成。
