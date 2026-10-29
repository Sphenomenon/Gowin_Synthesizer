# USB2：同一生产 CPU 下的 25K／Push 交替接入

日期：2026-10-27。离线验证身份：`usb2-mixed-hotplug-20261027-dev3`。本记录补充[会话围栏](USB2_HOTPLUG_SESSION_FENCE_20261027.md)和[Push peer](USB2_HOTPLUG_PUSH_PEER_20261027.md)两项记录，不是发布候选或硬件验收。

## 输入身份与范围

工作区 HEAD 核对为 `a579eec259a0190d45abcc7e4c0bd4a0e7b5df15` 加列出的本地差异。生产 RTL、业务固件、锁定基线、25K／vendor 原字节和板级约束本轮均未更改；新增交替 bench／测试入口，并为原 Push bench 增加完整帧模式。具体输入由各场景的组件 manifest、ROM、仿真源哈希和实际日志绑定，不以 HEAD、latest 或并行任务产物替代。

| 来源 | SHA256 |
|---|---|
| `sim/test_workstation_usb2_hotplug.py` | `0d7d29926abdfafe75a52f774cf419c510f3bb40009339bdde67a4f8f36c08f7` |
| `sim/usb2/tb_workstation_usb2_mixed_hotplug.sv` | `a99ea9fee23b4fced997ccfa9dd0e418057aeb5d558f26abe643cc330bf3b57f` |
| `sim/test_workstation_usb2_push.py` | `1d40106726e90c93a4d9eb7a2755396417bffa27992198261adc5a5ce92ea379` |
| `sim/usb2/tb_workstation_usb2_input_push.sv` | `7190ea2f002b79bbd46ba2d202b86f9711862b062f05eb886133536c339b2d21` |

仍用 `prepare(... firmware_profile='workstation', component='workstation-input')`。HS 允许协商，FS 显式关闭 HS；音频接口保持原 18-bit 格式。交替场景只实例化一个生产 CPU／USB2 主机／USB3300 模型和原 owner／FIFO／CDC，peer 在同一口轮流接入，不是四次各自冷启动的仿真，也不表示两个设备同时连接。

25K peer 使用实际 `midi_usb_device`、生成描述符和 `panel_display_endpoint`，MIDI 从真实设备端接口注入，LCD tile 完成仍为模型。Push peer 沿用仿真专用 EP0／EP1／EP2 实现与合成描述符，不能称作真实 Push 固件或实物设备。主机不使用 C mock 替代 USB 枚举和传输。

## 交替场景

单次执行依次完成 25K → Push → 25K → Push，检查：

- 四次从地址 0 重新枚举到地址 1，原 owner 接入寄存器按设备类型切换 `00=7`／`00=1`；CPU 释放后不再复位。
- 每轮接入均收到带公共默认初始化标志的 attach 和初始化屏障，共四次；三次拔线经实际主机会话失效、owner 断开和 audio 生命周期交付，不以固件返回值冒充断开。
- 两种模式的 owner 写入各五次，audio 端精确收到十个既有映射事件。25K 保留普通力度，Push 保留既有 `pad_force` 映射；持音拔线后不补播旧输入，Push 的同一 pad 再接入可再次触发。
- 两次 25K 均从新 PL session 开始，至少交付前两个正确 tile，坐标重新从 0／62 开始；第二次 session 不复用第一次值，不向 MIDI OUT 泄漏 PL。
- Push 两次均重新发送屏幕 header 和至少 1024 字节像素；第一次部分帧期间再注入按键，实际 CPU 继续轮询 MIDI。该交替场景没有等待完整 Push 帧。
- audio 接收端施加背压，并检查无取消时的 valid／数据稳定性；这仍是事件检查器，不是真实 DSP、公共参数执行端或串行 DAC。

HS／FS 实际执行均通过：HS 结束于约 2.3 秒仿真时间，实际耗时 612.893 秒；FS 为约 1.9 秒／569.319 秒。每种速度都在同一个持续运行的 CPU 内完成四次交替，不把两种速度的独立执行当成动态切速验证。

| 交替场景 | 结果 | 执行日志 SHA256 |
|---|---|---|
| HS | PASS，10 events／4 attaches／4 barriers／3 detaches | `b1e421e0e51aecc8e9842409c8ad9f2b6712276be2c48a7990f75d1ee1403199` |
| FS | PASS，10 events／4 attaches／4 barriers／3 detaches | `6e5550fa531a022987c162be12899ef0037a123fd5632162bf4a865ee7af5cd8` |

本机证据根目录：`/home/sphenicidition/.cache/fpga-usb2-hotplug/20261027-152415/`，分别使用 `hs_1`／`hs_0`，含 `hotplug_evidence.json`、完整仿真暂存源、ROM 和编译／执行日志。

## 重连后的完整 Push 传输帧

独立 Push bench 新增 `COMPLETE_FINAL_FRAME=1` 模式。第一次接入仅发送部分帧，在 pad 37 保持按下时拔线，明确断言尚无帧完成提交；重连后再 On／Off 同一 pad，等待一个新的正确 header、327680 字节像素及生产固件的 `0x30` 帧完成提交，且 header 没有中途重新开始。

HS／FS 均实际通过：完整传输帧为 16＋327680＝327696 字节，peer 按 USB CRC、MPS、DATA toggle、帧头和长度检查，生产 CPU 仅在完整发送后提交一次帧完成。该测试不比较独立像素图像参考，不证明真实屏幕的颜色、缓冲交换或恢复时间。

