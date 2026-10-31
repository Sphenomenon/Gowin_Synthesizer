# W-DEMO PCM 命令许可的组合分解

2026-11-01。W10 `D2103116` 实际路径从 PCM owner 的 `staged_stream[10]` 到 `written[2][77]`，18级、data18.458 ns、setup−5.502 ns。流代次大小比较之后还经过公共 command error、response error、命令解码，再控制512位写入位图清理；不能通过放宽音频时钟解决。

维护源 `workstation_ae350_pcm_owner.sv` 将 START／COMMIT／SELECT／STOP／CANCEL 的校验并行表达，具体操作直接使用自己的许可。原响应／错误输出复用相同谓词，暂存寄存器写入有独立资格；命令ID只对实际接受的控制更新。队列、存储、SRC、采样节拍、应用ID和状态优先级保持，末尾撤销仍覆盖同沿命令，没有增加流水周期或权威状态。

独立复核发现第一版直接使用 `full_write && !(&command_id)` 会改变旧过程式 `if` 对未知 strobes／ID 的处理。最终使用两个局部过程式格式／ID资格位，保留原四态行为；旧差异复现和失败尝试保留。最终源 SHA256 `a28f84ee8ba95e8aa0a3ea7faf764f9c5cbcaf40dc25e13f17f01871ce5645ae`。

完整旧 owner 对照7,811周期，比较61公共输出／状态组、512个PCM RAM字、4组位图／帧计数，含6,000条随机命令和同沿撤销；7,369次直接许可检查一致。五操作及暂存许可的57bit完整二态模型均UNSAT，4个实际源码破坏负控拒绝；576组未知 strobes／ID组合与原四态一致。独立复核另以真实边沿比较3组未知值复现，以及 STOP／CANCEL 分别同时遇到 TF、会话、context、switch和CPU失效的10组撤销，均与旧实现一致。

最终源通过原8项 owner 回归，包括48k／44.1k、±2000ppm各576,000输出帧、双声道次序、队列背压、描述符、序号、重置和历史屏障。原描述符11万组向量／16,384组缺帧组合及4负控、2项PCM边界检查通过。正式 D APB／CDC→owner→完整效果→I2S双率／PANIC仿真通过1,918个物理模型帧、1,917个显示快照、12次PANIC；使用理想时钟和有序DDR模型，未验证真实手机或板卡。

[机器证据](dual138k_pcm_control_admission_20261101.json) SHA256 `eb5e89cbe71bb3528fe256ce8cc9fbe097b12b9665df9a17a06080ee45729e15`，绑定实际触发路径、最终源码、可复现测试和独立审查。运行新许可证明需已安装 Z3 的解释器，例如本机 `/Users/sphenicidition/miniforge3/bin/python3`。新源的综合／物理收益尚未测量，冻结 W10 输入保持；后续 prepare 必须核实维护源确被消费。未下载 SRAM、未写 Flash，不提升整机或硬件验收。
