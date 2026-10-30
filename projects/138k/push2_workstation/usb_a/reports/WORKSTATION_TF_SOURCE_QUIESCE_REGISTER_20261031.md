# TF source quiesce 注册发布：父级源码复验

维护 `workstation_tf_runtime_service.sv` 现在用 50 MHz 保持寄存器发布 compute 同步器的 quiesce 输入，common reset 时置 1。跨域控制不再直接来自 state／epoch／错误的组合译码。`invalidate`、generation、PCM 准入和 native source hold 仍在原事件边沿执行；源时钟在最后边沿后停高或停低时，取消继续可见。退出静止状态后 quiesce 保守多保持一个 20 ns 源周期，实际 quiet／control ACK 仍必须等待。

源交付 commit `43ef616d4474f2e52b6e75d1725d6f12bb5536b4`，service SHA256 `196b57cd9f7a1647e856e5f03a7f1bc941e8ae47a55ee21dcec42ca85ece5395`。父级检查代码和完整差异，导入九项精确 Git blob：owner、契约、四份显式 profile 的两个 owning SHA、定向 runner／TB 和旧 TB 的默认不变 timeout 参数。四份 profile 除 service／契约身份外完全相同。未修改锁定 baseline、vendor、旧帧桥、SDC、时钟或固定 222fb761／C2103102。

父级完整重放通过，与交付的全部场景 metrics 相同：direct 与 command-buffer 两种路径、48k／44.1k、八类事件和源时钟停高／低共 64 场景，另有四次源边沿间 epoch 扰动，恢复后共检查 4,300 帧真实 PCM。事件覆盖 cancel、epoch／rate 变化、换曲、stop、transport error、runtime invalid，以及 cancel／restart／stop／error 同拍。测试等待真实 DDR／清流／generation 和 quiet 回程，检查没有早放行、旧帧或虚构完成。

六个实际 RTL mutation 均被拒绝：旧组合发布、取消 invalidate 延后、publisher 漏事件、reset seed 错误、跨域原组合旁路、native hold 漏事件。原 STOP／CLEAR／近回绕帧桥回归已由交付完成并封存，父级逐项验证其输入／结果字节。主线八项 profile 来源检查和 17 项 accepted 来源检查通过。主线首次 profile 检查被尚未提交的 C02 renderer 身份变化正确拒绝；父级仅暂时排除这两份未完成 renderer 改动再测 TF 来源，随后恢复它们，失败日志保留。C02 来源更新另立提交。

交付 seal `b977661279aa28d0291846cc85ee268e9741a45006e89a8af55b0fe949c501c4`，262 本地／41 外部输入已重验。父级 seal `7c1c5f508ce76654f096b141b9f9053ecbdd8dfb460e55e254843c85872d1ed3`，11 本地／360 外部输入，保存九份源码快照和完整父级重放。机器摘要见 [tf_source_quiesce_parent.json](workstation_task_20261030/tf_source_quiesce_parent.json)；本机证据为 cache `tf-source-quiesce-parent-v1`。

这是源码和理想数字协议阶段，没有新 prepare、综合或 P&R。注册 publisher 的实际 Q→first D、时序／MTBF、新网表 CDC／reset 及完整硬件门禁仍未接受；旧 222 scope 不替换 hash、不转授接受，也未新增时序 cut。没有板卡、SRAM 或 Flash 操作。若回退，以新候选恢复前一 owner／契约及四份 owning SHA；历史固定候选和证据保持不变。
