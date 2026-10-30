# 观察 FIFO：实际 RAM 与数字安全审查（2026-10-30）

本审查只绑定 `custom138k-workstation-v1-f1be50e853d3700a` 的封存 VG `8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535`。已通过实际存储映射、消费者资格和带假设的理想数字FIFO证明；RAM物理数据时序与完整CDC仍未通过。没有安装新约束，也没有把结果转移给后续注册控制或no-CNN网表。

实际观察FIFO是25个深度16的 `RAM16SDP4`，共100条物理数据位，98位有效、2位零填充。有效位逐一对应PCM32、error1、sequence32、epoch32、rate1；98个DI直接来自选中 `dac_mclk_d` 域的98个独立串行器寄存器。异步读地址来自compute域，写地址和WRE归选中串行时钟。有效数据的保守前向闭包包含696个输入pin端点、583个cell，覆盖29,036条位到端点关系，无未建模payload sink；端点包含D、CE及下游SDPB地址／数据／使能。

Z3解释实际LUT／INV／ALU／MUX及寄存器更新，178项反例查询均无解。WRE精确等于source release、物理帧valid和非full的合取；指针增量、Gray编码、两级同步与三拍release均核对。548个首级FF在无有效head时对任意RAM payload值不敏感，三组下游SDPB的九项资格检查通过。

另32个首级FF属于录音投机转发捕获，确实可以在head无效时更新，不能称为valid门控。其数据逐位等于当前PCM，`forward_valid`在无效head时不会置位，随后32个FF在forward_valid=0时不依赖投机数据。16个无关DSP输出按任意值量化；本审查不证明其DSP语义，也没有将未知payload消费者忽略。

独立深度16的ghost-ordinal模型通过14项归纳检查和544组有限Gray标志组合，证明未读项不被覆盖、有效head不与已接受写入碰撞、存储身份与次序保持。前提是远端指针观察相干、单调且不超前；这项假设仍需实际Gray时序／亚稳证据支持。只有协调common reset清空FIFO，epoch／rate是载荷标签，不单独flush。full时丢新观察帧并计数，不能反压音频；独立单边reset不在支持契约内。

交付的三相位RTL回归各记录51 accepted、21 dropped、50 checked、63默认深度检查、8次stream变更、2个序号缺口及7项饱和检查。父级核对其全部实际输入字节及结果，没有将这些数字仿真称为RAM器件时序或板测。

父级逐一复核原seal的25个文件，在独立副本重跑实际inventory／178项语义／19个网表破坏版本、14项安全证明及六个反例、vendor检查及四个反例，再生成约束提案并通过汇总验证。原交付目录未改，父级日志、结果、脚本及完整targets／inventory的路径和哈希见[机器证据](workstation_task_20261030/observation_ram_f1be_parent_review.json)。这些cache脚本是具日期的实验审查输入，尚未安装为生产门禁；版本化checker与新网表适配另行交付。

## 未安装的物理提案

三个时序边界必须分开证明：源寄存器Q到RAM DI／WAD／WRE保留正常同域setup和hold；写发布必须包含RAM内部CLK→DO以及之后全部路由／组合延迟；compute读指针Q经RAD→DO到消费者保留正常一周期setup和hold。从DO才开始的max delay遗漏内部RAM弧，不能证明写发布。宽异步或hold例外会遮住RAD同域问题，因此本审查没有提出这种例外。

在已证明的数字资格及相干指针假设下，新写入到首个合资格capture的最早下确界是两个76.8MHz周期，约26.041667ns；13.020ns完整write-flight只是一项保守提案，预算尚未接受。32个投机FF可以更早采到无效数据，其后合资格路径仍需物理settling／setup／hold证明。

Gowin功能模型确认异步RAD读取，timing模型有4条CLK→DO和16条RAD→DO弧，但其nominal specify值全为零，不能作为器件PVT证据。提案命令全部注释；Gowin对象解析、内部RAM弧、clock latency／uncertainty、全端点setup／hold、物理Gray相干、复位recovery／removal、投机数据亚稳隔离及硬件观察仍待完成。本阶段无EDA、JTAG、SRAM或Flash操作，deployment_allowed=false。
