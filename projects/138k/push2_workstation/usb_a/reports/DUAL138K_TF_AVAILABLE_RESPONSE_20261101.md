# TF available 响应计算维护阶段

维护 DMA 已将 available_after_read／available_after_write_read 的 delayed／full／partial 算术提前分支计算，最终占用选择与采样周期保持。已知 partial 分支仅在原完整比较及对应 known 条件成立时直接取结果；未知控制与 pending 继续使用原 helper。read_pending_bytes 与 pending_bytes 是独立 6-bit 输入，不假设它们等于 32 或等于 available。accepted-used cofactor、所有 NBA 目标／RHS／顺序与之后源码逐字节保持。

实际维护源 SHA256 `1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7`，版本化完整变更前 fixture 为 `3f9eb8afa2c3308d270ce215693723bfb7cb48584ee96c3c3fbe749a4902e7b6`。新 runner 精确逆 hunk 恢复完整 fixture，旧 response runner 再保留原 3f9→5ac 全文件门；原 oracle 函数及六个 mutations 保持字节，只在原唯一锚点构造 mutant 后恢复新 hunk，对完整实际模块仿真。

[机器报告](dual138k_tf_available_response_20261101.json)记录三项 48-free-bit UNSAT（任意 32-bit occupancy、两个独立 6-bit 数值，无可达性假设）、2,097,152 四态向量及三项实际源码负控。原 response 7 runs／6 负控、occupancy 14／8、threshold 8／6 全通过；真实 TF service／clear／stop 回归与来源 17 项通过，均绑定 1baa 实际源。主线程独立重读验证 309 项产物与四个维护文件；seal SHA256 `5ef531cd99843271ec5e664f67d636542183613bfa9a4c25e0d7e1bb12676dbd`，位于缓存 `tf-available-response-maintained-review-v1/seal.json`。

本阶段是维护源码及离线功能验证；四态仿真有界、代数证明不等同完整 SV 形式化或全网表等价。新增并行算术可能增加面积及末级 mux 负担，不预记资源或时序收益。M16／W14冻结输入保持；新 M17／W15 已另立来源身份准备并启动全量综合，实际资源／routed时序另记。本阶段无 SRAM／Flash 操作或实板声画接受。
