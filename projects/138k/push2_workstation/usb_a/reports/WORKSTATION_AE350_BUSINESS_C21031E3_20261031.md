# AE350 业务替换：整机候选 C21031E3

源码检查点 `f8cf875`；现有 `custom138k-workstation-ae350-business-v1`
生成候选 `39a6b2e5cfbbf595`，614 staged／272 enabled。
保持 1080p60、双率音频、完整效果、TF、HDMI、USB 和两路 DDR 录音，
ILM／DLM 各 64 KiB、启动 ROM 64 KiB；no-CNN／no-local-panel。
本批不选择 A2DP／SBC，相关成本未混入卸载收益。

AE350 的真实启动／后台 pump 调用 C owner，接管八槽任务、三类 ID、
START／STOP／GET／CLEAR、全部 OPEN／READ／ACK／组合读／恢复、
CLOSE／CANCEL 与 30 秒超时。原 `native_bluetooth/ble_recording.v`
及其任务、对象、下载会话状态机退出编译；FPGA 保留采集、CRC、DDR、
封存、Rice、线规和重放缓存等数据通路。本轮增加共享 20 周期 GATT
sample／CRC builder、现有 C350 上的真实 pump 观测，并修正六个共享
release FF 的旧空 CLEAR 选择器；没有新探针或长期 profile。

## 完整综合

Gowin 综合退出 0，362.104 秒，登记输入前后保持，无 AG 组合环诊断。
VG SHA256：`8bc03bfcb25a970abafd7aef6d1e2ca448227c21478d35d05680ecef5667df88`。

| 综合资源 | 迁移前 011fdc9c | 前次 business 1a806f23 | 本次 39a6b2e5 | 相对迁移前 |
|---|---:|---:|---:|---:|
| Logic | 94,623 | 97,095 | 96,704 | +2,081 |
| LUT | 75,967 | 78,715 | 78,346 | +2,379 |
| ALU | 16,802 | 16,766 | 16,744 | −58 |
| Register | 60,578 | 62,883 | 62,809 | +2,231 |
| RAM16 | 309 | 269 | 269 | −40 |
| 等效 BSRAM | 245 | 248 | 248 | +3 |

以上是完整同功能配置总量，包含 CPU 存储、邮箱、队列、总线、RTC 和
本次 96 FF 观测寄存器；尚无卸载净资源收益。前次与本次 configuration
完全相同，15 个 staged 文件变化；同时包含已并入主线的 serializer／
boot memory 等维护修改，−369 LUT 不能全部归给 GATT。GATT 本体仅
−11 LUT／−1 ALU／−1 FF；邮箱映射由 3865 降至 3510 LUT。
综合 BSRAM 不代表物理占用，Logic 不代表 CLS。

## 验证与物理进度

C／APB／实际 RTL／DDR 协同仿真通过 1701 checks、136 条消息与旧线规
逐字一致；GATT 两项回归（含背压、快照及两种中断／重连）、真实固件
六项、实际 prepare 业务十一项、accepted 来源十七项通过；profile 七项
通过，十五项外部前置跳过。ILM 30144 B、静态 DLM 656 B，保守调用栈
1376 B／预留 16384 B；ELF SHA256 为
`8b520dda735def4f9ec1bf22719257806d465593a9cf69bdfa5f40ae1cd0b479`。

`C21031E3` 已启动完整 P&R，place2／route0／不复制资源，不放宽时钟或
数据路径例外。新 VG 时钟正向门禁通过；PCM CDC 检查发现 serializer
`requested_s0/CE` 新消费端，当前正在做该端点的必要 next-Q 证明，
未将拒绝计为通过。P&R、完整 STA、物理 PLL 与 SRAM 验证结果待收取。

外部产物：`~/.cache/gw138k-task-20261030/business-gatt-integrated-candidate-v2`
及 `business-gatt-integrated-physical-C21031E3-v1`。本批未操作板卡、未写
Flash；板上仍为回退身份 `C11028E5`。只有必要物理门禁通过后执行已授权
SRAM 验证；失败时重载已有 Flash 并独立读回原身份，不改 Flash 内容。
