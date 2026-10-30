# 媒体结束结果组合（2026-10-30）

常开50 MHz的 `workstation_media_preparation` 并行请求runtime录音／score／TF owner与BLE录音owner，等双方本次真实终态后才返回组合结果。组合器自持hold，CPU observer撤销不能解除仍在运行的后台事务。失败保留runtime原因1..9或映射BLE原因10，准入竞态明确失败11；双端真正ready后才重新开放请求。注册request送达当沿的旧终态被忽略，不能回答新事务。默认 `ENABLE_BLE=0` 完全透传runtime接口。

契约见 [MEDIA_PREPARATION_CONTRACT.md](../rtl/services/MEDIA_PREPARATION_CONTRACT.md)。机器证据 [media_preparation.json](workstation_task_20261030/media_preparation.json)，SHA-256 `8c29cbea2cbbe94f07b9a974e6677731e3f07ac228a0e0a21712ab0df8441a3d`；主要回归身份 `native-media-preparation-v1-2b51c99d3f8ca337`。

父级回归9类、8次后端请求、5次成功、4次失败和193次默认透传检查通过，提前完成和重用旧终态两个临时负控均被语义断言拒绝。Verilator lint无warning。独立agent用注册后端接口模型追加100次事务，53成功、47失败、25次调用者撤销及1148次清理等待检查通过；另一独立BLE owner额外复核了单侧失败、CPU撤销、另一侧仍pending的组合。

所有输入前后哈希保持。验证仅覆盖协议组合和理想同域时序，后端为fixture；没有将真实TF、BLE、APB、DCS和物理帧串成同一enabled链。native top接线和下一profile由后续阶段验证。本阶段没有综合、P&R、位流、板测或部署，也不改变accepted/pinned来源。回退只需撤该独立source和显式启用，不涉及硬件写入。
