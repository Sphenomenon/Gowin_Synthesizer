# 原生 workstation 整合与最终主音量（2026-10-24）

## 范围与来源

本次继续现有 `build.py --prepare-custom-board` 原生装配，不新增编号生产 builder，不复制整机，也不切换已接受的 full83／timing85／resource-timing 配置。开发身份为 `custom138k-native-integration-20261024-a17`，不是已部署或已接受身份。

- 已执行 `git pull --ff-only`，从 `f502f28` 前进到远端 main `e528073e2ae8763ecfcf2e10761f88cb9b0ca223`；再次同步确认无新增提交。
- 蓝牙业务分支远端 tip 为 `f2bae2dab3fbeb0ce5f55bbd555a3a29c76bb9c8`，已合入 main。采用最新导入的 138K 传输 vendor，而非旧 BTST 诊断服务。
- 工作区原有未提交的原生 USB2、25K 面板及 BLE 外部 PCM 改动继续保留。候选不是仅靠上述 Git commit 就可重建的干净树；具体源码、业务适配、固件、锁定基线与编译闭包以候选输入哈希为准。
- `boards/custom_138k/peripherals.json` 锁定远端 AK4493 排线、LCD 时序和双晶振测量依据的哈希；来源漂移、位置冲突及未完成准备必须拒绝。
- 保留 A/B/C、矢量、效果、TF WAV、识别、USB Push／25K、HDMI；加入原生 RGB LCD 与最终主音量，保持 BLE 实际 PCM 短录音／second40 下载。D 模式、长录音、Wi-Fi 网络服务与 LCD 触摸不在本次范围。

Push 和 25K 在同一个 USB-A 口交替连接。HS／FS 离线仿真不承诺实物一定协商到 HS，也不表示可同时连接。

最终准备目录为 `out/workstation_integration_20261024_v4`。输入清单归档为 [`workstation_integration_20261024/integration_inputs.json`](workstation_integration_20261024/integration_inputs.json)，SHA-256 为 `0f426f7035d93f028c0eb2d22f36d85e546efc3afd98e1b1aa2233ea720faf0f`：616 项工作区来源、507 项阶段输入、230 项启用编译输入，包含独立 BLE 业务来源哈希及实网表身份。固件选择 `workstation`、允许 HS 协商；ROM SHA-256 为 `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457`。没有位流，`bitstream_sha256=null`。

## 主音量：旋钮 → 唯一参数 → 最终功放输出

```text
Push CC71／CC79 相对旋钮 ─┐
                         ├→ 原有事件／会话提交 → workstation_parameters.CC7
25K 编码器 1 绝对 CC7 ────┘                          │
                                                    ↓
A/B/C／矢量 → CC11 表情及效果 ─┐              原子 PCM＋音量邮箱
TF 播放 ──────────────────────┴→ 最终选择 → 主音量单次缩放 → AK4493 I2S
                                                              └→ BLE 短录音
```

`workstation_parameters` 仍是唯一应用点。18-bit 事件、会话取消、PANIC 和提交背压保持原契约；旋钮输入和显示缓存都不能提前修改权威状态。25K 本地旋钮值只是发送端交互状态，不成为 138K 的另一套主音量权威。

原生装配显式选择 `EXTERNAL_MASTER_VOLUME=1`，效果输入的合成增益改为 CC11 表情，而不再乘 CC7；最终 FPC 适配器在效果和 TF／合成选择之后只乘一次 CC7，因此 TF、矢量和效果尾音也受同一音量控制。默认参数为 0，其它装配保留原行为。Push 的实际参数反馈使用主音量，而不是 CC7×CC11 的乘积，防止下一次相对旋钮写回错误值。

音量采用既有 Q1.15 映射：CC7=0 静音，1..126 为 `value<<8`，127 为 32768。立体声 PCM、输出使能与音量共 49 bit 原子跨域；非零变化每帧最多 256，零目标在下一帧直接归零并 SMUTE。采样和串行时钟不会为旋钮、LCD、BLE 或下载暂停。邮箱繁忙时沿用已有丢弃计数，不以实时流背压等待后台业务。

AK4493 使用并行引脚模式，未增加不存在的 SPI 音量控制。主音量为 FPGA 最终数字缩放，不是模拟增益校准，也不能修复功放模拟侧故障。HDMI 分析仍消费原输出路由的观察快照，位于新增 FPC 主音量之前；不能把它的幅度当成实际功放输出幅度。

## 音频排线与时钟

独立 pinout-only 配置保留历史同序排线假设；原生装配另行按网表反序推导，并与远端已核对的 `example/AK4493_AMP/constraints/audio.cst` 交叉验证：主板 `FPC2.n` → 功放 `FPC1.(25-n)`。两种位置输出不可混用。

| 信号 | 原生球位 |
| --- | --- |
| PDN / MCLK / BICK | C13 / B13 / A13 |
| SDATA / LRCK | A14 / B15 |
| SSLOW / SMUTE | B16 / A15 |
| SD / SLOW / 检测输入 | A16 / D17 / C17 |

