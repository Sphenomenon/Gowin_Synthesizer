# accepted DDR 锁定来源边界修复（2026-10-30）

维护地址图增加 R00 分区后，旧 accepted builder 将活动 map 的变化误当作历史输入漂移，导致 clean prepare 失败。本阶段将 accepted full83／timing85 的 map 选择明确绑定到锁定基线，并在最终 stage 及 EDA 返回后再次校验历史哈希；活动 map 只作观察记录。其余四项活动 DDR 输入的漂移检查保持，所有五项锁定 DDR 输入仍需通过身份校验，不允许缺失、损坏或重新绑定后回退到活动文件。

父级核验隔离交付的六份封存文件后导入四文件补丁，完成来源测试 **17项**、USB 固件 **7项**、基线 **23项**，均无跳过。基线测试启用 `GW138K_VERIFY_CLEAN_PREPARE=1`，验证 accepted／timing85／resource 三条路径在无私有历史 staging 的干净 clone 中与当前工作区逐文件一致，同时通过 trace CDC、生命周期及锁定源损坏拒绝。三条路径的 staged map 均为 `0ec949e54acecac04b71fceca2cf725d56d2691c850fbd83951fdc6441fc8ddb`；活动 map 保持 `1b7ed38191bf6c14e5de65f9f68e78d1f6f43b1ac0ea0163140be10256eb289a`。

三份 custom profile 只刷新 `workstation_sources.py` 的来源锁，配置保持。父级 fresh prepare 与来源检查各 **12项**通过：R00 为 `aced56fa321871ee`，保留识别为 `39ffc0d7eb50dd7d`，no-CNN 为 `c302fcc98ab76b03`。各自 583／570／571 项 staged 输入与前序 prepare 逐字节相同。这里的新身份不继承正在综合的 R00 `4b1436d83219e765` 或旧 FC 的物理结果。

冻结基线、vendor、原始清单和历史失败证据均未改动。本阶段仅验证来源与准备，没有新增综合、P&R 或板卡操作；完整 CDC、复位、STA 与硬件接受仍未完成。详细哈希、命令及父级记录见[机器证据](workstation_task_20261030/accepted_ddr_boundary_parent_validation.json)。
