# 原生 DDR 扫描窗口 admission 检查点

日期：2026-10-30。将独立 D5 的扫描窗口原则移入明确选择的版本化 HDMI 组合，并同时约束 CPU 后台写。**这里只交付来源接入和离线诊断，不勾选 D01／D04，不转移独立 D5 硬件验收。**

## 来源与行为

`rtl/workstation/workstation_hdmi_display.sv` 从 F02 revision 2 的实际 prepared `src/video/hdmi_display.v` 精确迁出，父 SHA256 为 `900914bbcc98cdb563f708eea2bf6edf989917526103d628799930acfba59794`。原活动文件、冻结 baseline、vendor、DDR 地址和 queues/core 不改。父来源和七个连接／参数变更区域保存在 [provenance](../rtl/workstation/workstation_hdmi_display.provenance.json)；逐项反向恢复可重现父字节。

新增 [workstation_ddr_scan_window.sv](../rtl/display_data/workstation_ddr_scan_window.sv) 放在 `basic_pitch_ddr_client_queues` 稳定本地槽之前。实际 scan 的 `fetch_busy=active || request_pending` 为 1 时，merged raster/shared writer 与 CPU 写的新 valid、ready 同时被屏蔽，生产者保持原请求。CPU 读及 TF、delay、CNN、display reader／BIST 路径不经过门控；已接受的槽、grant 引用、native command 和所有返回继续排空，保持 mask／顺序／owner。

组合参数 `SCAN_WINDOW_ENABLE` 默认 0。显式宏 `WORKSTATION_DDR_SCAN_WINDOW_ENABLE` 将默认置 1；revision 3 的 source policy 由 `workstation_profile_hdmi.sv` wrapper 明确启用。新增逻辑只控制 admission，没有逐文本改写生产 RTL 的 overlay。具体组合、候选身份与输入闭包以 [scan_window.json](workstation_task_20261030/scan_window.json) 和独立 profile 证据为准。模块门控契约见 [SCAN_WINDOW.md](../rtl/display_data/SCAN_WINDOW.md)。

本次诊断选用 `custom138k-workstation-v1-d23d498ea824c9f9`，profile revision 3，共 231 个 enabled source；HDMI 为 1080p60，当前整机实现采样率仍只有 48 kHz。gate SHA256 为 `34e8ae73aab53472b0ecbadf17c747f90f6ea12ca3cf61bed47a6d758f0a9454`，native HDMI 为 `607f30dd643b01c4522e5e813745e608749dad141bcc9f09b91876be78749432`，provenance 为 `4446ca568ac88345ad1c6cfc483b255161806a43451e0dd57903fb2f53a7fa62`。机器证据记录 wrapper、prepared profile 与所有仿真输入的哈希；两次最终运行之间及运行前后均未漂移。这里记录的是 prepare 身份，不是 bitstream 或板上部署身份。

每 owner 一个本地槽与一个共享 native command buffer，在窗口开始后可能继续 native-issue 最多两笔该 owner 已接受写；grant 引用本地槽不另存命令。该界限不包括 DDR IP 内部已接收事务，不能当作物理控制器尾部保证。没有在窗口开始时清队列、取消事务或伪造完成。

## 验证范围

`sim/display/run_scan_window.py` 直接编译 revision 3 prepared 的实际 scanout、SDP、queues/core 和 gate，记录每个输入 SHA256，并检查测试前后来源不变。新增有界 TF／delay／CNN／display 请求模型只用于施压，没有用它们替代真实业务 DMA 的完整验收。

- gate 的 64 种握手组合核对默认关闭透明、writer／CPU 写同时禁止 valid／ready，以及 CPU 读透传；Verilator `--lint-only -Wall` 无告警。
- 默认关闭与旧分支实际扫描结果相等：均比较 61,440 像素、32 行，无黑行／欠载，native 后台写同为 103,026 次。父组合其他逻辑逐字节保留，并经反向迁移哈希核对。
- D5 仅连续 writer、64 UI 拍读返回、100 UI 拍人工方向切换模型通过，61,440 像素无黑行／欠载。
- 混合负载包含连续 writer／masked CPU 写；TF 按 `400000000/fs` UI 拍一请求、delay 按 `200000000/fs` 一请求，交替读／写；CNN 及 display 每 5000 UI 拍一请求。每个读模型最多一笔 outstanding。ready 定期每 11 拍停一拍，另外施加方向切换等待；这些都是明确的人工控制器参数，不是实板测量。
- 两种请求速率的正常及迟到行／epoch 恢复检查记录像素、tag、mask、native 顺序、controller stall 时 payload 保持、producer 到槽／槽到 native／native 到返回的最大等待，以及 scan／返回队列峰值。停止测试生产者后，所有已接受命令精确发出一次、读响应全部排空；窗口内两类后台写尾部均不超过 2。

完整 1080 行模型各覆盖四帧：

