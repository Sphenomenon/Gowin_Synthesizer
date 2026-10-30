# R00 生产 owner8：父级来源与真实链路复验（2026-10-30）

父级已导入隔离提交 `a62070710cdbe2f65dd7d326bd94654d614b6348`，在主工作区刷新三份显式 profile 的来源锁并重新 prepare。`custom138k-workstation-r00-v1` 实际选择最终物理 PCM→非阻塞 CDC→录音对象服务→native-accept bridge→HDMI DDR owner8，AE350 APB 页为 `0xf8040000`。这次完成了生产接线，仍未完成 BLE 存储迁移、长录音或物理接受。

| 父级新 prepare | 候选身份末段 | source锁／snapshot／staged／enabled |
|---|---|---|
| R00 | `4b1436d83219e765` | 338／753／583／266 |
| 保留识别的 runtime | `610c08c529757eff` | 338／748／570／259 |
| no-CNN runtime | `fe1d10705e82e413` | 338／748／571／259 |

新 R00 从 no-CNN 配置派生，默认及原 runtime 不选择录音 owner8。旧两配置只刷新来源锁和未选择的依赖，不增加 `recording_policy`；宏隔离回归证明原 top／HDMI 四种默认分支的预处理 token 与基点一致。新 no-CNN staged 相比前序 `60cae14e43255a2b` 只有三份 RTL 与 top 兼容副本共四项字节变化，未增删文件；不是旧候选物理接受的延续。

父级真实 runtime fixture **13正向＋5负控全通过**，身份为 `r00-runtime-owner8-offline-v1-34144ee774b2c86e`，与最终独立 fixture 一致。它通过实际 observation／APB CDC、service/backend、native bridge、owner8 queues/core 和有序DDR模型，核验立体声字节、序号回绕、两种采样率描述、不可变对象及非对齐范围读取、慢速CPU窗口、正常封存、native尚未接受时取消、已接受读返回排空、observer reset、源间断／超时／上下文变化及故障隔离。其它 runtime／BLE 媒体 owner 使用终态握手 fixture，没有据此声称实际采样时钟核或全板顶层仿真通过。

独立仿真发现并修复了三个真实边界：hold与单拍seal request同时到达时的丢请求；无valid的投机FIFO error污染录音；aggregate bus error经backend ready反馈造成组合环。相关负控分别恢复错误实现并要求命中对应故障。另用真实16-entry observation FIFO溢出证明当前fail-closed规则：未录音时丢帧也拒绝后续CREATE，CPU observer reset不恢复，必须共同controller／ledger／backend reset后才能新建；恢复后的9帧逐字节正确。该规则已写入契约。

父级额外回归均无skip：三配置来源审计各12项、R00 profile7项、原profile20项、识别profile7项、AE350固件10项、C API1项、accepted输入10项。旧媒体准备9场景／193项默认检查通过。独立child v5 prepare还核验实际GPRJ/provider预处理、owner8 native_accept[8]与成对client_rdata、共同UI reset、物理PCM、APB及第三媒体owner；其candidate为 `5775b90535632253`，父级新身份单独记录。

录音API仅R00 opt-in编入；旧两配置ROM均为 `c598c50aa0172be1c5644fa50a17c4a18ea304cce7aaeca476cd55b7dba0e752`，保持原字节。R00 ROM为 `c88468fa4833dbbd625a4c2cefdcbb7855584b43582dc65afc65f8b15bf41dc4`，14,052／16,384字节，静态RAM60字节、保留stack容量7,620字节；没有全程序stack上界或实测水位证明。录制中poll跨多个寄存器，是动态诊断，不能称原子快照；download显式POP后提供不可变32-byte窗口。

DDR分配继续由维护 `ddr_address_map.vh` 管理，R00只在原baseline map上校验追加，既有宏不改。当前单对象上限仍16,384帧／64KiB，BLE仍保留原片内短录音和业务绑定；没有净BSRAM收益、BLE下载、CRC／可靠传输、掉电保存或长录音接受。独立原生owner8／backend既有回归结果保留，但不转移为完整工作站验收。

另外发现此前维护map增加录音分区后，accepted clean prepare被旧live-map drift guard拒绝。该失败未因本次集成放宽；锁定历史map的来源修复已独立交付，随后分阶段移植及重跑clean三prepare。accepted输入10项通过不抵消这项已知失败。

本阶段未综合、P&R或操作板卡。FC的STA失败仍只属于旧 `525ffff10d622031`，新R00的完整CDC／reset／RAM数据弧／PLL、双模式STA、功能与硬件均须重验。父级prepare、锁刷新、全部测试及独立证据索引见[机器记录](workstation_task_20261030/r00_production_parent_integration.json)；隔离实现说明保留于[child记录](workstation_task_20261030/r00_production_source_stage.md)。R00／R01／R02及部署门禁保持未完成。
