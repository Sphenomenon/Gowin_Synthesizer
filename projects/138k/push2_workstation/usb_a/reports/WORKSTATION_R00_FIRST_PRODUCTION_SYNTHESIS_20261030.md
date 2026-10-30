# R00 首次生产接线整机综合（2026-10-30）

候选 `custom138k-workstation-r00-v1-4b1436d83219e765` 已完成真实整机综合，退出码0，耗时366.168秒。父级重核583项staged输入、四项runner输出、实现目录全部七文件、日志及两项工具身份；输入保持，无AG组合环或ERROR诊断。实际VG为 `882bf435ac70eb2acc44e3deccecd1e56c97c53fe1028c6b33a03c8adbd43e9b`，原过程与来源未改名或重绑定。

综合估算为 **Logic108,298、Register53,530、BSRAM246**（84,129 LUT、15,787 ALU、1,397 RAM16）。这些不是物理占用或净存储收益；BLE仍有原RAM录音后备，R00仍限16,384帧。新录音业务的存在和综合成功不代表BLE迁移、长录音或真实音频接受。

父级在这份实际VG上完成时钟4项／23负控，以及既有runtime CDC共27项中的25项／75负控；两个显式历史VG对照未选路径而跳过。CDC结果只覆盖既有400个Gray首级位与media／USB子集，不覆盖新增录音CDC或完整reset。原始诊断完整保留，包括两条无驱动（既有未选择的playback信号及vendor USB CPU信号）、宽度裁剪、优化及三条时钟关系警告，不能称全部诊断关闭。

本次综合输入属于先前 `524f533` 准备的固定候选，未选后续USB音频owner复位修复，也未选正在修复的音高／ADSR流水；后续阶段的新prepare不会继承这份网表。FC的setup／hold／recovery失败仍属于旧no-CNN身份，不能用其布通结果接受本候选。本阶段未P&R、无位流、未操作板卡；全部功能、完整CDC／reset／RAM数据弧／PLL及双率routed时序仍须验收。

[父级机器记录](workstation_task_20261030/r00_first_production_synthesis.json)包含原始过程、全部输入与输出哈希、资源行和具体范围。综合目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-parent-synthesis-4b1436d8`。
