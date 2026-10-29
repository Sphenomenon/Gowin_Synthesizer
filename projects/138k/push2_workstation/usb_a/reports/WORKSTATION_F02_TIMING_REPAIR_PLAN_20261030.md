# F02 audio／USB／readiness后续修复依据（2026-10-30）

本轮只读分析F02原时序与routed VO／SDF，没有修改业务RTL、约束或启动EDA。[机器记录](workstation_task_20261030/f02_timing_repair_plan.json)绑定原证据hash，保存最差路径、分组、统计和修复边界。以下建议需要新的source／综合身份，**未包含在固定rev2网表的F03布局实验里**。

| 边界 | F02实际失败 | 所属模块与建议 |
| --- | --- | --- |
| Audio ADSR | 最差−0.823ns；13.783ns数据路径，20逻辑级；同源560条详细负路径 | `unified_oscillator_engine.sv`的包络读取／算术／饱和写回分级；runtime对应owner同样需要独立验证 |
| USB引导灯光 | 最差−0.341ns；20.927ns数据路径，27逻辑级；11条同源详细负路径 | `push2_lights.sv`消费完整显示snapshot，先寄存再做变化检测与颜色／缓存选择 |
| 模型就绪同步 | 0.306ns CLK→Q＋1.732ns route＝2.038ns，超过2ns | `basic_pitch_workstation_link.sv`保留两级receiver；在Flash约束owner显式收紧级间物理要求 |

## Audio

完整详细报告的setup Path5从`engine/envelope_update_attack_q24…/DO[3]`到`engine/envelope_level_q24[13]_23_s1/D`，周期13.021ns，数据cell6.041ns、route6.134ns、BSRAM tC2Q1.608ns。当前源码虽已将数组选择写成寄存步骤，mapper把相关读取折叠为BSRAM输出后，仍与ADSR算术及32voice写回选择串在一条路径上。应依据新映射后的实际寄存边界拆分，不能只改变量名。

建议在audio owner里明确形成读取、加减／比较、饱和选择／写回的流水步骤，并逐级携带voice index、state和valid。最后一级写回完成前不得声明包络更新空闲；sample snapshot必须读到完成后的状态，PANIC必须清空所有新valid，维持note-off等事件的原优先级。额外周期必须纳入32voice和两种采样率的每帧预算，不得暂停串行输出采样时序。验证应覆盖最后voice、临界饱和、零step、同周期事件、背靠背帧和取消尾部。

Audio共有781条详细负路径，560条来自上述BSRAM源，另有vector state→reverb BSRAM CEA最差−0.769ns、mode→sine next-address−0.795ns、releasing／online／allocated mask→vector CE等组。它们需要在相应oscillator／vector／effect owner局部寄存请求、预译码或降低控制扇出；ADSR修复不能代表整个audio域已经通过。781是详细报告行数，不能当成唯一负端点数。

## USB引导灯光

详细setup Path458从`u_guide/read_index_0_s1/Q`到`lights/value_1_s0/CE`。实际链条是notes异步读→guide_mask译码→lights变化判断／颜色／缓存与CE，cell9.911ns、route10.710ns、tC2Q0.306ns；其中lights内部实际穿过64个COUT节点。不能只按源代码中的一条比较语句估计延迟。

优先只在`push2_lights.sv`增加完整guide mode／mask显示快照，使notes／mask生成与LED决定分属不同周期；宽变化判断可分成小组再平衡合并或流水。显示可推迟少量周期，`push2_score_guide.sv`中target／played-note判定、score队列与cursor语义应保持原契约。快照变化时仍要清除旧灯并完整重扫；发送`valid=1 && ready=0`期间kind／index／value必须稳定。仿真需要覆盖背压中切换mode／连续目标更新／clear／复位，确认不会遗漏最终灯光状态，也不会进入音频或命令应用通路。

## 模型就绪同步

原VO已经满足两个DFFCE、INIT0、共50MHz、常开CE、共CLEAR、直接Q→D和第一级唯一功能扇出。原RTL有`ASYNC_REG`标记，但F02 SDC只有到`model_memory_meta*/D`的第一级异步例外，没有`meta.Q→ready.D`的专门max-delay。路由门禁的2ns检查直到实现后才拒绝2.038ns。

后续独立source候选可在`tools/workstation_custom_flash.py`约束owner增加精确两级间2.000ns max-delay，并保留原第一级D例外；需要时用checked近邻物理区域帮助placer。目标是让实现满足现有2ns界限，保持两个receiver及其单一扇出。不能放宽门禁、对第二级加false path、复制第一级作为功能源，或用增加同步级掩盖原级间飞行时间。新的完整P&R仍要实测CLK→Q＋route≤2ns并重新执行CDC、STA、PLL及资源门禁。

上述所有修改均属于下一source身份。接受输入边界发生变化时，需要`sim/test_current_workstation_sources.py`及对应子系统回归；prepare、综合、P&R与硬件接受分别记录。F03仅解决原wloadn capture布局实验，仍必须独立处理DDR DQS HOLD setup−1.867ns等其他负路径。