| 请求速率模型 | 比较像素／行 | 黑行／underrun | 启动单行最大 | 运行单行最大 | native writer／CPU／TF／delay／CNN／display |
|---|---|---|---|---|---|
| 48k，40 拍方向切换 | 8,294,400／4320 | 0／0 | 1381 UI 拍 | 1358 UI 拍，13.58 µs | 296021／296020／800／1600／1334／1334 |
| 44.1k，40 拍方向切换 | 8,294,400／4320 | 0／0 | 1322 UI 拍 | 1427 UI 拍，14.27 µs | 298383／298382／735／1470／1334／1334 |

两组完整运行的 scan 总 credits 峰值均为 8、返回 FIFO 峰值均为 3，native 已发未返回读峰值分别为 9／10。各 owner 已接受槽到 native 最坏为 CPU 120／125、writer 120／200、TF 42／78、CNN 55／91、delay 118／88、display 42／82 UI 拍；模型 native 读到客户端返回均为 65 拍。producer pending 到 writer／CPU 槽最大分别为 2510／2512 和 2451／2454 拍；其他有界模型当次槽可立即接受，这不代表 native 零等待。两类窗口尾部各最多 2 笔，停止生产者后全部命令与响应精确排空。

完整运行均通过像素、顺序、mask 与排空检查，但运行单行最大仍超过 1200 拍／12 µs 设计目标。这里的成功域仅在记录的模型及覆盖范围成立，不推出其他控制器／相位组合通过；44.1k 只调整请求到达速率，不代表音频时钟或整机采样率已经切换。

实际 prepare 后，`test_workstation_profile.py` 13 项全部通过（prepared 与 legacy prepared 两套路径均显式指定，无跳过）；包括新增 wrapper／依赖闭包、启用策略篡改拒绝和默认工程不受影响。`test_current_workstation_sources.py` 10 项全部通过。新板既有九项定向测试中七项普通检查通过，另两项 TMDS 检查在补齐官方 simlib／Gowin 动态库环境后分别重跑通过：真实 OSER10／ELVDS 仿真，以及 `NativeBoard.test_native_tmds_dedicated_output_route_synthesizes`。后者只是独立输出路径小工程综合，不作为完整候选综合或物理验收。复核扫描证据中的全部 prepared、原生源码和测试输入 SHA256 均一致。

## 保留的失败模型和期限缺口

| 人工模型 | 观察 | 结论 |
|---|---|---|
| 混合请求，100 拍方向切换，gate 关闭 | 第 2 行黑行；启动单行最坏 21,970 UI 拍 | 原有竞争可严重破坏扫描 |
| 同一混合请求与 100 拍方向切换，gate 开启 | 第 7 行黑行；启动单行最坏 1859 拍，已完成运行行最坏 1499 拍 | 仅暂停 writer／CPU 写不足以给全部 TF／delay／CNN 竞争建立扫描期限 |
| 混合请求，40 拍方向切换，gate 开启，短窗口 | 两种速率各 61,440 像素无黑行／欠载；运行行最坏 48k 1295 拍、44.1k 1240 拍，启动单行最坏均为 1322 拍 | 存在可测通过域，但仍超过先前提议的正常行 1200 拍／12 µs 设计目标 |

100 拍模型失败不是通过调整 scan 宽度／额度、关闭 TF／delay／CNN、停止采样或放宽像素时钟修好的；失败日志和参数保留。测试工具把“按预期观测到 deadline violation”与 `functional_success=false` 分开存储，不会把该负例写成渲染通过。

scan 有两个同时成立的期限：从 x=1919 的请求到 N+2 目标行 x=0 约 16.707 µs，须扣除跨域与 tag 发布；同时 mailbox 必须在下一次 x=1919 触发前收到完整取行 ACK，即约 14.815 µs 再扣请求／ACK 往返 CDC。1499 拍虽约 14.99 µs，仍可错过下一次行请求而黑行，不能只检查目标行像素到达。启动两行预取在 vblank 中另计，不和正常逐行期限混为一类。

## 下一阶段与回退

完整 D01 仍需给控制器 Gread／Gwrite 联合 ready／Lread 建立包含刷新、方向、地址序列和最大 outstanding 的上界，并用真实客户端水位与 deadline 做有界调度。当前固定优先级仍可饥饿；gate 也不给长时间取行中的 CPU／writer 额外公平份额或超时。短模型的 ≤1 ms 观察不能升格为全业务保证。44.1k 在这里仅改变流量模型，不证明整机 44.1 kHz 音频、delay 系数或 DAC 模式已经接通。

后续综合、P&R、CDC／PLL／时序及实板并发按同一新候选单独记录；本离线诊断没有操作 SRAM／Flash 或据此推断板上内容。源码回退可选择 revision 2 的父 HDMI 输入及 profile，或让原生组合参数保持默认 0；已接受的历史输入及独立 D5 回退证据保留。