| 完整帧场景 | 结果 | 执行日志 SHA256 |
|---|---|---|
| HS | PASS，`complete_frames=1` | `c914ec27e2979bb909872a0cfaf5be416caa936fc43186a8e06dcf927303a864` |
| FS | PASS，`complete_frames=1` | `aeea7649d997f7c54ca4f894450fca6b14e24130ba4e9520c4ba91f0822ba86d` |

本机证据根目录：`/home/sphenicidition/.cache/fpga-usb2-push-frame/20261027-152612/`。完整帧使用 `hs_1_complete_frame`／`hs_0_complete_frame`，原 HS／FS 部分帧回归使用 `hs_1`／`hs_0`。HS 完整帧的组件 manifest SHA256 为 `a3e7f37241973d056e8886da01b2735e1e6dc1cad4f105dde2d3cb03d11063e8`，ROM 为 `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457`，与本轮 HS 交替场景相同。

FS 两类场景的组件 manifest SHA256 均为 `384ab5818e933ecf33d53b9ba70591b0aa629afeaed3a60c882ffada701e3cd9`，ROM 为 `80a3415b6c89de06f359b268e14b7e826c14f6dd34ea54ddad4739ecf422aa41`。两个原部分帧回归也实际通过，HS／FS 执行日志 SHA256 分别为 `c20ad0caa9d7e0977074be0b372c609f6a6cf5d1256e195c396de94393dde4aa`／`93a2ba3b0242662411fcd031d7b7c0e6f6c00c36ac3852e9131b7e78ea5d358f`。六个 CPU 场景的原始源、仿真暂存副本、组件暂存输入、prepare 输入四项一致性检查均为 true，实际执行均退出 0。

完整帧验证仅将该场景的 `full_frame_validated` 置为 true；`hardware_tested`、`deployment_allowed`、`release_ready` 仍为 false。交替场景的 `full_frame_validated` 仍为 false；不能拼接不同用例，声称 25K↔Push 交替后也已完成整帧或实体屏幕验收。

## 复现与环境故障

```sh
evidence="$HOME/.cache/fpga-usb2-hotplug/replay_new"
mkdir -p "$evidence/tmp"
TMPDIR="$evidence/tmp" GW138K_USB2_HOTPLUG_EVIDENCE="$evidence" \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_hotplug.py -v

frames="$HOME/.cache/fpga-usb2-push-frame/replay_new"
mkdir -p "$frames/tmp"
TMPDIR="$frames/tmp" GW138K_USB2_PUSH_EVIDENCE="$frames" \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_push.py -v
```

默认 Push 入口包含 HS／FS 部分帧与 HS 完整帧；FS 完整帧另调用同一 `NativePushInput.run_push(..., high_speed=0, complete_frame=True)`，使用独立子目录，不覆盖其它场景。两个完整帧场景不是交替 bench 的一部分。

FS 完整帧的等效复现命令，沿用前述新建的 `frames` 目录：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a/sim \
  TMPDIR="$frames/tmp" GW138K_USB2_PUSH_EVIDENCE="$frames" \
  python3 -c 'from test_workstation_usb2_push import NativePushInput; NativePushInput().run_push(0, complete_frame=True)'
```

另复跑服务适配器 129 checks、两个生产 C ASan／UBSan 用例、pinout 32 项及 accepted 来源边界 10 项，均通过。当前源码对应的完整整机缓存产物重新执行独立审计通过，结果在交替证据根目录的 `complete-workstation-audit.json`；资源仍为 Register 54183／Lut 73623／Bsram 272，`release_ready=false`，不改变此前精确资源断言失败的结论。

第一次交替 HS 尝试在 `/tmp/ulpi-mixed-hotplug-20261027-152249/hs_1/` 因编译器临时目录配额不足而退出 2，未执行设备仿真。随后使用 home 缓存和独立 TMPDIR 重建并实际通过 HS；保留原失败日志，不删旧证据、不修改源码掩盖环境故障，也未碰并行 HDMI／DDR 进程或工程。

## 剩余工作与回退

- 仍需同一 CPU 交替场景中的完整 Push 帧，以及实际 `workstation_session`／公共参数应用／DSP／串行音频链的端到端验收；当前事件端屏障不证明默认参数已应用或音频连续。
- USB3300 ULPI IO 是否确由 3V3 供电仍是电气旁路项唯一待实测，`actual_board_measured=false`、`full_electrical_acceptance=false`；其它电气和板级验收仍不能由名义电压检查替代。
- 本轮不改完整整机编译输入；此前实际完整综合／独立审计及保留的历史资源精确值断言失败仍见前一记录，不报告完整回归全绿。P&R、路由时序、CDC／PLL、物理资源与实物 Push／25K 的 HS 能力和业务恢复仍需独立验证。
- 未操作板卡、SRAM 或 Flash，`bitstream_sha256=null`、`hardware_accepted=false`、`sram_deployed=false`、`flash_deployed=false`。不更新 accepted、latest 或部署索引；实体操作仍须用户明确授权。
- 回退只移除本轮交替仿真文件和原 Push bench／入口的完整帧增量及说明，不撤销生产会话围栏、电气旁路，也不回退并行任务文件。

目标保持进行中；已验证的离线范围不重定义为整个热插拔目标完成。
