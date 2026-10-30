# 条件 no-CNN：实际整机综合（2026-10-30）

[主线明确选入](WORKSTATION_CONDITIONAL_NO_CNN_SOURCE_20261030.md)的 `custom138k-workstation-no-cnn-v1-525ffff10d622031` 已完成整机综合，退出码0，耗时335.536秒。571项登记输入保持；父级再次重新hash全部输入、四项综合输出及日志。没有AG组合环诊断，其余警告原样保留。[机器证据](workstation_task_20261030/conditional_no_cnn_synthesis.json)绑定全部输入、工具和结果身份。

| 身份 | SHA256 |
|---|---|
| candidate input | `525ffff10d6220314f4c61b29536f7fcc0b2ecdd1d4710ea94ecd4b84e02d957` |
| configuration | `8907b17a341351e5284f067e728c6eafa0c00ebe0f604a5b21f0fb93bce0dad4` |
| synthesis process | `f209022bfe86cde0b760e345bde0e405a514025cf98c6de91dd9bd33044cb7ec` |
| actual VG | `37c811ffcc0a0ae2ce55aa66550c95bec8bb04cc7fc92aa69c1cc7c17d6f3f4f` |

| 综合估算 | 注册控制 enabled 候选 `1aea3c01fa6c1b14` | no-CNN `525ffff10d622031` | 差值 |
|---|---:|---:|---:|
| Logic | 121,604 | 102,128 | −19,476 |
| Register | 61,346 | 51,122 | −10,224 |
| BSRAM | 268 | 245 | −23 |

no-CNN Logic构成为79,170 LUT、15,122 ALU、1,306 RAM16；七个可见PLL和一处DCS仍在。表中只是综合估算对比，两个候选的输入和配置分别锁定；没有把综合BSRAM差值当成物理净收益，也没有声称释放了PRIMARY／LW资源或提高时序余量。

独立实际网表预检确认CNN producer、song-command CDC、score-push FIFO及CNN guide／menu实例均不存在；手工score／REC、实时引擎、chorus／reverb、TF、USB、BLE、串行器和显示消费者仍有实际层级／资源。实例存在仅作来源与保全检查，不代替声音、显示、协议或完整功能验收。

301行SDC的501次静态查询中，17个空token／完整空query全部属于加密DDR IP的内部PHY层级；可见端点没有新增空查询。静态parser不能解析加密实现，也不能证明Gowin的实际对象语义。完整query／层级清单保存在机器证据绑定的cache文件，版本化摘要保留缺口和身份；独立P&R还须验证这些对象，没有用宽cut删除它们。

原件目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-synthesis-525ffff1`。新的时钟、Gray／媒体／USB与PCM审查分别在这份VG上进行；不能从enabled旧结果直接继承。物理资源、完整CDC／reset／PLL、双模式routed setup／hold及实板尚未完成。本阶段没有P&R结果、位流、SRAM或Flash部署，deployment_allowed=false。
