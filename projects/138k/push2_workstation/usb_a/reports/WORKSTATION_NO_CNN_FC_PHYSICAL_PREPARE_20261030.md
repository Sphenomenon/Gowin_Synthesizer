# no-CNN FC：同网表 placement 对照准备（2026-10-30）

FA 已完成[真实路由失败](WORKSTATION_NO_CNN_FA_RESOURCE_FAILURE_20261030.md)。下一独立试验 `C11030FC` 保持同一 `custom138k-workstation-no-cnn-v1-525ffff10d622031`，完整 Tcl 仅改变 UserCode FA→FC、place2→place1，route0／replicate=false 不变。其余时钟、hold 修正、VG、301行 SDC 和 CST 均保留原字节，以单项 placement 对照继续定位路由压力；没有再删除功能或放宽门禁。

父级 verifier 与独立审查均通过：FA 的18项来源输入、失败process、日志／全部输出，以及 FC 的23项登记输入逐项重hash。独立14个负控拒绝算法／UserCode漂移、重hash后的网表／约束篡改、新增时序放宽、丢失或新增输入、伪造接受状态和重绑综合来源。父级重新核验独立seal五文件及全部负控。FC manifest SHA256 为 `02c89d15b5b9142026a986b6f55f89307dc32020e34a5a7a0f18ce30262d88cf`，独立seal为 `a2164ac87a6943420914eda99cdfa24318790b7be2234e8796ebdec0fc65da62`。

| 未变物理输入 | SHA256 |
|---|---|
| VG | `37c811ffcc0a0ae2ce55aa66550c95bec8bb04cc7fc92aa69c1cc7c17d6f3f4f` |
| SDC | `ead347d58729b7ac917ca6b27a0c0d65c598ac4cd8f8dcd7fa1cd127c19c4036` |
| CST | `8c3f8415936623883006f02b6c70ad464f323337d9ed486583fee4349cbead3e` |

新 dated preparer 从 FA seal 重新构建精确输入；旧 preparer、原 Tcl、原 prepare结果及原 process 作为来源证据另名保存。主线 PCM 工具锁已经变化，故没有重跑或绕过旧 preparer 的 current-root 等价guard，也不重新断言 FA 的历史 root 等价仍成立。当前 maintained implementation helper 仍与 FA 副本逐字一致，Tcl由其已有函数生成；新增脚本只用于这次 cache 实验，不成为长期生产 builder。`C11030FB` 已用于 prepare-only 正例，未复用。

目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-physical-C11030FC`，父级已用原锁定离线 runner 启动 P&R。准备证据及启动身份见[机器记录](workstation_task_20261030/conditional_no_cnn_fc_prepare.json)；本报告不预写物理结果。全部 CDC／reset／RAM数据弧／PLL、两模式 routed timing、功能／电气与硬件门禁仍未接受；即使后续生成位流也不能据本 manifest 部署。无板卡、SRAM或Flash操作。