K18 的标称 12.288 MHz 振荡器经 PLL 生成 49.152 MHz 工作时钟；I2S 为 48 kHz、双声道 32-bit slot，PCM16 左对齐，BICK 3.072 MHz，MCLK 12.288 MHz（256fs）。不再从 50 MHz 合成 512fs MCLK。先保持 PDN 低四帧，再静音到启动第 1028 帧；失锁立即复位／静音。检测脚保持输入。

其它 TF 采样率仍以最新完整立体声对保持／抽取到 48 kHz，并非带限重采样。连续 16 帧没有新观察值后归零静音；不无限重播旧值。PLL 使用理想模型的仿真只能验证数字行为，不能证明实际抖动、外部电平或模拟出声。

## 蓝牙与显示

BLE vendor 来自 `example/RTL8723DS/vendor/rtl8723ds_ble`，与 25K 业务项目的冻结 manifest 一致并逐项核对选入字节。GATT、H5、命令、存储和 second40 可靠下载继续使用 `projects/25k/example/RTL8723DS_PROTOCOL/` 的业务适配，不改 vendor、不从 ignored generated／builds 取源。广播名 `GW138K-MAIN`；保留业务启动 115200 → 921600 baud，不按单模块 115200 诊断工程降级。Wi-Fi 保持禁用。

BLE 从实际 FPC 串行器最终 48 kHz 帧取样，包含主音量、启动静音和输出静音；完整 PCM 与连续帧号经保持字 CDC 传递。合成／矢量与 TF 都可录入，正常音源切换继续记录最终输出及切换静音；帧号缺口或停钟超过 4 ms 进入 ERROR，不能下载不完整对象，允许清除。断连不反压音频，已启动录音继续。

独立 RAM 上限仍是 16,384 帧，即 0.341333 秒，满容量封存；不是 DDR 长录音，不新增 DDR 地址分配。REC_START 继续 `format=1, source=0, flags=0`，最大时长 0 表示容量上限；不能填 1 秒并声称满足。保留 boot_id 重复限制，重新配置后不能盲目恢复旧未完成下载。未新增 BLE 参数写入能力或私有音量命令，Android 依赖方向和线协议不变。

`workstation_lcd` 使用远端 LCD 的 31.5 MHz、976×528 总时序、800×480 有效区，缩放复用现有 960×160 Push 性能页。290-bit 公共反馈快照经原子邮箱，在帧边界使用；不另建参数副本，也不申请 DDR。没有权威末音／力度输入的字段隐藏，不用零值冒充实测状态。背光等待三个完整帧，失锁复位；刷新和丢旧快照不会阻塞音频。其显示内容为公共性能状态，不等于 BLE 连接／录音状态页。

## 已完成的离线回归

| 回归 | 结果与边界 |
| --- | --- |
| `sim/test_workstation_fpc_audio.py` | 2 项通过：真实 Push 映射／参数提交、25K CC7 全 128 值及背压／上下界；实际 I2S 解码、半音量／零音量、256fs、立体声原子性、BLE tap 一致、采样率保持及 PLL 恢复 |
| `sim/test_workstation_peripherals.py` | 4 项通过：来源漂移／碰撞拒绝、原位置配置不变；实际共享渲染器完整 LCD 光栅、帧原子状态、背光及失锁恢复 |
| `sim/test_workstation_bluetooth.py` | 6 项通过：真实业务 UART／补丁／GATT／实时 PCM 录音、下载与错误边界；不是实体射频或 Android 真机验收 |
| `sim/test_workstation_custom_clocks.py` | 4 项通过：三输入、十一个派生时钟及约束来源 |
| `sim/test_workstation_custom_board.py` | 9 项通过：原生 prepare／端口闭包／默认顶层 token、隔离、真实 25K HS／FS 输入和原生 TMDS 专用输出综合 |
| `sim/test_workstation_custom_board_synthesis.py` | 最终 v4 实际综合产物审计及故障注入通过：来源、ROM、层次／资源、复位、CDC、PLL、CC7 最终连接与 CC11 效果输入，错误不得放行 |
| `sim/test_workstation_usb2_audio.py` | HS／FS 两项通过：实际生产 CPU、25K 对端、会话／参数／DSP／参考串行链／delay DMA，连续 48 kHz、拔插／PANIC／PL；不是实际 DDR 控制器、FPC DAC 或 LCD 总线验收 |
| 25K `tb_gw138k_panel_controls` | 真实应用实核通过，包含编码器排队音量步进、重连默认值及不回放旧事件；本次未修改 25K 文件 |
| `sim/test_current_workstation_sources.py` | 10 项通过，已接受输入边界保持 |
| `sim/test_stage_usb_firmware.py` | 6 项通过，固件准备与来源验证 |
| `GW138K_VERIFY_CLEAN_PREPARE=1 sim/test_workstation_baselines.py` | 23 项通过，包括三条完整 workstation prepare 路径在干净 checkout 中重建、不依赖私有历史 staging |
| 架构 composition／build-options | 6／12 项通过 |

