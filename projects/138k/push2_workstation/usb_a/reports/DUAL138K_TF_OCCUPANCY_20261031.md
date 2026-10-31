# M：TF DMA占用计数的同拍等价修复

2026-10-31。M8实际DDR同域最差同步路径为`read_total_bytes`经32位减法、读请求／零延迟response资格，再到读总数与256位读缓冲使能，最差−1.667 ns。修改实际消费的维护`rtl/tf_audio/workstation_tf_runtime_dma.sv`，不改冻结TF来源或默认／legacy模块。

`available_bytes`与`accepted_used`由每拍计算两个32位总数之差，改为与原总数在同一边沿提交的占用寄存器，始终保持模32位的`write_total-read_total`和`capture_count-read_total`。写接受、读响应和输入接受的差值仅在7位内计算，符号扩展后各用一个32位加法更新。reset／restart／新文件归零；hold及S_DONE保持；同拍写接受＋读响应、零延迟返回、最后部分拍及原4GiB上限错误保持。不增加DDR请求或PCM输出延迟，不改FIFO、地址映射、采样调度或取消握手。

[逐拍与独立字节证据](dual138k_tf_occupancy_20261031/equivalence.json)：缩放64字节bank和真实64MiB bank两配置各400,007次公共输出／原有内部状态比较。每配置覆盖34次同拍提交和响应、772次部分返回、24,848次hold、405次restart及1,087次零延迟接受；显式一致状态种子核对32位上限溢出，不冒充实传4GiB。遗漏输入增量、错误零扩展负delta、同拍漏写入三个真实RTL负控均在占用不变量处拒绝。

原独立byte／ring oracle的无停顿／native stall与立即／延迟response四组合全部通过，检查空／7字节／整拍／跨bank／满环／两轮回绕／重启／地址及实际输出逐字节正确。这里是128字节缩放环模拟，不宣称实际传输了128MiB。

[完整TF runtime／clear证据](dual138k_tf_occupancy_20261031/runtime_clear.json)：direct／真实command buffer ×公共／独立复位四配置各23场景、677个最终输出；实际WAV、暂停／停止、旧read排空、取消、切率、格式失败及scope语义通过。默认模块与冻结来源12,531次逐拍对照一致。两种buffer配置各6个停钟token-clear场景通过，源停高／低电平及首新指针检查保持；立即ACK负控拒绝。输入hash末尾及提交前复核一致。v2扩展runner首轮因负控先触发公共输出检查而未命中预期文本，重排不变量优先检查后v3精确拒绝，没有修改生产逻辑或减少覆盖。

源码与离线阶段通过；资源、完整新综合、P&R时序／CDC／PLL及实板声画留待新候选。没有预记收益，没有SRAM或Flash部署。M8旧候选及其失败结果不变。
