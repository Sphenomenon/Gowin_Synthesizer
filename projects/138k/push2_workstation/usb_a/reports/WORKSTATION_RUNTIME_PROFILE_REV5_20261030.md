# Revision 5：媒体准备接回双采样率整机

日期：2026-10-30（Asia/Shanghai）。本阶段在显式 native runtime profile 中接回媒体准备事务：AE350 首入口保留持音，先正常封存受控 REC／BLE 对象、取消 score、实际停止 TF，再请求唯一采样率核心。新增状态属于各自 owner，顶层只做组合；没有新增 MIDI CC、页面或 BLE 线协议。这里交付来源、综合及部分 CDC 离线检查点，整机任务方框保持未完成。

## 最终来源身份

最终 prepare：`/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev5-v3`；候选 `custom138k-workstation-v1-f1be50e853d3700a`。完整输入 SHA256 为 `f1be50e853d3700ae0517b8616dd8b0578deb1d872324d0a9e03165efa716cdf`，配置 SHA256 为 `ad36e3cec3f541ae15a66d7b4c179b633cd70dfa145267464a03ddf8c54f0eeb`。313 项来源锁、734 项源码快照、570 项 staged 文件，259 项启用输入；256 个 HDL 单元、288 个 module、2 个 package。

完整来源及配置见 [runtime_profile_rev5.json](workstation_task_20261030/runtime_profile_rev5.json)，逐编译单元与 include 归属见 [runtime_profile_rev5_source_audit.json](workstation_task_20261030/runtime_profile_rev5_source_audit.json)，验证命令和输入身份见 [runtime_profile_rev5_verification.json](workstation_task_20261030/runtime_profile_rev5_verification.json)。本阶段继续使用既有 prepare／综合入口；没有新增编号生产 builder，冻结 baseline、vendor、原网表与历史证据保持原字节。

`workstation_media_preparation` 只聚合 runtime 与 BLE 的实际终态并保持 fence。runtime 内部继续拥有 REC／score 及 TF stop；BLE 继续拥有对象、CRC 和线协议。`tf_stop_pending` 真实接回 bridge；TF 使用 token-qualified FIFO／DMA clear ACK，最后 inactive mailbox 必须得到目的端 ACK。BLE `source_allowed` 不受媒体 hold 遮挡，以免正常封存被误判为 source loss。切换准入先判断平台 memory guard，媒体准备结束后再查核心 ready，避免 TF busy 导致 stop 永远无法发出。

CPU observer reset 不撤销已开始的媒体事务，也不解除 compute hold。媒体超时、失败和迟到结果不能自动发起旧命令。失败类别 1—8 保留 TF 原因，9 为本地封存、10 为 BLE 封存、11 为 backend admission；11 要求新的调用者决策，不自动重试。首个入口仍是 AE350 checked-MMIO API，页面随后复用。835 项 host 检查和两次 RV32 构建通过，submit／poll 最多 9／11 次访问；安装 ROM 为 `c598c50aa0172be1c5644fa50a17c4a18ea304cce7aaeca476cd55b7dba0e752`，binary 12,380 B，RAM end 572／8,192 B，栈保留 7,620 B。此容量和模型测试不证明实际启动、完整调用链或实板时限。

受控短 REC 的格式限制、BLE format 1 的 48 kHz 限制继续保留；44.1 kHz observation 不能冒充 48 kHz 录音。TF 仍使用 DDR 文件中转，只接受当前已应用采样率匹配的 WAV。原生 SD sector owner 已另行离线验证，但本 profile 尚未选择它；R00 DDR PCM backend 也未在此候选集成。不能据本阶段声称长录音、完整 TF 流式迁移或手机业务闭环。

## 真实综合与失败保全

| 候选 | 结果 | VG SHA256 |
| --- | --- | --- |
| `45fe05aa60554f78` | 综合 rc0，但组合环门禁失败 | `041643d6f790e830c9b5bea69e9e8a27cdd459720e99b1e882a88f9c17271a57` |
| `9106b1aaffd290c6` | 综合通过，但旧 USB setup cut 阻断 CDC 安装 | `4d56dc8e4738d43de22cf9fc72d6b2c9c53256ad8a3366c68c27444e719b0cb0` |
| `f1be50e853d3700a` | 综合及本批实际 CDC 检查通过；完整门禁待办 | `8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535` |

最终综合耗时 484.055 s，Logic 120,981／138,240、Register 61,345／139,095、BSRAM 268／340（综合统计）。331 条剩余警告与 9106 按路径／行号归一后逐条相同，AG 诊断为零；不将其余警告视为无害。

最终独立静态 inventory 重建了 AE350 4096 个 ROM 字、唯一共享 2048 点双声道 FFT、XY／peak 与两级 hold DFFPE；289 个综合网表层级与资源归属保持。新旧 VG 内部 net／port alias 有变化，因此没有声称网表逻辑等价或完整 feature acceptance；证据在 [runtime_rev5_static_inventory.json](workstation_task_20261030/runtime_rev5_static_inventory.json)。

三份候选分别保留原身份和不可变 prepare，570 项输入在综合前后及父级复核时重新计算 SHA256。所有工具、日志、VG／资源报告和逐项输入在 [runtime_rev5_synthesis.json](workstation_task_20261030/runtime_rev5_synthesis.json)。EDA 使用 `/private/tmp/gw138k-build.lock`，没有并行综合或改写旧 process。综合资源与物理资源分列；本阶段没有 P&R、位流或板卡操作。

