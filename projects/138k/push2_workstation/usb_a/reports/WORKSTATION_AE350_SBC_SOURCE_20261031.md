# B04：AE350 SBC 解码来源阶段（2026-10-31）

本阶段提供未选择的 CPU 单帧 SBC 解码组件、固定 Apache 上游、精确适配、独立参考回归和 RV32 增量预算。没有改生产 profile、既有 HCI owner、BLE 协议、事件布局、DDR 地址图、时钟或音频输出路径；没有综合、P&R、板卡操作或部署。**B04 仍未完成**，手机 A2DP 连通、持续播放、速率／频差处理和完整资源验收不能由本报告替代。

## 1. 来源与复用选择

| 对象 | 固定版本／用途 | 结论 |
|---|---|---|
| Zephyr Android/OI libsbc | `8e1beda02acb8972e29e6edbb423f7cafe16e445`，Apache-2.0；content register 的 Android revision 为 `6b3bed846fb38036e23e70b18c07be2fa1c0aaaf` | 本次解码来源；只导入 decoder，32 个原始输入保持字节，另附标准 Apache license |
| Google libsbc | `6e505650145c9973d08a0bdd5e5f5e1914305e40`，Apache-2.0 | 有显式小上下文、无 malloc；原始 decoder 负数左移触发 UB，修两处后音乐压力向量相对 BlueZ 最大误差 3,227 LSB、最大 RMS 62.9139、最低 SNR 44.5777 dB；本阶段不选它 |
| BlueZ sbc | `b3deb8a5dcfb42d8c10ba1f2f1ac9bd7bf7271cc`，LGPL-2.1-or-later | 只作外部独立编码／解码参考，不把实现代码带入固件；测试输入与参考 PCM 来源于本项目生成的刺激 |
| Zephyr host | `0534e997eacb94bae1df6c9a7dd4a9a6cbf1cecf`，Apache-2.0 | 有实际 BR/EDR L2CAP／SDP／AVDTP／A2DP；直接依赖 kernel、net_buf、连接对象和内部 HCI，不能当成裸机有界模块直接接入 |
| BTstack | `9edb5d82ea6ec4466a393415d65030929330acdf` | 只读参考；仓库 license 条款 4 对个人／非商业／获利有约束，不默认为可商用固件来源，也不导入它的第二套 HCI owner |

版本 URL、原件清单和许可证位于 `firmware/ae350/third_party/sbc_oi/`。原件头部 Android/OI 版权与 Apache 声明保留。上游 `oi_cpu_dep.h` 的 ARM7 little-endian 选择在所读实现中只提供基本类型／字节序宏，不表示生成 ARM 指令；本移植实际使用纯 C、RV32IM 编译并检查 32-bit int、little-endian 和算术右移。没有浮点、堆或动态内存分配。

## 2. 原始失败及单独适配

普通 OI 原始运行并不充分：原生和 sanitizer 初始 PCM 差异来自 host harness 未清调用方 workspace，`DecoderReset` 本身只初始化上下文。服务现明确在每次新 epoch 清 synthesis history。

原件在联合立体声 4 子带的首半字节调用 `OI_BITSTREAM_ReadUINT4Aligned`，但刚初始化的位缓存不满足其条件；42 组中四组出现很大音频误差。适配改为通用 4-bit read。通用位读取在零分配子带还会执行 shift-by-32，现对零位显式返回零，同时允许初始化状态的 `bitPtr==32`。

两类算术检查分开保留：负数左移改为等效乘法；随后新增 CRC 有效、极端 scale factor 与随机 payload 后，真实触发原来的 signed accumulator overflow。不能靠关闭检查或 `-fwrapv` 将其标为通过。当前适配对 4/8 子带 transform 和 window 使用 64-bit 和、32×64 高位乘法；joint subband 进入 int32、filter state 进入 int16 时显式饱和。所有普通参考输出保持原来的最大 6 LSB 差异，极端 payload 也不再触发 ASan／UBSan。

`tools/prepare_ae350_sbc.py` 先核对完整原件清单／hash，再复制到一个不存在的目录并按精确锚点和计数适配；任何原字节、文件集合或锚点漂移失败。输出单列原件、适配器、first-party 算术头及适配结果 hash。临时适配的退出条件是向上游提交这些窄修复或固定经过审阅的新 revision，然后用同一回归比较后退休适配器；不能把当前生成输出变成唯一未登记的生产输入。

## 3. CPU 服务与有界行为

`sbc_decoder_service.h/.c` 每次消费一个完整协商帧，输出一个完整 PCM 块，不轮询无线、不访问 MMIO、不分配队列或存储整首音乐。范围为 44.1/48 kHz、mono／dual／stereo／joint、4/8 subbands、4/8/12/16 blocks、loudness／SNR 和 bitpool 2..53；mSBC／enhanced 关闭。最大 224 compressed bytes、128 PCM frames/channel、256 个 int16 scalar samples／512 bytes。双声道按 L/R 交织，单声道连续存放。

