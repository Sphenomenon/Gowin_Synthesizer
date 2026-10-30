# R00 正式源选择与真实 RTL 离线阶段（2026-10-30）

本阶段把已有 PCM DDR backend、四位 owner8 仲裁和 native 接受账本接入一个显式可准备的正式源 profile。新入口为 `custom138k-workstation-r00-v1`；它基于 no-CNN runtime，保留旧 BLE 短录音 RAM。R00／R01／R02 尚未完成，也没有净 BSRAM 收益、物理时序、硬件或部署接受。

机器证据见同目录 `r00_production_source_stage.json`。这是基于 `3156993f7659709d6efe73ae0b8385a369d00997` 的隔离源交付；父级集成新的 PCM checker 后必须刷新三个 profile 的完整来源锁并重新 prepare，新输入不能继承此处的候选身份。

## 源选择和对象边界

| 入口 | provider／仲裁 | AE350 编译 | DDR map／BLE |
| --- | --- | --- | --- |
| enabled revision5 | 原 runtime；原 legacy DDR 队列 | 原五个源文件 | 原准备策略；原 BLE RAM |
| no-CNN revision1 | 原 no-CNN wrapper；原 legacy DDR 队列 | 原五个源文件 | 原准备策略；原 BLE RAM |
| R00 revision1 | 新 R00 wrapper；HDMI 内真正的 owner8 队列／core／返回账本 | 显式再加入 recording API | 校验原宏不变后选择维护地址表；原 BLE RAM 保留 |

旧入口 top／HDMI 的预处理 token 与基点在四种宏环境下一致。相同 xPack GCC 15.2.0 下，新默认固件和基点默认固件的 binary／ROM 逐字节相同，ROM SHA256 为 `c598c50aa0172be1c5644fa50a17c4a18ea304cce7aaeca476cd55b7dba0e752`。这不代表旧候选的源锁仍可接受新共享构建工具。

最终序列器完成的物理 PCM 经 98-bit observation CDC 进入 recorder；实际 rate／epoch／sequence 随帧携带。物理 PCM 高16位为左声道，进入 backend 时交换为下载格式的低16位左声道。CREATE 等待下一有效物理帧确认；该帧排除，之后连续帧才录入，4 ms 无来源超时不创建对象。AE350 提供非零64位唯一对象 ID，backend 单独拥有提交后的对象描述符。

业务页为现有 AE350 APB 上的内部 `0xf8040000`，经过现有 APB CDC 到 DDR 域。POP_HEAD 捕获原子256位窗口；CPU 可慢读、乱序读八个 word，RELEASE_HEAD 后才可捕获下一 beat。维护 C API 没有自动重试；失败可能已写入，poll 的 ID 双读只检测对象更换，CAPTURE 的计数跨寄存器读会继续增长。

媒体准备增加可选第三 owner：正常切换先封存采集，等待不可变 READY 和采集写真正 native 提交后再确认。已有 READY 对象的下载和引用可跨采样率切换继续；这个确认不代表全部 owner8 读事务静默。正常 hold 阻止 CREATE／CLEAR／CANCEL。CPU observer reset 只重置总线窗口并释放／排空下载引用，不清录音对象或采集。

PCM observation loss 在 controller 生命周期内 sticky。没有录音时丢帧也会拒绝以后 CREATE；CPU reset／CLEAR 不恢复，只能共同 controller／ledger／backend reset 后重新观测有效帧。新实际 FIFO overflow 场景和错误 observer-reset 对照验证了这个 fail-closed 恢复规则。

地址仍来自 `rtl/ddr_address_map.vh`，使用既有录音预留 `0x30500000..0x305fffff` 的首64 KiB（16384帧），native word base 为 `0x0c140000`。安装先比对锁定原 map 字节，再检查所有历史宏保持不变；不修改 baseline、vendor 或历史清单。

## 校验和来源

隔离 prepare v5 候选为 `custom138k-workstation-r00-v1-5775b90535632253`，config SHA256 `2b182e300576095172925207f0bc29f5ab074e305fb93ca129b21c84330b4bf6`，profile artifact SHA256 `20e5ae31d3d36cfb833e9cd1488b452b8f789269de93d232d5652a352e99b503`。来源闭包为338个锁定文件、266个实际编译输入、583个 staged 输入和753个完整 snapshot 文件。

维护回归 `sim/services/run_workstation_recording_runtime.py` 的13个正向场景及5个负控全过，identity 为 `r00-runtime-owner8-offline-v1-34144ee774b2c86e`。它实例化真实 runtime／PCM CDC／APB CDC／service／backend／native bridge／owner8 core 和有序 DDR 模型；其他 BLE／runtime 媒体 owner 是终态握手 fixture。场景涵盖双采样率实际描述符、序号回绕、CREATE 沿排除、左右声道逐字节读回、非对齐 tail、native stall、cancel、正常 seal、第三 owner stale ACK、CPU reset 的已接受读排空、总线 snapshot、来源间隙和真实 observation FIFO overflow。负控必须拒绝错误左右顺序、无 valid 的错误位、hold 丢 seal、本地 ready 假提交及 CPU reset 假恢复健康。

此外通过：实际 prepared profile 7项；固件来源与真实 RISC-V 编译10项；C API 每个总线失败点的无重试／输出保留／窗口校验；accepted 输入边界10项；原 media preparation、owner8 44项与 backend 41项。service Verilator 使用 `-Wall -Wno-PINCONNECTEMPTY`，仅允许有意不消费的输出空连诊断，其余告警仍失败。新 ROM 为14052／16384字节，静态 RAM 60字节，预留栈容量7620字节；完整调用链栈界和硬件水位未验证。

独立审查重新核对 actual GPRJ／Tcl、provider 预处理、HDMI 内 owner8、物理 PCM、native_accept[8]、返回数据、共同 reset、第三 media owner、DDR 范围及原 BLE 字节，并独立重跑全部18场景；没有未解决的确认源缺陷。阶段纠正了 registered seal 与 hold 同拍丢请求、未用 valid 限制 observation payload error 两个真实问题，均保留负控。

额外 clean baseline 检查的22项普通测试通过，但三入口 clean prepare 在 accepted_full83 的第一步被既有 `accepted DDR input drift: rtl/ddr_address_map.vh` 拒绝。维护地址表与本交付基点字节相同；这里没有移除检查、修改冻结源或借用旧接受身份。该阻塞另行处理，不能把本阶段描述为全部仓库门禁通过。

## 余项和回退

没有运行完整 top elaboration、综合、P&R 或板上操作。新 PCM／seal CDC 的物理约束、reset／PLL、DDR 服务上界、并发无音频欠载、真实非零 PCM、BLE 对象／CRC／Android、长录音、SRAM／Flash 仍待各自验收。现有时序或资源数字不得转移给本候选。

回退到原 enabled 或 no-CNN profile 就不选择新 recording runtime／owner8 分支；正常生产接受身份不被替换。API 不生成 BLE task ID、不改 wire format，也不自动挂接 UI 业务。此阶段没有位流和 SRAM／Flash 回退身份。