首次候选 45fe 的工具退出码为零，但出现 AG0100×6／AG0101×2：Gowin 将混合异步清零／置位的 `hold_compute` 映射成自反馈 LUT。后续 [hold-fence 修复](WORKSTATION_RUNTIME_MEDIA_HOLD_FENCE_20261030.md)使用共同 reset／hold 的异步 PRESET，两拍真实 compute 边沿释放；RTL、官方原语门级及负控已独立验证。9106 完整 VG 已确认两个 DFFPE、无该组合环，但实际 SDC 仍有旧 USB 混合 setup cut，因此也未通过已审 CDC 安装检查。两次失败均未追改为成功结果。

最终 shared-constraint adapter 仅从已锁定旧行移除 `queue_write_release_0*/D`，保留 settled／panic／defaults 三成员；不受检的形状漂移直接拒绝。其余旧混合 query 继续逐成员保留有效端点，不能通过删除整行掩盖缺口。

## CDC 范围及负控

第二批 policy 为 `native-runtime-cdc-gray-media-fence-v2`，53 行精确约束。21 组／400 bit Gray 同步路径保留源周期以内的传播上限；实际 token-qualified TF FIFO 为直接两级，read pointer MSB 使用已核验的 registered binary alias。新增媒体 request 两级、ACK 三级、held failure 两级；ACK 的实际 enabled transition 与 failure 更新事件进行完整小 Boolean 锥枚举，支持实际 Gowin 的 D 或 CE 门控等价形态，同时拒绝错误 CE／D。

compute hold 为两级共同 PRESET，USB 为六级 queue release、六级 drain release及两级 write release。检查器核对真实时钟、复位、CE、D/Q、首级扇出和 Boolean reset／ready 锥。hold PRESET 与 drain CLEAR 共八个端点的例外检查独立于 `-from`；禁止额外 false path，max delay 只允许两条精确 assertion bound，保留 recovery／removal。原检查器的 get_ports／任意 Q／get_regs 过滤绕过已有独立复现及修复负控。

| 验证 | 结果 | 接受范围 |
| --- | --- | --- |
| 实际 profile／来源 | 18／18；12／12 | 实际 runtime 与默认 prepare、闭包篡改、256 单元、端口和来源 |
| AE350 API／构建 | 835 host checks；两次 RV32；固件 9／9 | ASAN／UBSAN、MMIO 上界、确定性 ELF／binary／ROM |
| 已接受来源边界 | 10／10 | accepted／pinned 选源隔离 |
| 真实 runtime＋TF＋BLE | 10 场景、6 负控通过 | 140 个物理／观察帧，35 个 eligible BLE 帧均采集，TF 请求／返回／最后 mailbox 排空 |
| 默认 runtime | 1,078 物理＝观察帧，977 非零 | 双率、FFT／APB、USB／CPU 输入与原生命周期；不是默认启用媒体政策 |
| 实际时钟／DCS | 4／4，23 负控拒绝 | 16 个声明、可见 PLL／divider／DCS／serial 端点；完整物理时钟仍未接受 |
| 实际 CDC 第二批 | 25／25，77 负控拒绝 | 21／400 Gray、media／hold／USB fence、真实安装 SDC；完整 CDC 仍未接受 |

本批 actual CDC 为非 endpoint-development 模式，`candidate_constraints_installed=true`，完整来源在检查前后保持。详细范围、失败保全和负控见 [CDC 专项报告](WORKSTATION_RUNTIME_CDC_MEDIA_FENCE_20261030.md)。离线 P&R F7 已准备，CST 仅追加维护的 ULPI LVCMOS33 声明，SDC 原字节保留；准备清单及实验脚本完整源码在 [runtime_rev5_physical_f7_prepare.json](workstation_task_20261030/runtime_rev5_physical_f7_prepare.json)，尚未启动 P&R。

这些结果只覆盖已审端点和精确 SDC 文本。完整 held payload、FIFO RAM 所有权／碰撞、其他 level／pulse、全量 reset、工具 query 实际解析、routed propagation／skew、recovery／removal／pulse、PLL 及整机 feature preservation 仍需关闭。所有完整 CDC／STA／硬件接受字段保持 false；checker fixture、旧 VG 或局部边界通过不能替代真实新候选。

## 后续与回退

默认 prepare 保留旧 AE350 ROM 和关闭的媒体扩展；accepted、pinned 与独立 resource 入口均不选择本 profile。源码回退可省略显式 profile，恢复默认 native 路径。板上没有本阶段部署，无需因本阶段执行硬件回退。

用户已授权综合、SRAM 和探针迭代，并告知 SD 已插入、25K 已接 138K USB2 High-Speed 口；这些连接信息不作为枚举、协商速度或实板功能证据。后续先进行独立且不可部署的 P&R 资源试验，完整物理与功能门禁通过后才运行 SRAM／读回／真实声画和外设测试。用户追加允许在 CLK／BSRAM 压力下两次布局布线仍难成功时舍弃曲谱引导及 CNN；当前候选仍保留这些功能，届时须新配置、新身份和实际资源差异。Flash 尚无本轮写入授权。
