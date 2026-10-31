# M／W DEMO：DMA fault 与 USB FIFO 异步接收边界

2026-10-31。维护工具 `tools/workstation_demo_boundary_cdc.py` 及其独立测试已冻结。M10b、W9b 各自真实综合 VG 和默认物理 VO 的完整结构与实际 SDC 回归全部通过：每份运行 6 项测试、拒绝 60 个负例，共 240 个负例；原始网表及审计依赖 bytes 均保持不变。[配套 JSON](dual138k_demo_boundary_cdc_20261031.json) 保存四份完整消费者清单、来源散列、原始回归命令和证据散列。

本阶段交付的是两处接收边界的精确结构证明与四条约束。既有 M10b／W9b 候选和 `physical.sdc` 未被改写；回归仅在内存中向实际 SDC 追加提案。本阶段没有新综合、P&R、位流、SRAM 或 Flash 操作，也没有测得资源收益或新时序余量。既有四份物理候选的整机 STA 均失败，见[原始物理记录](DUAL138K_M10_W9_PHYSICAL_20261031.md)。

## 1. 冻结来源与构建选择

| 输入 | SHA-256 |
|---|---|
| `tools/workstation_demo_boundary_cdc.py` | `903e31b08476a05b2dd4b41e5fb9913b5ece6ee66e1a8dd0353bd0130d18fc9b` |
| `sim/test_workstation_demo_boundary_cdc.py` | `878dc3eac682c4dfc14ed14d73e6a8c1f739cc68588731cb170d9f3ccd312ce9` |
| 四条约束原始文本 | `c1f7020a9e8a7a0ce6f147c462aab1ec6ffaf019476bdf469b179f9c95569fb7` |
| `demo-boundary-maintained-seal-v2.json` | `b5126588c0b07727862d679df5b0068acb8a93fb8310a326f25cbf8127e6fa35` |

外部证据目录为 `/Users/sphenicidition/.cache/gw138k-dual-20261031/`。seal 固定上述工具及 `workstation_runtime_pcm_cdc.py`、`workstation_synthesis_netlist.py`、`workstation_recording_phase1_cdc.py` 的散列，逐份固定网表、实际 SDC、回归 JSON 与完整命令。提案与先前独立证明 `m10b-boundary-proposed-v1.sdc` 的原始 bytes 相同。

组合根仅在显式 M／W DEMO 分支选择独立的 `demo_boundary_cdc` 元数据，固定 policy、role、helper 路径与散列、四条新增文本；它不占用旧 `demo_runtime_timing` 元数据。实际结构审计返回的 `inventory_role` 必须与选定 role 一致。旧候选缺少新元数据时，只允许四条新文本全部不存在；此兼容分支不要求旧 stage 补入新 helper。

主线程提供的 `demo-boundary-prepare-compatibility-v1.json` 已核对，SHA-256 为 `bdd10176fc51fa4215c82a0fdc90f3d83ae4b7684f82b88d9cd5c67e710e459e`。其中旧 M10b／W9b 的新元数据均为空，新 M11／W10 独立选择冻结 helper，四份 `verify_prepared` 均通过。其身份和输入散列完整保存在配套 JSON；prepare 通过不代表新综合、路由或实板通过。

## 2. 唯一的四条新增约束

```tcl
set_false_path -from [get_pins {u_managed/runtime/delay_dma/watchdog_fault_s*/Q u_managed/runtime/delay_dma/protocol_fault_s*/Q u_managed/runtime/delay_dma/peer_fault_s*/Q}] -to [get_pins {u_managed/runtime/service/workstation/runtime_effects.effects/dma_fault_meta_s*/D}]
set_max_delay 2.000 -from [get_pins {u_managed/runtime/service/workstation/runtime_effects.effects/dma_fault_meta_s*/Q}] -to [get_pins {u_managed/runtime/service/workstation/runtime_effects.effects/dma_fault_sync_s*/D}]
set_false_path -from [get_pins {u_native_usb/input_owner/queue_release_5_s*/Q}] -to [get_pins {u_native_usb/input_owner/events/fifo/unbuffered/write_domain_reset/release_q_0_s*/CLEAR u_native_usb/input_owner/events/fifo/unbuffered/write_domain_reset/release_q_1_s*/CLEAR}]
set_max_delay 2.000 -from [get_pins {u_native_usb/input_owner/events/fifo/unbuffered/write_domain_reset/release_q_0_s*/Q}] -to [get_pins {u_native_usb/input_owner/events/fifo/unbuffered/write_domain_reset/release_q_1_s*/D}]
```

