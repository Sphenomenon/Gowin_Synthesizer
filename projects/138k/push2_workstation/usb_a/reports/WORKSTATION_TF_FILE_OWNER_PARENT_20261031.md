# TF 文件 owner 父级复验（2026-10-31）

未选择的 `workstation_tf_file_reader` 已由独立提交 `f317bf1f…` 合入主线 `1972fde`。本阶段仅增加八份源码、合同、测试和报告，已有 reader、sector/session、vendor、baseline 及四 profile 未变。owner 只负责卡／卷发现、有限 playlist、文件字节与实际取消／错误终态，不持有解码、PCM、采样时钟或 DDR 客户端。

父级审阅实际状态机与接口合同，重新运行封存来源上的全部 56 组 SPI/FAT 场景、八个行为故障负控及 21 项原生 sector 回归，逐项比较参数、输入、返回码和完整指标，全部符合原结果。八个主线新增文件逐字等于导入 Git blob 并存入父级快照；当前主线 accepted 来源 17 项通过，正／反精确 GPL 派生和全部原交付哈希复核通过。父级 seal 覆盖 13 本地文件／555 外部输入，完整身份见[机器记录](workstation_task_20261030/tf_file_owner_parent.json)。

真实 wire fixture 覆盖 FAT16/FAT32、superfloppy／第一 MBR 分区、碎片链、最终短 sector、目录边界、换曲、latest-request、stop／迟到数据、复位、坏几何／链及传输／初始化超时。`track_applied` 只在旧 payload／CRC 排空后产生，下一拍之后才可接受新的 512-byte reservation；EOF 需逻辑长度和最终 FAT EOC 同时成立。过长／循环尾链、早 EOC 和错误均不产生成功 EOF。源测试以实际 SPI 命令／边沿和文件字节 oracle 验证，没有 force 内部寄存器。

已知限制保留：CRC 只排空未校验；无物理卡检测／CID，快速换卡需要显式复位；严格支持的文件链必须在声明长度所需最后 cluster 结束。尚未组合 PCM ingress、选入 profile 或证明即时播放零 DDR；FAT cache、持续供给预算、物理 I2S EOF、综合／P&R 与硬件均未验证。M03 和整机任务不勾选，没有板卡操作、SRAM 或 Flash 部署。下一阶段组合单一文件 owner 与流式 WAV/PCM；原已选择路径保留作回退。