开始新流必须提供严格递增且非零的 epoch；新流清 history，取消关闭当前流，旧 epoch 不解码。耗尽不回卷。CRC／帧／格式／codec 错误关闭该流；短输出容量可在同流重试。只有全帧成功才设置 `result.valid`，调用方只能在 `OK && valid` 后发布 PCM。协商格式逐字段检查，不能靠帧头悄悄改采样率。服务需要单 CPU owner 串行调用，输入、输出和结果不重叠。CPU reset 后外部队列 fence 仍待实现，本 API 的 RAM epoch 不冒充跨 reset 的持久身份。

服务没有测得执行周期，也没有被主循环调用。未来 RTP／SBC reassembly、预填充、压缩队列／PCM 队列水位、溢出／欠载、DMA 所有权、A03 效果路径和 A06 速率切换仍须接入。44.1/48 kHz 每帧 128 samples 时分别约 2.902/2.667 ms；这是输入帧时长，不是 CPU 已满足的服务期限。手机和板上同标称率的长期频差不能靠有限队列永久吸收，仍须时钟恢复或明确 SRC。

## 4. 验证与预算

从仓库根运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_sbc_decoder.py \
  --output <不存在的新目录> \
  --reference-root <外部42组vectors-v1目录>
```

不传外部目录也有 11 组便携内置参考，含 joint/4-subband 回归。最终 source-stage 跑 11 内置＋42 外部，共 53 cases／3,392 音乐帧／577,536 scalar samples；原生与 ASan／UBSan 输出逐字相同，每套 62,593 checks。仅外部 42 组为 2,688 帧／458,752 samples，覆盖两采样率、四模式、两子带数、两分配方式、不同 block／bitpool。相对独立 BlueZ PCM 最大误差 6 LSB、最大 RMS 1.7346916941、最低 SNR 75.7623994410 dB。不是 SIG qualification vectors。

每个 case 另跑 128 帧 CRC 有效的全零／全一／随机 payload，共 6,784 帧，覆盖高 scale factor；维护服务还实际检查旧 epoch、取消、重启 history、格式变化、截短帧、CRC 错误、短输出、epoch 耗尽及 PCM canary。32×64 helper 以 host 128-bit 独立参考检查正负边界。更早直接 codec 验证另拒绝 210 个 CRC／截断输入，日志和失败版本保留。

六个来源／行为负控全部拒绝：原始输入字节漂移、适配锚点漂移、不清 history、接受 stale epoch、忽略 CRC、恢复错误的 joint4 半字节读取。维护 firmware 10 tests、accepted source 17 tests 均通过；未改变它们的生产选择。

实际 RV32IM_Zicsr／ILP32／O2 的 standalone link 包含服务、decoder 和维护 `ui_runtime.c`，text **16,883 bytes**、data **0**、BSS **2,752 bytes**。与仅普通输入修复的较小版本相比，额外成本主要是宽算术；不能沿用前版约 10.8 KiB 的预算。链接使用 function/data sections 与 GC，仅测增量组件，不是完整 UI／业务固件 fit，也不改变生产编译政策。所有编译器报告的最大单函数静态 frame 为 **80 bytes**；这不是跨调用／函数指针／异常入口的完整栈上界，更不是板上水位。未测周期／最长无服务间隔／总线等待／有效持续吞吐，物理 BSRAM 和时序成本仍未知。

## 5. 下一个标准协议入口必须保持一个 HCI owner

目前被审阅的 `projects/25k/example/RTL8723DS_PROTOCOL/adaptations/` 实际为 H5→initializer，初始化后切到 ACL bridge→GATT。H5 `MAX_PAYLOAD=280`，长度／地址接口 9-bit；ACL bridge 默认 `MAX_PACKET=264`、`ACL_BYTES=27`，单 BLE handle、单 partial PDU，完成 credit 只累计当前 BLE handle，`!connected` 会重置 credit。初始化读 LE ReadBufferSize `0x2002`，不能由它推断 BR/EDR 独立或共享池容量。

后续应在同一个 H5 出入口建立公共 command/event／handle／ACL credit owner，保留 initializer 与 BLE branch，CPU 标准栈通过其有界接口提交命令／ACL；不能把另一完整 host 的 HCI owner 并列接上。必须读／验证 BR/EDR ReadBufferSize `0x1005`、controller 支持能力、LE dedicated/shared pool policy、command credits、不同 handle 的 Number Of Completed Packets、连接／断开／reset 与串口重传所有权。

可以继续验证较小入向 L2CAP MTU（如 240）是否避免扩大 H5：被审阅 Zephyr L2CAP BR 实现的最小 MTU 常量为 48，但这不是本项目已完成的标准／手机验收；AVDTP signaling 分段、SDP continuation 和媒体 RTP/SBC fragmentation 要各自实现。单个最大 224-byte SBC frame 加普通 12-byte RTP 与 1-byte SBC payload header 为 237 bytes，只是几何可行性。手机可能聚合多帧、带 RTP 扩展或在配置完成前发其他数据；不能据此假定来包总小于 264/280。必须按实际 controller HCI ACL 接收长度和流控验证；必要时完整扩宽 H5 长度字段、RAM、CRC 和 credit 逻辑。

当前初始化后 fast UART 为 921600 baud，8N1 理论约 92,160 bytes/s，H5 framing／escaping／重传与 BLE 业务还要扣除。它不是已经测得的音乐吞吐。标准协议入口、真实手机和持续音频验收继续独立推进。