音频 HS／FS 测试使用默认音量策略验证旧配置兼容性；新增最终音量的执行测试和综合网表连接审计分别验证原生策略，不能把三者混称为单个真实板级端到端测试。上述执行回归所用 RTL 与最终准备输入的相同范围逐项核对；审计器随后因 Gowin 把主音量端口合并命名为 `performance_words` 而修正，重新准备并综合，不覆盖旧失败快照。

v3 到最终 v4 的 616 项来源中仅审计器改变；32 项原生复制源、4 项锁定支持源、BLE 源快照与固件 ROM 完全一致。最终审计器检查参数所有者的标量输出、FPC 对应总线位宽／方向及逐位连接，并单独核对效果输入仍为 CC11；不能把无法解析的旧端口名当成已验证连线。干净 checkout 回归首次在 `/tmp` 的 clone 阶段写文件失败；改用仓库 ignored `out/workstation_test_tmp_20261024` 所在磁盘作为 `TMPDIR` 后全部通过，未删除历史目录或修改测试来绕过。

## 最终综合审计

v4 完整离线综合和来源／网表审计通过，完整结果归档于 [`native_synthesis_audit.json`](workstation_integration_20261024/native_synthesis_audit.json)，派生位置与实网表来源证据归档于 [`pinout.json`](workstation_integration_20261024/pinout.json)。这些是候选证据，不是新的生产输入或位置权威。

| 项目 | 结果 |
| --- | --- |
| 源综合网表 SHA-256 | `83bb875fc6432cbe1ee5a23eed6779ca0a9efad18cc87d43b8752d0a308612de` |
| 综合日志 SHA-256 | `c79ef0853461183513f91fccadeb8bcb0e30257022df586a4f7c18ddee43aee4` |
| 资源报告 SHA-256 | `648cb2462f12c0ff4f98070a1b8577e4cf50f1ea288b241358dda19626491bad` |
| 寄存器／LUT／ALU | 56,988／78,198／15,353 |
| BSRAM／SSRAM | 266 综合等效／1,459；不是 routed 物理 BSRAM 数 |
| MULTALU27X18／MULT12X12／MULT27X36 | 46／42／45 |
| 端口覆盖 | 127 项位置、136 个物理端口 bit，含独立核对的隐式差分负端 |
| 启动 ROM | 16,384 words 与所选业务固件逐项相符 |
| 功能保留 | USB／CPU、合成／矢量、效果／delay DMA、TF WAV／DMA、识别、DDR、HDMI，以及 FPC、BLE 实际 PCM 存储和 LCD 均保留 |
| 主音量连接 | 权威 CC7 逐位到最终 FPC；效果输入单独为 CC11，不重复主音量衰减 |
| 时钟 | 共 14 项；10 个可见派生时钟拓扑通过。三个外部输入与不透明 DDR UI 内部仍不能据此宣称硬件／全部物理时序通过 |

完整审计 JSON SHA-256 为 `9e44f8d10c9e7243fd2e81d42e3d4c6b3067a0e37bae909a3e97bc00060668a8`；审计器 SHA-256 为 `17283438c219ec243ccee0da4eeceacf4f75f38779ab5fbd638c02198b6d3b83`。

最终回归组结果、测试源码／日志哈希、v3→v4 来源比较及所有未放行状态见 [`verification.json`](workstation_integration_20261024/verification.json)。收尾时重新核对全部 616 项工作区输入、507 项阶段输入和 13 项 BLE 外部来源，均与最终准备清单一致；归档输入、位置和审计结果字节也已核对。

## 验收门禁与回退

本次没有生成发布位流，没有操作板卡、下载 SRAM 或写 Flash，也没有更新部署／latest 指针。`place_route_allowed`、`deployment_allowed`、`release_ready`、`hardware_tested` 均保持 false，电气检查仍 blocked。

仍需分别完成：

1. USB3300／TXS 及各 Bank 电压、电平、排线方向和全部 IO 电气检查。
2. P&R、真实 PLL／CDC／复位／布线时序、物理 BSRAM 与资源门禁；综合等效 BSRAM 数不能当成物理占用。综合日志仍有跨 PLL 时钟关系警告，不能靠 false-path 扩大豁免或降低时钟掩盖。
3. 实物 Push／25K 交替枚举、旋钮、全音源输出、HDMI 和 LCD 联调，验证大量屏幕／BLE 活动下采样不断流。
4. 功放左右声道、噪声／爆音、电平、静音和上电验收。远端 AK4493 例程记录仍有耳机右声道单侧／噗嗤／断音反馈，不继承“数字检查通过”为模拟出声通过。
5. 实物业务 BLE 配对、Android 短录音下载及 PCM／CRC／声道核对；长录音和稳定跨启动对象身份另作集成。

以后只有获得明确上板授权、产生独立位流身份及读回／实测证据后，才能记为 SRAM 或 Flash 部署。回退为继续使用原来明确选择的 accepted 配置；本次没有替换其输入，也不需要为回退删除 ignored 历史结果或刷板。
