# 新板原生 USB2 音频组件验证（2026-10-22）

## 1. 范围与结论

从 `5712029` 保存的阶段性源码继续验证。显式身份 `custom138k-usb2-audio-component-v1`，顶层 `workstation_usb2_audio`；没有生成、下载或固化位流。实际 CPU／USB2／25K MIDI＋PL 已进入原会话、参数、DSP、参考串行链和真实 delay DMA，HS 与独立 FS 策略均执行通过。

这不等于整机完成或新板可下载：未知功放／DAC、USB 电气、板级时钟／复位／IO、完整 DDR／显示／BLE 集成和 P&R 等仍未完成。`workstation_integrated`、`hardware_tested`、`deployment_allowed`、`release_ready` 全为 false。前一阶段 [INPUT 证据](CUSTOM_BOARD_USB2_INPUT_20261022.md) 保持其当时来源和模型范围，不回写为本轮结论。

## 2. 实际装配与来源

```text
真实 RV32I 业务 CPU / 原生 USB2 Host
  → 原 push2_usb_a_control + 真实 FIFO / CDC
  → 原生命周期合并 / workstation_session
  → workstation_parameters 唯一提交点 / 声部与 DSP
  → workstation_frame_delivery / 原 PT8211 参考串行链
  ↔ 原 delay FIFO / delay_ddr_dma / owner-6 native DDR 通道
```

组件只组合接口、CDC 和 readiness，不复制公共参数或引擎，不引入新的 18-bit 事件格式。音频状态经 448-bit mailbox 整体到 50 MHz，再由原输入 owner 交到 CPU，避免把音频域 performance 总线伪装为参考域输入。实际时钟为 CPU 48、reference 50、ULPI 60、audio 76.8、memory 100 MHz。

`tools/workstation_usb2_audio.py` 明确选择 66 项 RTL，另有 17 项 ROM／头文件／scope 数据；锁定依赖按原 baseline 描述重建。仅复用已有四项受检时序变换，没有生成另一套会话／参数业务 RTL。53 项被选音频源／数据与真实资源候选 prepare 输出逐字相同；新组合 wrapper 不存在旧位置，输入侧仍沿用已验证但未经资源候选变换的 FIFO，不能把整套组件称为资源候选的等价整机。

ROM、header、锁定支持源及 bundle 漂移在准备阶段失败，不发布完成 manifest、不回退历史 staging；包文件必须先于依赖它的模块。显式 audio 不能搭配 probe，也不能混用 accepted/resource 整机选项。默认 SoC／input 来源、固件和资源门禁没有隐式扩大。

## 3. 真实端到端执行

保留目录 `/tmp/workstation-usb2-audio-evidence-20261022-v3/hs_{1,0}`。Verilator 5.046，全部 66 项组件源、实际 25K MIDI USB／PL 端点、真实生产 C 和五个原频率时钟进入同一仿真；没有业务 ACK、会话、参数或 DSP 替身。仅接入去抖缩为 100 µs，不缩放 USB 根复位、recovery、SOF 或音频节拍。

