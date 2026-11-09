# v123：W DMA消费者证明恢复，物理目标仍未完成

W新候选`custom138k-workstation-task3-w-preboard-v1-e2685055848dda14`完整综合审计通过30/30，独立prepare的743个暂存文件、203个编译输入及顺序完全一致，已重新计算实际文件哈希。配置和证据索引见[JSON](DUAL138K_TASK3_PREBOARD_V123_20261109.json)。本阶段没有新P&R或位流，不能沿用旧W位流代表新源码；M/W仍未放行，不操作板卡。

DDR故障同时门控DMA ready与response。初次仅对ready预计算的结构在局部较短，完整综合却仍经response绕回，实际最长7级，因此没有进入P&R。新版本化原生DMA预计算ready/response四种状态后继，在原边沿选择，保留未知值的原procedural投影，不增加寄存器、周期或改变flush／故障边沿。局部实际Gowin映射的838个寄存器next-Q／INIT／clock与430个公开输出位全部等价，五个timeout参数及X/Z回归通过，错误RD_REQ后继被拒绝。完整W网表的ready到state D均为3级；这是组合拓扑证据，尚无布线时序改善结论。

完整W另外证明全部803个DMA寄存器的reset-inclusive next-Q、INIT和clock，与已审计父映射一致。展开全部组合逻辑，没有内部LUT cuts；named-state和精确DDR/FIFO输出对应是明确假设，不宣称整机归纳。改错state D和clock两个破坏反例均被拒绝。故障闭包先执行此证明，再核对662个实际FF端点及4个RAM CEA；不再沿用已消失的state0 CE。TX类别审计先证明数字别名确实等价，失配时只接受真实消费者中唯一且完整SAT等价的函数，保留别名拒绝记录。

W完整综合为46949 Register、58286 LUT、15925 ALU、253综合BSRAM等效、779 SSRAM。v123仅增加或修订非编译审计材料，与v121的全部编译输入、顺序、固件、脚本和工程字节一致，使用有哈希收据的综合复用。物理配方按实际v121网表重建786个native目标和2224个delay/FIFO逻辑目标，排除原8个硬RAM；保留原区域、时钟和SDC。剩余录音ingress→真实录音结果、tag→raw completion/fetch及endpoint TX路径仍须处理，不能仅凭DMA局部证明重复P&R。

M溢出计数局部实验在11291个完整owner周期、61个状态／输出、512个PCM字和4个位图槽对照中通过，包括6000随机命令、4096项X/Z场景及同拍撤销。实际映射的32个overflow next-Q／INIT／clock证明通过，错误计数更新被拒绝；1413个FF不变，staged_frames到overflow的11级路径消失。该实验尚未选入整机。另两种位图归约在实际映射中使response路径从11级变为21／13级，均不选入，不进入整机或P&R。

17项当前来源回归通过。M v39物理审计的reset消费者参数漏传已修复，进一步检查停在真实DDR配置路径失败；不能继续称为未知reset清单漂移。旧[v118](DUAL138K_TASK3_PREBOARD_V118_20261109.md)候选、位流与失败证据不改。M v39 `D21109E7`、W v38 `D21109E6`仍禁止加载；[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)保持待放行状态。task2、单板、历史回退和冻结输入全部保留。
