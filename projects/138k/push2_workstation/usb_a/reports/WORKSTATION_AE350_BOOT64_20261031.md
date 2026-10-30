# C06：64 KiB 冷存储与 ILM／DLM 显式整机准备

新增 `custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1`，继承当前 no-panel 的音频、显示、录音和 BLE raw DDR 组合。它实际编译版本化的 `workstation_ae350_boot_memory.sv`，替换冻结 ROM owner：地址窗、索引和镜像均为 16384×32-bit（64 KiB），保留原 ABI 和 8 KiB scratch RAM。冷启动将代码／常量装入 64 KiB ILM，数据／BSS／16 KiB 栈放入 64 KiB DLM；运行容量和冷镜像容量分别检查。

导入作者提交 `277e725fe3abccc11b527a0517d4097f04834c67` 的 11 份精确 blob。新 profile 从当前主线 no-panel 重建，保留较新的 TF quiesce 等来源，而未照搬作者旧基底的配置。四个原 profile 仅刷新公共构建依赖哈希并补锁新 helper，继续选择原 PL 16 KiB ROM／8 KiB RAM；没有更改冻结基线、vendor、时钟、DDR 分配或协议。

## 父级验证

- 存储回归 4 项：16 KiB 新模块与冻结模块全部 4096 ROM 字及 4000 RAM 事务对照；64 KiB 全部 16384 字、末字、边界、无别名及空闲计数检查；真实超过 45000 bytes 的固件在旧容量失败、在新容量成功并执行上半镜像复制，再增加 32 KiB 时拒绝越界；唯一 owner、容量和硬核配置漂移拒绝。
- 启动／故障 12 项、固件 10 项、accepted source 17 项、profile source 6 项、runtime source 12 项全部通过。带 `GW138K_VERIFY_CLEAN_PREPARE=1` 的 baseline 23 项通过，包含无私有 staging 的三种完整 prepare。五个 profile 来源锁均加载成功。
- 新整机 prepare：`custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1-0a5c185263bc43fd`，600 staged／269 enabled；runtime audit 为 266 编译单元／298 modules／2 packages。配置 SHA256 `3ef567b7e20a136a1a640037b3d207654516ca02e78dc8868f4dfe8fdb9b3fc1`；profile artifact SHA256 `448c1a68422b2e9b7dd0e1c79ae27d65bf056035971560e8473239ba2a3861ae`。真实 prepare 后再次 verify 通过。
- 真实 xPack GCC 镜像：冷镜像 14928 bytes，ILM 14320 bytes，DLM data 16／BSS 64 bytes，保留栈 16 KiB、堆为零。当前可达入口的保守调用链栈上界为 544 bytes；未接入的导出服务另列，不代表未来业务栈已验证。RV32 模型按实际镜像执行 205021 条指令，完成复制／清零／屏障／ILM 自检并抵达 `services_main`；它不替代加密硬核仿真或板测。
- ELF SHA256 `6908a9821db2df861d737173ef17ddf94c86aac34522d2a57c94ec70685314ad`，BIN `a4b64abd9dfab365ab9a0ea9263e3105f28d1a5005f8140a83279eb6d7644629`，ROM `6faa84042bc3695f7ae783168eeb937029f15cc706d80a98101752b2a4ebb68d`。
- 原 no-panel 也实际 prepare 并 verify：`custom138k-workstation-r00-no-local-panel-v1-b86cfbf730dd8493`，599 staged／269 enabled，ROM SHA256 仍为 C02 的 `1b2e8fac6677508c6f070baa6a4486b372ce79d0a40b9b81a1a8546c47f90766`。

父级启动附加收据移至 prepare 目录外，未改写候选原始元数据或其证据库存。机器记录为 [ae350_boot64_parent.json](workstation_task_20261030/ae350_boot64_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/c06-boot64-parent-v1` 封存 18 份源码和 2127 项外部输入／产物，`verify.py` 可只读复核；seal SHA256 `f33515abf97c40706ab4c6998ba22c2cfb5c197073fb5aae77c0b37838b394f4`，receipt `0133282ad89f9fdfff5de3008e2f776e0efce2571cb45fd25d01b3f28753aff0`。

## 后续与回退

I／D Cache 保持关闭，入口检测已开启则失败；没有假定 APB、显示共享页或 DMA 的 Cache 属性。实际 CSR／ILM 取指／DLM 访问、Cache 属性与维护、ECC、周期／栈水位，以及同功能资源／物理时序与硬件验收继续独立完成。新增 48 KiB ROM 是逻辑存储差额，不能换算成已取得的物理 BSRAM 成本或 CLS 收益。64 KiB 是此显式配置的容量，不是对后续固件扩容的限制。

本阶段无综合、P&R、板卡操作、SRAM 或 Flash。回退可选择原 no-panel profile；如需撤销实现，以 `febf274` 恢复本阶段源码／配置并以新身份重建，保留既有候选与证据。C06／C04 等整项任务不提前勾选。
