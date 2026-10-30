# TF 外部停止事务（2026-10-30）

新增默认关闭的 `EXTERNAL_STOP_PROTOCOL`，由新owner显式启用后提供50 MHz的 `stop_request_i`、`stop_pending_o`、`stop_done_o`、`stop_failed_o` 和四位 `stop_failure_code_o`。成功必须包含真实accepted-read drain、四FIFO与DMA清空ACK、frame bridge sourcequiet、memory gate-open返回，以及最终inactive／busy=0控制mailbox的ACK；busy下降本身不产生成功。已提交的[clear握手](WORKSTATION_TF_RUNTIME_CLEAR_HANDSHAKE_20261030.md)（`7daa75b`）及旧缺陷报告保持历史身份，不覆写。

## 政策与边界

stop优先于同沿restart，pending期间重复请求合并。接受stop后锁存停止，track只保留作下一次显式restart的当前选择；mode、run、reader restart、卡返回或transport变化不会重新播放或恢复分析。显式restart只在不pending时解除锁存，且从当前选择重新启动完整文件。释放上层媒体hold不是restart，TF也不请求／改变采样率。

stop watchdog覆盖整个事务，包括clear已经完成但最后控制mailbox未确认的时间。失败每事务至多一个单拍；清理尚未完成则pending继续保持，恢复后只撤pending，不为同一个失败事务补done。全证据已完成的停止对象可幂等接受新的stop并成功，不重新清空或改变generation。`stop_failure_code_o`独立记录本stop故障直到下次stop接受；最终mailbox单独超时可在普通文件`failed_o=0`时报告stop失败8，调用者必须使用专用结果端口。

失败码沿用1采样率、2格式、3DDR/readiness、4卡、5context、6epoch/rate、7transport、8清理／mailbox超时。实际physical context故障与stop同时发生时，stop失败一次。完成判断只使用50 MHz的同步返回证明；没有将compute域控制寄存器直接取回组合判断。

本阶段只修改TF service／契约与其测试fixture，并新增stop专用TB／runner；录音先封口、AE350命令入口和时钟事务由独立owner实施。没有修改native top、profile、锁定baseline、vendor、DDR分配或原18-bit事件布局。

## 固定输入及复验

| 本阶段维护输入 | SHA-256 |
|---|---|
| `rtl/tf_audio/workstation_tf_runtime_service.sv` | `955295b2b7d2c5c0ace0f63194e85606e866ee773fb983432de531933b991332` |
| `rtl/tf_audio/WORKSTATION_TF_RUNTIME_SERVICE_CONTRACT.md` | `6a4e3b4957d5b9e627776021f2abbb3723f262ff657b67f3543a2e6728911e20` |
| `sim/tf_audio/workstation_tf_runtime_service_tb.sv` | `9b47184e096d5d7cbc255ba186bb465649c6697740bb8cf4698d1b9fd566ca49` |
| `sim/tf_audio/tb_workstation_tf_runtime_stop.sv` | `56f65b4f73b4a2924d80e1bc3a37d37dcb24f8971da9739921c44dda196c8f00` |
| `sim/tf_audio/run_workstation_tf_runtime_stop.py` | `d612cd7ce5e28dd8a9d3555798035b7d25644907c90e48844bcbc7b8ae1ad27d` |

完整source集合、编译命令、log hash和保留的default/clear输入证明见[机器记录](workstation_task_20261030/tf_runtime_stop_policy.json)。最终身份 `native-tf-runtime-stop-v1-c278476aa692fe50`，完整集合SHA `c278476aa692fe50959ecac1608fe64d762baf61bc619d1d7dc3a52d129b6519`，运行前后输入seal相同。输出目录路径属于证据输入记录，父级独立复跑会产生自己的新身份。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_runtime_stop.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/tf-runtime-stop-v2
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
git diff --check
```

| 检查 | direct | 实际command buffer |
|---|---:|---:|
| 专用stop场景 | 10 | 10 |
| 成功脉冲／失败脉冲 | 10／4 | 10／4 |
| pending重复合并请求 | 3 | 3 |
| memory stopped-high／low | 1／1 | 1／1 |
| 最终mailbox held检查周期 | 40 | 40 |
| accepted-read drain等待检查周期 | 30 | 30 |
| 停止锁存保持检查 | 300 | 300 |
| 完整PCM／generation oracle交付 | 88 | 88 |

十个场景分别验证活动播放停止及track/run/mode/analysis不重臂、干净停止的重复幂等请求、explicit restart恢复及同沿stop优先、真实旧read未返回前不能clear、memory停钟后clear ACK等待与合并、memory超时／恢复不补done、compute提前停钟超时／恢复不补done、只缺最终mailbox ACK的短暂停钟／恢复、只缺最终mailbox ACK的独立超时／恢复不补done、同沿真实transport故障失败一次再显式恢复。最后mailbox超时场景额外断言state为IDLE、busy为0、普通文件failed为0而专用stop仍必须失败8，防止局部clear watchdog冒充总事务时限。

默认参数0时主动送stop请求，TF仍按完整64帧oracle播放且没有新增invalidate或任何stop输出。普通direct/buffer回归仍各22场景、677 PCM、128 analysis、6暂停零帧；clear专用回归仍各6场景、60 ACK变化、28次多位归零及capture/playback首RIFF各9次；default真实path逐拍对照128帧／12,531周期。

临时副本移除最终 `control_pending_o` ACK条件，在19,220 ns被 `stop done preceded final mailbox/clear/gate proof` 断言拒绝，维护输入未修改。clear ACK-bypass与combinational memory_quiet负向控制也继续被拒绝。所有正向编译／执行退出0，10项current-workstation来源检查和diff检查通过。编译无implicit declaration或新增功能警告；仅沿用timescale及默认reference未连接的关闭opt-in输入提示。

## 接受范围及回退

这些证据使用真实维护TF path／DMA／FIFO／WAV／85-bit frame bridge／控制mailbox和实际command buffer，但SD/FAT reader是byte-boundary fixture，DDR为有序single-outstanding模型。不证明实际卡/FAT延迟、独立memory reset或late/reordered响应、模拟毛刺／亚稳态、routed CDC、完整时序、AE350／录音／时钟联合政策或板上行为。TF仍经DDR中转，最终no-DDR流式迁移另行完成。本阶段没有综合、P&R、JTAG、SRAM或Flash动作；后续必须将新stop选择接入同一新候选并验证。

回退可撤销本stop阶段至`7daa75b`的clear契约；保留既有clear／缺陷审查与固定snapshot证据，新release输入不得复用旧接受身份。

## 父级独立复验

父级新目录 `tf-runtime-stop-parent-final` 完整重编译／运行 stop runner，direct／buffer 各10场景、默认关闭与最终ACK负向检查通过，前置普通／clear／default及其负向检查也通过。规范化临时生成文件的输出目录后，输入内容哈希逐项相等，stop／disabled指标和子代理一致；见 [独立复验证据](workstation_task_20261030/tf_runtime_stop_parent.json)。本次没有更改物理或整机联合验收状态。
