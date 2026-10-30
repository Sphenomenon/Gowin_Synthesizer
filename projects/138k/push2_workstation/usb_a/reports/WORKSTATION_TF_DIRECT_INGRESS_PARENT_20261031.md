# TF 流式 WAV/PCM 入口父级复验（2026-10-31）

未选择的 direct-ingress 源码由独立提交 `195050ea…` 合入主线 `0855a0d`，仅新增十个文件。已有 WAV kernel、四 profile、时钟、SDC、vendor 和 baseline 均保留。新组件在同一 50 MHz 域接收已保留空间的 sector 字节，使用 4 KiB byte FIFO、4096 个带 last 的 PCM frame 和一帧 lookbehind，输出 held-ready stereo PCM16；generation／rate 只是外部已提交状态的会话快照。组件没有 SD 控制器或 DDR 端口，采样调度不等待文件输入。

父级在实际主线源码重跑 42 个场景、11 个行为负控和三项旧 WAV 回归，完整 JSON 仅归一化独立 clone→主线的 checkout 前缀后与封存结果逐项相等；共 35,649 次 PCM transfer、154 checks、763 sector、50,682 deadline，源 lint 零警告。主线来源 17 项通过，十个新增文件逐字等于导入 Git blob 并另存快照。两份派生 patch 的正／反向重建、旧 kernel／profile 不变、各交付的输入与工具哈希也已复核。父级最终 v2 seal 为 `2e37b9fa…`，17 本地文件／647 输入，见[机器记录](workstation_task_20261030/tf_direct_ingress_parent.json)。

两名独立审查者分别给出七项边界重放，以及完整 42／11／3 重放和另外三项会话 pin 扰动。审查实际复现了旧版 `chunk_size=0xffffffff` 的奇数 padding 加法回卷后错误接受；新 parser 使用 34-bit chunk-end 与 RIFF 容器界限比较，针对性负控移除界限检查即被测试拒绝。双率、mono/stereo、8/16/24/32-bit、预填／暂停／背压、取消／回绕、真实耗尽、短／空／截断文件和终态失败均覆盖。正常本地 tail 转交之后不会再次误报 underrun。

父级初次只读验证因当前终端 Miniforge Python 与封存 `/usr/bin/python3` 身份不同而拒绝；逐项比较仅此工具路径变化。保留原失败日志，按显式 PATH／系统 Python 重验通过，没有改 seal。初版父 seal 没有直接枚举作者的 `relative_sha256` 键，完整依赖已由独立 receipt 间接覆盖；v2 明确逐项重哈该键，647 项依赖集合相同，v1 原样保留。

本阶段不选择 profile，尚未把真实 file owner、浅 CDC bridge 和物理 I2S 串起来。`decoded_eos`、`local_tail_drained` 都不代表物理最后帧完成；未证明整机 owner4 零 DDR trace、健康卡 50 ms 服务预算、所有 WAV header 字段校验、资源映射、routed STA 或硬件接受。M03 保持未完成，没有 SRAM／Flash／板卡操作。下一阶段验证单一 SPI/FAT owner→本入口的真实组合，保留现有已选择 TF 路径作为回退。
