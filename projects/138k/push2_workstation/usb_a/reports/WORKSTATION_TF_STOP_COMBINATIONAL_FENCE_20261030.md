# TF 停止事务组合反馈修复（2026-10-30）

真实 runtime＋TF 联合 Verilator 编译发现原停止 owner 的组合环。本阶段仅修复该 owner 的作废准入判断，保留停止完成的全部证据；旧阶段报告和验收范围不修改。

身份：`native-tf-runtime-stop-v2-c4e9c27529528dfd`。完整输入集 SHA-256：`c4e9c27529528dfd5915669074ceeaff808315a1c8a3a3e3048722e35c08f2e6`。机器证据见 [tf_stop_combinational_fence.json](workstation_task_20261030/tf_stop_combinational_fence.json)。

## 发现和固定来源

原 `workstation_tf_runtime_service.sv` SHA-256 为 `955295b2b7d2c5c0ace0f63194e85606e866ee773fb983432de531933b991332`。联合编译日志 SHA-256 为 `9e4428fde6933d3caa2fb8b365a018710583e90200fe97efb989330c69bd0691`；保存副本位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/tf-stop-structural-loop`。Verilator 5.052 的实际路径是：

```text
invalidate → source_quiesce → source_quiet → stop_cleanup_complete
           → stop_invalidate → invalidate
```

旧判断 `stop_begin && !(stop_latched && stop_cleanup_complete)` 把停止完成反馈到当前作废。`source_quiet` 有意在作废当拍为假，因此不能通过删除帧桥的作废屏障来消除环。旧 Icarus 功能仿真曾通过，其结果不能证明组合结构无环；固定旧源的独立 Verilator lint 也准确重现1条 `UNOPTFLAT`。

## 最小修改和不变量

改为 `stop_begin && !stop_latched`。第一次 stop 建立新 generation fence；停止锁存后，mode、run、track 和 reader restart 均不能恢复媒体，只有可接受的显式 restart 清除锁存，且同沿 stop 优先。因此重复 stop 复用既有 fence，不需要依赖当前组合完成来决定是否再次作废。

停止完成条件保持原样：`state==IDLE && !busy_50_o && source_quiet && path_clear_done && memory_open_sync[1] && !control_pending_o`。已接受 DDR read 必须返回；四个 FIFO 本地端和 DMA clear 必须各自 ACK；最后 inactive／busy=0 mailbox 必须得到目的域 ACK。超时后继续清理，同一失败事务不补发 done。

两处 `EXTERNAL_STOP_PROTOCOL` 整数布尔表达式显式写为 `!=0`，保留任意非零启用语义并关闭 owner 的两条宽度警告。

产品新 SHA-256：`debe8ca8c0515ea0ef5b1c7c45c9835373a4720731df0cef97f11daddb467612`。未修改路径、DMA、FIFO、帧桥、顶层、构建 profile、vendor 或冻结对象。

## 离线验证

运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_runtime_stop.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/tf-stop-structural-loop/final
```

- direct DDR 命令连接和真实单入口 command buffer 各11场景，通过12次 done、4次失败、3次 pending 合并；每路有6次幂等边沿检查，包括前次 done 后首个可接受源边沿立即重复 stop，generation／clear token 不改变。这里的 direct 仍经过 DDR，不是 M03 的无 DDR 流式播放。
- 保留原 runtime service 每路22场景、clear 每路6场景、默认路径128帧／12,531周期对照和 stop 默认0忽略行为；末次 mailbox 停钟等待、旧读返回、memory 停高／停低及超时恢复仍通过。
- 两路 Verilator lint 均0条 `UNOPTFLAT`、0条 TF service warning。每路11条 `WIDTHEXPAND`、18条 `WIDTHTRUNC` 来自原支持源及测试夹具，机器证据保留计数和日志哈希，不将它们视为整机 lint 清零。
- 负控恢复原 stop 组合依赖，精确重现1条 `UNOPTFLAT`，检查拒绝该副本；移除末次 mailbox ACK 的独立负控仍在停止提前完成处失败。
- `test_current_workstation_sources.py` 10项通过；`git diff --check` 通过。runner 前后输入哈希一致。

## 范围与交付

本阶段是源码实现、局部结构检查和离线功能验证。完整 clock＋TF＋BLE 编排的联合复验由其独立阶段记录；本阶段未综合、P&R、验证路由 CDC、操作 JTAG 或生成／下载位流，未写 SRAM／Flash。SD 在本地测试中是字节边界夹具，DDR 模型为有序单 outstanding read；不推导实际卡或物理板验收。

后续原生 profile 必须锁定新服务哈希并重新综合、时序／CDC／PLL 检查和板测。回退为恢复本阶段三份维护输入的前一提交，但旧组合环也随之恢复，因此该回退仅供重现和定位。M03 读流审计的初稿保留在 cache，尚未实施，也不计任务完成。

## 父级独立复验

父级在新目录重跑完整stop runner，direct／buffer各11类、12done／4failed及全部原service／clear／default回归通过；两路结构检查无组合环，恢复旧环及绕过最后ACK的两个负控都被拒绝。仅规范化生成fixture的输出目录后，所有输入hash、逐项指标与冻结子阶段相同。原始独立结果见 [tf_stop_combinational_fence_parent.json](workstation_task_20261030/tf_stop_combinational_fence_parent.json)，SHA-256 `51c1228b3371677faf808ac86fd0a368ca2c0c53d89575b30743995884c19d1c`。
