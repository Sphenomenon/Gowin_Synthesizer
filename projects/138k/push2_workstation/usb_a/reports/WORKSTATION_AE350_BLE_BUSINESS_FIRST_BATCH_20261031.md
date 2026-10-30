# AE350 BLE 业务第一批：真实 C owner 与独立候选

日期：2026-10-31。输入以 `3f8cf5f74820dbe4f079784537d163d2c241f919` 当前主线为父级，保留 C02 PANIC 修复、C06 64-KiB 冷启动和 TF 源码。首批实现录音业务中的八槽任务表、三类 ID 和录音／传输开关命令；**C01/C03 整体迁移尚未完成**。下载 READ／ACK／恢复／30 秒超时策略留给明确的第二批。

唯一选择入口是 `custom138k-workstation-ae350-business-v1`。默认、accepted、25K 和 vendor 不选择本批业务 owner。源码与内部接口说明见 [native contract](../rtl/bluetooth/cpu_owner/CONTRACT.md)；外部 BLE 线规继续使用原协议，未另建 opcode 或格式。父级证据索引见 [receipt](workstation_task_20261030/ae350_ble_business_parent.json)。

## 实际运行边界

| Owner | 本批实际职责 |
| --- | --- |
| AE350 `ble_business_owner.c` | 唯一 `tasks[8]`，operation/object/transfer 单调 ID；`04`、`20/21/22/23`、全部 OPEN 模式、CLOSE/CANCEL 的业务决策；任务保留时间按真实首帧／终态时间 |
| 138K native parser | 分片、CRC、nonce/session、高水位和精确请求重放；原 S1a mailbox；原响应缓存与线上字节构造 |
| Physical data engine | C 提供的 borrowed tags；采集、四字节 CRC、raw DDR、native drain/seal/fetch、Rice、四 transfer banks 和 wire framing；READ/ACK/resume/timeout 暂留 |
| 现有独立 R00 | `f8040000`、object64、首个 64-KiB DDR window 保持；未与 BLE32 任务／对象混为一份状态 |

真实固件定义 `A138_BLE_BUSINESS`，链接 C owner、mailbox 和新增 physical helpers，C02 在初始化和有界服务点调用 init/pump。新 APB `f8050000` 经实际 `gw138k_apb_cdc` 到 50 MHz，再穿过 workstation/GATT/core/parser 的原生端口；未用未调用的 C 文件充数。`f8050000..ff` 沿用 S1a ABI，`f8050100..1ff` 是独立 probed primitive。BLE 仍只用既有第二个 64-KiB DDR 区，容量 16,384 stereo frames；并非已实现长录音或 44.1-kHz BLE 格式。

选择器只复制 versioned native 字节，并从 staged tree 和编译列表移除旧 `ble_recording.v`。生产不执行旧 recorder text adaptation；旧 RTL 仅作为对照测试输入。原 Rice encoder、transfer banks、wire-message function 有受保护的逐字节哈希检查。顶层新增 decode/CDC/接线，无任务或录音业务状态表。

## 提交、观察与失败

START 的 PENDING 必须先有真实 raw START 接受；任务在首个完整 PCM/CRC 帧后成功。容量一帧直接进入封口的路径也记录首帧时间。STOP 任务等实际 READY/native committed prefix；零帧对象在封口后让 START 任务失败；CLEAR 等实际 raw completion。

physical final submit 丢 ACK 仅观察同序号；1000 ms 仍未 accepted 则 `SUBMIT_UNOBSERVED` fence，不重发、不提交候选 ID。mailbox COMPLETE 丢 ACK 仅观察原完整键；1000 ms 无 RESULT/PUBLISHED 则 `COMPLETE_UNOBSERVED` fence，真实任务与采集继续。读取 state/key/meta 撕裂产生的 advisory STALE 留在 OBSERVE，不能当作请求已经作废；独立 coherent context 的 session 变化才结束旧发布观察。CPU observer reset 不能清空计数后重用旧 boot，primitive 保留 sticky fence，实际对象、采集及自主 seal 仍存在。