11 个不同选择器在每份实际映射中都必须各自只命中一个真实 pin，四条文本必须各出现一次。第一条仅从三个已证明的 memory 域 sticky fault Q 到 audio 首级 D；第三条仅从第六级 audio queue release Q 到两个 USB 接收 CLEAR。两对后级 Q→D 各保留 2 ns 数据上限。13 个功能写指针 CLEAR 的 recovery／removal 没有新增例外。

SDC 审计同时检查完整候选 SDC：缺失、重复、放宽或改投后级的命令均失败；额外 false path、后级更弱 max delay、时钟目标／无目标 max delay、功能 CLEAR 的 min delay、后级 multicycle 和覆盖相关时钟的 clock-group 均失败。空格或 tab 缩进不能隐藏这些命令。既有其他例外若在名字上命中受保护寄存器，必须用其显式源 Q 的完整真实闭包证明没有到受保护 pin 的路径。

## 3. DMA fault 的完整真实结构

`u_managed/runtime/delay_dma/{watchdog_fault,protocol_fault,peer_fault}` 均为 memory clock 的 DFFCE，INIT 为 0，D 恒为 1，CLEAR 精确为 `!memory_release[2]`；CE 可以保持或置位，源状态只能保持或变为 1。三个 Q 到 `runtime_effects.effects/dma_fault_meta/D` 的完整布尔式精确为三输入 OR。meta／sync 都是 audio clock、CE 恒开、INIT 为 0 的 DFFCE，CLEAR 精确为 `!compute_release[2]`；meta Q 只有 sync D 一个消费者，直接连接且没有组合逻辑、额外 primitive 或顶层输出。

每个 fault Q 的完整消费者都逐一核对，三个源的闭包完全相同。两角色共同的 FF 端点清单为：DMA `applied_rate_44100_o/CE`、`chunk_buf[255:0]/CE`、`popped_sample[63:0]/CE`、`rptr[31:2]/CE`、`rsp_hold[255:0]/CE`、`state[0]/CE`、`wptr[31:1]/CE`，read FIFO 的 `g_large_head.full_q/D`、`write_binary[9:0]/CE`、`write_gray[8:0]/CE`，以及唯一跨到 audio 的 `dma_fault_meta/D`，共 660 个端点。

| 实际角色清单 | 在共同清单外的精确端点 | 每个源的 FF 总数与时钟域 |
|---|---|---|
| M10b | DMA `state[2:1]/D`、`wptr[0]/D` | 663：memory 662、audio 1 |
| W9b | DMA `state[3:1]/CE`、`wptr[0]/CE` | 664：memory 663、audio 1 |

这是两套真实综合网表的状态机与使能映射差异。工具先按完整 fault 闭包精确匹配角色，再要求其他两个 fault 及 USB queue 闭包匹配同一角色；不按时钟或前缀过滤额外消费者来容纳变化。

两角色的 read FIFO opaque 消费者清单相同：综合 VG 为四个 `SDPX9B/CEA`；物理 VO 为原四个加四个明确的 `gowin_add_SDPX9B_` 拆分块，共八个 `CEA`。每个 RAM 的 CLKA 为 memory、CLKB 为 audio，数量、名字和 pin 均精确匹配。完整闭包中没有顶层导出。

## 4. USB FIFO reset 的完整真实结构

`u_native_usb/input_owner/queue_release[5:0]` 是六个 audio DFFCE，CE 恒开、INIT 为 0，首级 D 恒 1，后级逐级直接接前级 Q；前五级各只有下一级 D 一个消费者。共同输入复位精确为 `!event_release[2] || !connected || panic_flush`，三个条件生产者均在 USB 域。写接收断言精确为该式再 OR `!queue_release[5]`。

`events/fifo/unbuffered/write_domain_reset/release_q[1:0]` 是两个真实 USB 边沿的 DFFCE，CE 恒开、INIT 为 0、共同异步 CLEAR；首级 D 为 1，次级 D 直连首级 Q，首级没有其他消费者。功能写复位精确为最终 Q 的反相，只拥有 `produce_w_bin[6:0]` 和 `produce_w_gry[5:0]` 共 13 个真实 USB 指针 CLEAR。