| 策略 | 业务 ROM SHA-256 | DSP 有效帧 | 原串行链观察帧 | 执行 walltime |
|---|---|---:|---:|---:|
| 允许 HS，实际协商 HS | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` | 49,019 | 49,022 | 421.104 s |
| 显式 Host FS，实际回退 FS | `80a3415b6c89de06f359b268e14b7e826c14f6dd34ea54ddad4739ecf422aa41` | 42,683 | 42,686 | 366.786 s |

两种策略均检查：

1. 首次 NoteOn 进入真实 DSP 前，原初始化屏障已经完成，实际模式 C、音色／音量／表情、弯音中心、延音、滑音、vibrato、效果／矢量／TF 等默认值已经应用。
2. USB CC7／11／1／5／64、弯音和 ProgramChange 改变原参数；APB 写 CC7 通过同一实际应用点，非法事件返回 error，APB read 与 coherent feedback 一致。
3. 初始与重接音符产生非零 DSP PCM；音符顺序为 60、67、69、62，无重复或旧会话补播。每次采样 CE 间隔始终为 1,600 个音频拍，USB、PL、参数、APB、取消均不能暂停它。
4. PANIC／物理模型断线使真实 epoch 推进、held／deferred／active 清空；断线后八个 CPU 拍内 owner 离线。原 25K 清地址／配置后重枚举，接入默认值重新应用，随后 NoteOff／PANIC 清音。
5. 最后 PANIC 后继续观察至少八个原串行帧，最终观察 PCM 为零，健康／溢出／deadline／CDC／feedback drop 为零；这使用原 observer，尚未在本 USB 联调 bench 中独立解码 BCK／WS／DIN，也没有证明新 DAC 格式兼容。
6. 真实 delay DMA 执行读写；独立环模型注入有界 request 背压和七个 memory 拍读延迟，拒绝未写读取、越界、未对齐或错误 mask。地址限制在既有 128 KiB 分配，不新增 DDR 区域。
7. 25K PL 至少四块 tile 完成，协议／设备速度／配置／CPU fault 同时检查。所有仿真源、复制件、原准备输入和 staged 组件在执行后保持逐项哈希一致。

**仍为模型或未验证：** USB3300 是数字物理协议模型，不是电气合规；DDR 是环存储模型，不是新板控制器／仲裁器；LCD 只有 tile 完成，不是 SPI 面板；参考 PT8211 不是新功放。未连接 BLE、HDMI、TF、识别／播放后台或实际录音下载后端，不可用本轮 PCM 结论代替这些功能验收。

## 4. 实际综合与独立审计

GowinSynthesis V1.9.12.03，`GW5AST-LV138PG484AC2/I1`，使用 HS 执行中的同一 66 源／ROM／header 组件，实际综合网表 SHA-256 为 `931d5c1d6b5453736c715bd097497bce370d0f2bddc931763554097f0c7363b9`；manifest SHA-256 为 `63b063e5c8d4e0140424f7c04cbce153ae4302c3b7c454b6e793aea802fed006`。

- 75 SDPB＋1 SDPX9B＋21 pROM，共 **97 个综合等效 BSRAM**；1,194 SSRAM；16,893 个寄存器。pROM 必须计入，不能只报 76；这不是 P&R 物理 BSRAM 或整板资源结论。
- 新 `tools/workstation_usb2_audio_audit.py` 只接受上述显式 audio 来源／五时钟身份；锁定原语家族和数量、寄存器 `<18432`、XML／网表计数，并从全部 CPU bit-plane 重建 16,384 个 ROM word 逐字匹配。独立预算不是设备可放下整机的承诺。
- 原 SoC 和 input 审计不接受 audio 身份，预算不变；本轮又执行默认 SoC 实际综合，仍为 38 SDPB、1,922 个寄存器、16,384 个精确 ROM word。
- 负例覆盖 ROM 单 bit、缺 FIFO、额外 ROM／DPB／SP、原语数组、寄存器恰到上限、错误 top／XML 总数／来源策略、漏 header、改 header 和伪造 release 状态。数组门禁区分合法 Gowin 转义标识符（如 `\snapshot[0]_31_s0`），不能误杀正样本或漏算真正实例数组。

Gowin 保留 43 条警告：EX3791 35、CV0020 2、NL0002 2、EX3638／EX1998／EX2526／EX3780 各 1。包括原 `core_ce` 隐式声明、24-bit mem 到 22-bit ROM 宽度、未用显示输入位和未消费 FFT 优化；没有删除接口、篡改 baseline 或屏蔽警告来凑通过。Verilator `-Wall` 亦保留继承警告；新 wrapper 只有既有 FIFO 消费 memory reset 所引出的 `SYNCASYNCNET`，不是整板 CDC／复位通过。

## 5. 回归与复现

最终回归日志和逐项输入哈希见 [verification.json](custom_board_usb2_audio_20261022/verification.json)。速度子场景、负例循环和重复执行不另算独立测试数。

| 最终执行 | 独立 Python 测试数 | 结果 |
|---|---:|---|
| 新音频：HS／FS 真实 CPU 执行、来源／模型／数据漂移、lint、实际综合及资源／ROM 负例 | 10 | 全通过；执行单测分别 429.313 s、374.971 s，来源 8.638 s、综合审计 4.814 s |
| 默认 prepare 15＋MMIO 7＋真实 CPU 3 | 25 | 全通过；含默认真实综合、C ASan／UBSan、实际 25K HS／FS |
| clean baseline 23＋accepted 来源 10＋固件 staging 6＋原生组合 6 | 45 | 全通过；clean prepare 显式启用 `GW138K_VERIFY_CLEAN_PREPARE=1` |

合计 **80 个独立 Python 测试，无 skip**。本阶段未运行新板完整布局布线或板上测试；不把离线门禁折算成硬件通过。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio_sources.py -v
GW138K_USB2_AUDIO_EVIDENCE=/tmp/usb2_audio_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio.py -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio_synthesis.py -v
GW138K_VERIFY_CLEAN_PREPARE=1 \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_baselines.py -v
```

来源比较最初把地址头当作资源候选中的同路径文件，后按真实 `src/memory/ddr_address_map.vh` 映射修正；两份头字节本来一致。初版数组负例门禁误识别合法转义标识符，修正后正样本及全部负例重跑。上述失败不计入最终通过数，也不通过放宽生产来源或资源门禁解决。

## 6. 距离整机上板还缺什么

| 要求 | 本轮状态／下一实际证据 |
|---|---|
| 25K／HS | 真实 CPU→原 owner→DSP 组件 HS／FS 已验证；仍需 USB3300／TXS 电压兼容整改、实线与实体插拔／PL 观察 |
| 功放 | 参考 PT8211 链已接入，但补充网表 U1 仍无可靠器件型号；需实际芯片、FPC／RN 连线、MCLK、格式、PDN／电源时序，不能猜型上板 |
| BLE | 沿用独立已验证项目；新板连接和 138K 实际业务／录音后端未因本轮自动集成，未知 J2 balls 不能编造 |
| 其他外设 | 新板 PLL／复位／顶层、真实 DDR 仲裁与 ready、TF、HDMI 差分极性／HPD／CEC、LCD、UART 等须逐项接入并验证，不以此独立组件顶替整机 |
| 物理交付 | 未做本新板整机 P&R／完整 timing、CDC、PLL／功能资源门禁；没有位流身份、SRAM／Flash 或实体验收证据 |

完整目标继续进行，不标记完成。回退保持 `5712029` 及原显式整机 profile／既有部署记录；本轮组件不改 vendor、冻结基线、原 manifest 或部署指针，不对板卡执行任何操作。后续改变发布输入须另建可追溯候选，不继承本组件的硬件验收（本来就不存在）。
