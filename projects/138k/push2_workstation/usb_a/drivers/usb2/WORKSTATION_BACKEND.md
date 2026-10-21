# 原生 USB2 工作站传输后端

`workstation_usb2_backend.c` 将现有 `usbhw_*` 调用接到第一方 Host 驱动及原生 MMIO，供真实 `firmware.c` 使用。一个根口、一个设备、一个串行 CPU 调用者；Push 与 25K 仍交替连接。它不新增公共参数真值，不修改 USB PL 或 BLE 协议，也不把独立 CPU 组件变成整机候选。

## 来源与显式选择

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-usb2-soc --usb2-firmware-profile workstation \
  --usb2-soc-output /tmp/usb2_workstation_component
```

另加 `--usb2-full-speed-only` 可明确禁用 Host 的 HS 协商，用于 FS 诊断；默认允许 HS 并保留协商回落。该选项不能用于 probe、旧整机配置或缺少 `--prepare-usb2-soc` 的调用。

- 不指定 `--usb2-firmware-profile` 时仍是独立枚举 probe，绝不默认变为业务固件。
- 业务 profile 使用锁定 `start.S`、`minlibc.c`、`usb_core.c` 和链接脚本，以及第一方固件、panel 适配、Host／CPU port／backend；不编译旧 `usb_hw.c`，也不修改 vendor。
- RV32I／ILP32，业务代码 `-O2`，第一方 `-Wall -Wextra -Werror`。未修改 vendor 延续既有 `-Wall` 策略，不以第三方历史警告要求覆写 vendor。
- 输入与编译器身份、完整 ROM、静态 RAM 上限及来源漂移检查由同一个组件准备入口记录。业务输入缺失时失败，不退回 probe 或私有 staging。
- `business_firmware_selected=true` 表示 ROM 选择；`workstation_integrated=false` 仍表示服务未在板级组合根接到真实 owner。不会更新 latest，不产生板级约束或位流，不自动综合／下载。

## 包、会话与错误

每次事务前后核对 PHY／traffic／会话有效及 generation；换代、停钟、取消或驱动错误时停止使用旧设备地址／端点状态。关闭后清 IN toggle、PING 和控制状态，延迟 100 ms 再允许新接入；若底层关闭写本身失败，不声称硬件已经关闭。

`enable`／根复位预算 400 ms，单次底层 packet 调用 20 ms；等待同时受计时器和轮询上限约束，计时器停走不会死循环。应用既有包重试、重连和 MIDI 调度仍由 `firmware.c` 管理；传输后端不自行重放业务包。CPU 等待显示或 USB 不停止音频时钟，实际跨域队列／取消仍由工作站 owner 负责。

| 边界 | 规则 |
|---|---|
| MPS | HS bulk 仅接受 512，FS bulk 接受 8／16／32／64；事务最大分别 512／64，禁止把 FS 的 512 当成合法单包 |
| IN | 取速度上限与调用方容量的较小值，交给 MAC 验证；只有成功且 PID／长度符合时才推进该端点 toggle |
| 重复 IN DATA | 返回原 PID、零有效数据，不重复复制或推进 toggle；上层按既有 PID 合约忽略重复包 |
| OUT | 调用方持有 toggle；仅 ACK 或 HS NYET 表示该数据包已接受，调用方才推进 |
| HS NYET／NAK | 标记该端点须 PING；下一 OUT 先 PING。PING NAK 不重放已接受包，PING ACK 后才上传新的 OUT |
| SETUP／EP0 | SETUP 固定 EP0／DATA0／8 字节；成功后 EP0 IN 从 DATA1 开始，状态 ZLP 才提交待应用控制变化 |
| 配置／清 halt | SET_CONFIGURATION 状态完成后复位 bulk toggle／PING；CLEAR_FEATURE(ENDPOINT_HALT) 只影响指定方向／端点 |
| SET_INTERFACE | 初次配置前支持；已经使用 bulk 后明确拒绝，不能假装完成运行期 alt 切换并重置无关接口。当前生产路径只在接入时选择 alt |
| 失败 | NAK／STALL／timeout 映射现有返回码；结果矛盾、非法 PID、底层失败或换代不发布半包，须重新枚举／恢复 |

`usbhw_hub_enable` 保留旧调用签名，但原生控制器持有速度协商与 SOF，不用旧参数伪造速度或关闭必要 SOF。设备检测依据有效会话而非“线态非零”：HS 空闲本来就是 SE0。

## Push 与 25K 适配

原生 profile 不调用旧 FS FIFO 的 preload。Push 的逻辑帧仍为 16 字节 header 加 640×512 字节像素：通过服务 `28h` 定位、`2ch` 读取真实像素，保留既有逐像素 XOR／字节序；HS 每个逻辑块一包，FS 每个逻辑块拆为八个 64 字节包。每个实际包独立 ACK／toggle，NAK 只重试当前子包，不跳过字节或重放已确认子包。

25K 仍使用既有 MIDI EP1 和 PL EP2。原生 profile 的接收临时缓冲扩大为 512 字节，避免 HS 端点写入旧 64 字节局部数组；逻辑 PL reply 容量仍为 64，最大 reply payload、CRC、sequence 和 TILE wire contract 不变。62×4 的 TILE 逻辑帧为 520 字节，按实际 MPS 分包，不私自改为新格式。

宏关闭时旧 preload、缓冲和 MPS 路径不变；本轮用同一工具链重新编译，默认固件与 native 修改前逐字节一致。此比较是该编译环境的证据，不是对任意工具链承诺固定二进制哈希。

## 验证与范围

```sh
GW138K_USB2_APPLICATION_EVIDENCE=/tmp/usb2_workstation_application_evidence \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_application.py -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_preparation.py -v
```

证据目录必须不存在，省略环境变量则使用临时目录。应用 runner 固定并核对 Host 模型、bench、实际 25K MIDI／PL RTL 及其 include，保存各速度的 ROM／源哈希、工具版本、编译及执行日志；来源漂移或失败返回非零，不删除指定证据目录。

实际 CPU 场景执行未经替换的生产 `main`、锁定 USB core 和原生 backend，经物理 ULPI 模型与真实 25K MIDI／PL RTL 完成枚举、128 个有序 NoteOn／Off 事件以及 CAPS／两块 TILE。外部工作站服务仍是延迟应答模型，LCD 仍是完成应答模型：不证明真实参数应用、事件 FIFO／DSP、LCD 总线、实板 USB 或完整屏幕刷新。

另有 ASan／UBSan 的后端边界单测及完整 Push 帧生产 C 单测；后者核对全部 327,680 像素字节、FS／HS 子包、NAK 重试、PID 与 MPS，但传输和像素服务为模型，不是实物 Push 验收。

FS 回退物理模型在 peripheral `TermSelect=1`、`XcvrSelect=0` 等待 chirp 时也保留 D+ 上拉；依据 USB3300 DS00001783C §6.2.2、Table 6-8（第 34 页，Peripheral Chirp／FS 两行）。原模型错误地等到 `XcvrSelect=1` 才拉高，会让第二次根复位后的 Host 状态读取恰好遇到 SE0，并循环重新 attach；本轮通过独立十项模型检查和实际生产 CPU 的强制 Host FS／设备回落验证，不放宽 Host 复位、恢复、速度或错误检查。这是当前实际 25K UTMI 控制序列的字节级模型，不是任意 OpMode／电气状态的完整 PHY 模型。

还须在新板组合根接通真实工作站服务、原生时钟／复位／IO，完成 P&R／CDC／PLL／资源门禁，以及电气确认、实物 Push／25K／音频等验收。warm CPU reset 的可变 `.data` 恢复和运行期栈峰值也未由当前单次启动仿真证明。板级状态、完整范围和回退见 [本轮报告](../../reports/CUSTOM_BOARD_USB2_WORKSTATION_20261022.md) 与 [bring-up 清单](../../reports/CUSTOM_BOARD_BRINGUP_20261022.md)。