新增 physical helpers 只在 `A138_BLE_BUSINESS` 下编译。用同一 xPack 工具链分别重建父级与本批的默认／recording API 两个 16-KiB 路径，binary 与 ROM 均逐字相同：默认 14,428 B、recording API 16,100 B。accepted locked 输入另过既有 source regression。

## 离线验证

最终 actual C/APB/parser/raw-DDR cosim 为 `cosim-final-v4`，794 checks：322 主路径、316 边界、13 未提交 primitive、15 未提交 COMPLETE、15 真实 APB 撕裂、33 零帧、四个 CRC 字节阶段各 20。35 条完整 response/data-block 与锁定旧 RTL 逐字相同，包括 START/READ 精确重放、所有 OPEN 模式和 CANCEL、nonce/CRC/错误响应。

实际 DDR fixture 分离本地 slot、native acceptance 与 read return，PCM 用真实 48-kHz 分数节拍；测试不伪造采集结果。覆盖八槽满表／60 秒保留／三类 ID 耗尽、慢 CPU、CPU 停服务时采集与自主 seal、四个 CRC 阶段完整前缀、重连和 observer reset。六个实际运行 C 变异都被拒绝：跳过满表限制、首帧前成功、错误 object ID、移除两类不确定提交期限、撕裂时错误退出观察。不是只搜索源码 token 的负控。

补充检查：native 五层 glue 全 elaboration；显式 profile/source tamper 与实际 prepared closure 八项；默认 firmware 十项；recording API、callback stack 四项、accepted source 十七项；原 raw-DDR 两种时钟/FIFO 配置与五个行为负控、精确 lint 清单；Delay FIFO 维持原功能／provenance 检查。未运行 Gowin、P&R 或板卡动作。

## 固件和最终候选

统一 xPack GCC 15.2，RV32IM+CSR+fence.i；仅显式业务选择加 `-fno-jump-tables`，避免未证明的编译器内部间接跳转。真实 ELF/call graph/stack-usage/disassembly 闭包绑定全部固件输入、63 个 actual indirect sites、逐个 32-bit 指令及审阅目标集合；默认未知间接仍拒绝。

| 项目 | 数字 |
| --- | --- |
| 物理 boot ROM / ILM / DLM | 各 65,536 B |
| Cold binary / text / initialized data / BSS | 26,864 / 26,848 / 16 / 528 B |
| ILM runtime / DLM static span | 26,256 / 544 B |
| 保守调用链栈 / 保留栈 | 1,328 / 16,384 B |
| 固件 binary SHA256 | `876d504030bf67c4f1de984458a87ad821cc3f5dab48b0e5c311896a70d75137` |
| Boot ROM SHA256 | `6f3abefcb4fb3d6e5ab813357e62bf0203cf1578f0b791797ba3c2720b5ce2b7` |

真实 `prepare-final-v4` 选择 271 个编译输入，候选 `custom138k-workstation-ae350-business-v1-9c0f652c977f2323`，配置 SHA256 `ed438e9743cea2e9c653248657eec5699567202d45db7bf7c6f3a541045400a3`。其 612 项 staged 输入与 `prepare-final-v3` 完全相同；变化仅为父级时钟审计工具来源身份。原始 ELF、ROM、输入表和回归日志放在外部 seal 目录，源码树不放生成数据库／波形／位流。

这些是源码和 offline prepare 结果，未证明资源净减少、物理 BSRAM、整机 routed timing/CDC、实际 CPU 性能/栈水位、硬件 ILM/DLM/cache 行为、真实录音 tap、Android、SRAM 或 Flash。回退使用原 no-panel profile 或已记录的独立部署；不将本候选冒充 accepted 或板上当前镜像。后续必须对同功能的迁移前后真实综合／资源及时序比较，再进行单独授权的物理候选和读回验收。
