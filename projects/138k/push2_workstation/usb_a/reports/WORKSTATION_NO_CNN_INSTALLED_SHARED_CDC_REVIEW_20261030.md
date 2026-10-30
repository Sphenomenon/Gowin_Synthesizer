# no-CNN 实际 shared CDC：父级数字结构复验（2026-10-30）

父级已在独立副本重跑 `custom138k-workstation-no-cnn-v1-525ffff10d622031` 实际安装 shared 约束审计，结果与原交付逐字相同，14 个实际网表对象负控全部被拒绝。该审查使用封存副本中的 600 项工具输入，运行前后核验完整 571 项 staged；没有修改主线工具、网表、约束或板卡。复验 SHA256 为 `0eab34c5c3399a7054a7526de2f36c2f356de1038e2e3c838fb72a4ed8e090f5`。

旧通用 `audit_shared_cdc()` 面向 generic 157 行，直接在 runtime 候选调用会拒绝已被 runtime 退役的 `u_video/u_renderer/u_capture/held_*`。这属于审计器 profile 不匹配，不能称为已安装约束含空 query。实际选择链是 generic 157 → runtime 105（省略52／适配4）→ no-CNN 88（再精确移除17）；全 SDC 的 CNN 移除总数为19。原通用检查器及其拒绝结果保留，新 cache 审查没有静默放过空可见端点。

| 结构范围 | 结果与界限 |
|---|---|
| 43 个 false-path 首级位 | 逐位生产者、首 D、时钟、CE、共用 CLEAR、唯一 Q 驱动和完整首 Q 消费者；42条直连、1条精确同步清零门 |
| 8组／182个 Gray 首级位 | 真实注册生产者、逐位首 D 与次级移位、完整跨域消费者；Gray 序列及物理相干未接受 |
| 14组／1,308个保持数据位 | 实际存活位索引、源／目标时钟与完整源消费者；20个 scanout capture D 穷举证明采集或自保持方程，稳定期／握手行为仍待另验 |
| 89个唯一 query／127个成员 | 可见成员各自必命中，联合 query 不能掩盖空成员；13个精确 DDR 内部 query 明列 deferred |
| 110个 reset／primitive pin | 解析和列举通过，不代表复位语义或 recovery／removal 接受 |

DDR recovery 的特殊路径逐项证明 `first D = calibrated & controller_reset_n`、`second D = first Q & 同一 controller_reset_n`，并核验门控生产者为同域注册输出。不是容许任意首／次级间组合逻辑；两个 AND→OR 负控均被拒绝。七个状态生产锥含 LUT，未称为注册 toggle、无毛刺或满足脉宽。

Playlist 的 `read_gray*`／`write_gray*` 宽匹配同时命中 meta／sync；真实生产者另行登记，read MSB 使用实际 `read_binary_2` 别名，局部四个 RAM16SDP4/WRE 消费者及其时钟单列。首 Q、Gray 源及保持数据的完整消费者均检查到顶层输出和已知 RAM 输入，不能用声明的 D 端点代替完整扇出。

封存包位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-cdc-review-v1`，父级副本为 `no-cnn-cdc-review-parent`。25项原seal文件、600项工具复制输入和完整 stage 均重hash；原manifest SHA256为 `fd60459b65507878216b791e56416462dc0108cc6e7de7c5fd7124eb8660e120`。选择清单、负控及证据索引见[机器记录](workstation_task_20261030/no_cnn_installed_shared_cdc_parent_review.json)。

本检查器仍是独立 cache 审查，维护版本及明确 profile 调度随后集成。观察 RAM 参数／端口相同不转移旧物理证明；其周围两处 `write_fire_s2/s3` 是 LUT4，非 FF。全部 CDC／复位、状态脉冲与保持协议、RAM 数据时序、DDR 内部、两模式 routed timing、PLL 及硬件接受仍未完成，部署门禁保持 false。