第六级 queue Q 的共同完整 FF 消费者为：`u_managed/control_cdc` 的 `acknowledge_toggle/CE`、`response_held[32:0]/CE`；`u_managed/events/queue` 的 `count[1:0]/D`、两组 `data[17:0]` 和 `first[1:0]` 各自的 D／CE；USB event FIFO 的 `r_rdy/CE`、`consume_r_bin[6:0]/D`、`consume_r_gry[6:0]/CE`、原 `rst_cdc` 两级 PRESET；上述两级 write release CLEAR、`stopped_clock_queue_fence.drain_release[5:0]/CLEAR` 和 `queue_write_release[0]/D`，共 138 个端点。

| 实际角色清单 | 在共同清单外的精确端点 | FF 总数与时钟域 |
|---|---|---|
| M10b | `u_managed/events/queue/tail/CE`、`input_owner/settled_sync[0]/D` | 140：audio 136、USB 4 |
| W9b | `u_managed/events/queue/tail/D` | 139：audio 136、USB 3 |

两者另有同一个 packet `SDPX9B` 的 ADB／OCE 两个 opaque 端点，写时钟 USB、读时钟 audio，没有顶层输出。W 实际 tail 映射由 CE 改为 D，且移除了 settled 接收；M／W 的 RAM 清单没有差异。已有 `queue_write_release[0]/D` 和 M 的 `settled_sync[0]/D` 属于其他已拥有的 CDC 边界，本提案没有重新生成或扩大其例外。

W9b 实际 VG 还独立运行了原 `workstation_usb_fifo_reset.audit_synthesis`：真实 packet RAM CEA 在最终 USB release 前不可写，真实 producer Q0 仅随该实际写入翻转，13 个功能指针继续由本地最终 release 复位。结果保存在 `w9b-usb-fifo-admission-baseline-v1.json`，并由配套 JSON 固定散列。

## 5. 四份实际网表与负例结果

| 输入 | 原始网表 SHA-256 | 6 项测试耗时 | 拒绝负例 |
|---|---|---:|---:|
| M10b 综合 VG | `60b346962d8e467716c7ce664159932d948c823118daa964d7d1539921dcf229` | 271.167 s | 60/60 |
| M10b 默认 routed VO | `aac27852489ac943d9d2729a3eb28267d7af2553b86b7789d70a26f06a1f9232` | 247.464 s | 60/60 |
| W9b 综合 VG | `990302b2e222ef67b3c1cf6d0df555c0a02a55b281776e3ef44cc1c7d358ea1f` | 298.411 s | 60/60 |
| W9b 默认 routed VO | `1e02364a2682980746aae97bfa7206b27dfef353e5475edb1e64fa3b6e8c091e` | 271.532 s | 60/60 |

每份的 6 项为 3 项元数据／选择测试和 3 项实际结构／SDC 测试；60 个负例发生在实际结构／SDC 测试内部。四份并行运行，表中时间是各测试进程实测耗时。负例覆盖源时钟、sticky D、OR 真值、CE／reset／INIT、跳级、额外 FF／opaque／顶层消费者、原始网表 duplicate／未解析 named port，以及本报告第 2 节的各类时序覆盖命令。

VG 使用严格完整层级解析，VO 另对整个平坦模块的所有 primitive 和 named port 做独立词法清点；没有为通过审计改写候选网表、修改公共 parser 或只解析相关前缀。完整命令通过 `GW138K_DEMO_BOUNDARY_NETLIST`、`MAPPING`、`ROLE`、`SDC`、`EVIDENCE` 指定真实输入后运行 `sim/test_workstation_demo_boundary_cdc.py`；每次的绝对路径和完整环境变量名见配套 JSON 中 `actual_mapping_inventories[].run.command`。

## 6. 新候选仍须完成的门禁

旧 M10b 的 DMA fault 跨域首级 setup 与 USB write-release CLEAR recovery 负路径只是本次调查的触发，不能据局部结构证明改记旧位流通过。后续候选必须重新验证实际 VG／VO 的完整清单和角色、选择器唯一性、两对后级 2 ns routed 飞行时间，以及 13 个功能写指针和其他业务复位的真实 recovery／removal。

此工具不证明模拟亚稳态 MTBF、最小异步复位脉宽、整机 setup／hold／recovery／removal、CDC 总体闭合或物理资源收益。M11／W10 的新综合与物理结果由各自整机严格门和新候选证据记录；其真实 I2S／DAC、HDMI 声画与参数一致性、持续业务共存仍须实板验证。单板分时测试仍不能登记为双板并发验收。

MIDI ACK 提案、`CLOCK_LOC`／时钟资源重分配和同步 reference48 hold 均未混入这四条边界约束。旧候选输入保持可回退；本报告不改变 SRAM／Flash 部署身份。
