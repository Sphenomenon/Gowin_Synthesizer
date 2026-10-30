# 录音 DDR 存储基础父级检查点（2026-10-30）

本阶段接入尚未选择的 BLE 原始 PCM 存储和 DDR controller／ledger 代际资格组件，并把现有 CPU 后端明确绑定到原地址子区。BLE 对象、任务、CRC 和下载业务仍归原 owner；容量保持 16,384 帧。新组件尚未进入生产编译清单，没有整机资源收益或长录音接受。

## 地址与资格

唯一地址权威仍为 `rtl/ddr_address_map.vh`。既有宏和分配保持，新增十个显式子区宏：

| 使用者 | 字节地址 | native word 地址 | 容量 |
|---|---|---|---|
| CPU R00 | `30500000..3050ffff` | `0c140000..0c143fff` | 64 KiB |
| BLE raw | `30510000..3051ffff` | `0c144000..0c147fff` | 64 KiB |

CPU 数值地址未变；后端的容量、单位、边界与不重叠检查同步更新。首次旧 runner 因未登记的新宏拒绝执行，原日志保留；现在只允许这十项新增，并执行三项新的几何负控，44 cases 全过、严格 lint 零警告。

新 authority 补上既有 memory guard 首次 ready 前的 ledger reset 缺口：第一条可接受全局请求的 memory edge 就记录 controller epoch；此后 ledger 丢失，包括停钟期间短脉冲和只含 BIST 的启动阶段，永久撤销录音通道资格，直到真实 common root reset。恢复 ready、局部 reset 或新对象不能重新开放。独立实际 queues／core／mux／双 bridge 反例与修复检查使用边界输入模拟 native 返回和恢复 ready，未模拟完整加密控制器或 BIST FSM，也未证明物理排空。

## BLE 原始存储与独立修复

raw store 仅保存 PCM，使用 65-bit 有界采集 FIFO、不可变请求／完成／状态／读返回邮箱，以及 8 KiB 同步读缓存；一次 fetch 最多 8,112 bytes。close 等实际 native 写接受后才报告 drained；clear 排空已发布交通后复用；超时和 transport／protocol fault 隔离通道。新增 protocol-fault 输出只取 bridge 已寄存的错误，供未来聚合，不能用包含广播输入的 inclusive fault 反馈形成组合环。

原版 `8b6e573` 的 RTL SHA 为 `2c6ebca8…`。独立测试发现最后合法 generation 的 START／CLEAR 若保持 valid，会被重复判定为新请求并报耗尽；`ad780c2` 增加 unseen-level 条件，区分持有请求与新的耗尽请求。byte-identical 原版作为第五个负控保留。最终含已寄存错误输出的 RTL SHA 为 `422a1bb4c3b0cf842b416b65f714d023c65b270d0fa5219f9adec1c72d290ede`；原 [raw store 阶段报告](WORKSTATION_BLE_RAW_DDR_STORE_20261030.md)仅描述其旧身份，不覆盖这次硬化。

父级最终 raw runner 两配置通过 94,742／93,244 checks、五个负控和四条精确登记 lint 警告；未知警告仍失败。独立四配置另通过 55,487 checks，覆盖不同 generation PCM、FIFO 回绕、八个 unpack 位置 clear、停钟和早期 START overflow、最后允许的 native／read timeout edge。authority 父级通过十相位、每相位 17 场景／666 checks、六负控；独立审还保留真实边界反例。父级逐项验证两个独立 seal 的 375 个文件及当前来源身份。

## Prepare、隔离与交付范围

四份来源锁仅更新 map 和 CPU backend 的 SHA。最终 v2 prepare 重新捕获硬化后的未选择源；与本阶段 v1 的全部 staged 字节相同。相较前一个 seal-release 检查点，enabled／no-CNN staged 不变，R00／no-panel 仅 CPU backend 及同一 map 的两个目的路径变化。

| 配置 | 新候选尾号 | staged／enabled |
|---|---|---|
| enabled | `b4d9fc44cca17532` | 571／260 |
| no-CNN | `e2ff7a5cb3a717c9` | 572／260 |
| R00 | `db8d9c9ddb607fba` | 584／267 |
| no-local-panel | `443063dee260d7cb` | 584／266 |

各 prepare 的来源回归 12 项通过；最终 enabled 的 Profile 20 项通过（一个未提供的历史 legacy prepare 可选项跳过）。accepted 来源 17 项、CPU 真实 runtime 14 场景／五负控通过；录音配置七项通过，其中两个独立 prepare 可选项跳过。完整身份、日志 SHA、输入校验及 seal 见 [父级机器证据](workstation_task_20261030/recording_storage_foundation_parent.json)。

尚待实际 BLE 五层适配／顶层／profile 选择、原始 RAM 退休与新缓存映射、新网表 CDC／reset／RAM 数据时序、完整物理时序和实板 PCM／下载验收。本阶段未综合、P&R、操作板卡或部署；R00／R01／R02 保持未完成。前序 PCM v2 综合和 FE 物理失败均保留原身份，不能转移。回退须同时恢复本阶段源、CPU 显式绑定和四份来源锁后重新 prepare；历史 sealed 输出未修改。
