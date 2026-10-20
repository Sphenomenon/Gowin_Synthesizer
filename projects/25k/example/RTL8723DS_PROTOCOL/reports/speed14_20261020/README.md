# 第十四轮：ACL额度时间轨迹与H5确认合并试验

本轮新增真实板卡的物理ACL发包/额度归还时间记录，测试100µs H5确认合并策略。候选未显示吞吐收益，未采用；源码、生成源码及SRAM恢复22B4，Flash及0.2.8 APK不变。持续提速目标仍在进行。

## 额度时间记录

SRAM诊断8AF4以50MHz计时，在ACL桥接器向H5交包、解析完成额度事件时，记录微秒时间、累计发送数、变更前额度、归还数量和动作标志。4096×64位同步RAM满后停止，不影响流控；下载后首次读取FFF1冻结记录，后续逐条读出，每条具有独立CRC16。此为FPGA/HCI边界时间，不能当作空口抓包。

两次32768字节下载逐字节匹配参考，速率9977/10114 B/s。分别读出2727/2731条记录，逐条独立重算额度守恒和累计物理发送数，高地址跨2048也验证通过；前者1364次ACL发送、后者1366次，包含连接建立和元数据。原始下载通知均独立重组验证逻辑CRC、对象身份、连续偏移及PCM CRC，均为5个DATA块。

为避开建立连接和结束采样，用累计发送数100至总数减30的内部区间分析：完成事件均逐包归还，按事件间隔超过2ms划分的归还批次周期中位均15000µs；归还前额度为0时，到下一次交包中位均98µs，p95为115/122µs。记录可观察到7包和3包的归还批次，但此分组只是描述统计，不证明空口每事件包数或控制器极限。详见[trace_audit.json](trace_audit.json)。

trace_1.json 的采集、CRC和音频全部有效，但逐条读出耗时超过现有30秒Transfer超时，最末CLOSE返回0x8d；首次脚本错误期望成功，故runner_passed=false保留。trace_2脚本改为按已过30秒的清理返回校验，通过。超时策略未改；离线审计明确分开有效采集和清理结果。

## 确认合并候选

原H5接收可靠帧后优先发送独立ACK。试验参数ACK_DELAY_US=100允许100µs内准备好的下一包在H5头中携带最新确认；无待发包时计时结束发送独立ACK。发送开始后新收到的可靠帧继续保留独立确认，窗口仍1，重试和序号/数据校验不变。原默认参数0保持原行为。专项仿真验证携带确认的序号、避免重复ACK、空闲回退以及长帧发送期间新RX确认；原H5全回归、默认0回归及UART/H5系统冒烟均通过。

最初同时保留记录器的候选构建成功但setup18处违例、Fmax48.636MHz，时序门禁拒绝，未编程。移除记录器后D340候选50MHz setup/hold0/0、Fmax50.481MHz，通过门禁后才加载。D340 SHA256为`59679540f2fa552212bbe0d0168a29b362a1f85580389b73c53ee0b5f0f1ec85`。诊断8AF4为50.049MHz、setup/hold0/0，SHA256为`2399b9cfd66037c4834052dbcf151f5bddcdfd16ed32d142701260de18755c66`。

三次32768字节、8112块、ACK_READ、无响应写入：原H5+记录器8AF4前测10073/9846/9936 B/s，中位9936；无记录器确认合并D340为9889/9222/9756，中位9756。对照含记录器差异，并非只改一个参数的等布局配对，不能做精确因果归因。恢复无记录器、原H5的交付22B4后三次为9671/9380/9420、中位9420，显示前后漂移，不能据此判定合并策略优劣。因此补做D340/22B4两份无记录器镜像交替三组，各次编程后再建立唯一BLE连接，结果见[paired_speed.json](paired_speed.json)、[speed_audit.json](speed_audit.json)、[summary.json](summary.json)。

交替三组候选/原版分别9669/9845、9540/9503、9714/9632 B/s，配对变化−1.78% / +0.39% / +0.85%，配对中位+0.39%，方向不一致且幅度小于前后漂移，没有可确认收益。最终未采用确认合并。两组中位分别9669/9632 B/s，不能只引用该微小差异宣称提速。15份测速通知及2份轨迹均通过离线CRC/PCM核查。后续应进一步核对串口真实ACK帧数量与控制器队列/无线调度，或在手机实测连接优先级效果；本轮尚未做空口观测，也未证明控制器绝对上限。

## 记录与恢复

| 项目 | 记录 |
|---|---|
| 诊断构建、输入和程序 | [trace_build.json](trace_build.json)、[trace_inputs.json](trace_inputs.json)、[trace_program.log](trace_program.log) |
| RAM高地址综合网表核对 | [trace_memory_check.json](trace_memory_check.json)，16个SDPB全部12位读写地址 |
| 诊断定向仿真 | trace_bridge_sim.log、trace_gatt_sim.log、trace_sources/tests/ |
| 原始物理轨迹与审计 | trace_1.json、trace_2.json、[audit_trace.py](audit_trace.py)、trace_audit.json |
| H5专项/回归/系统冒烟 | h5_piggyback_sim.log、h5_delay_regression.log、h5_default_sim.log、piggyback_system_sim.log |
| 未编程时序失败镜像 | piggyback_build.json、piggyback_with_trace_rejected.json |
| 干净候选构建、输入与程序 | piggyback_clean_build.json、piggyback_clean_inputs.json、piggyback_clean_program.log |
| 初始九次及交替六次通知与审计 | baseline_before_*.json、candidate_*.json、baseline_after_*.json、paired_candidate_*.json、paired_baseline_*.json、[audit_speed.py](audit_speed.py) |
| 最终恢复和完整音频复验 | release_restore_program.log、release_recording.json、release_recording.wav、final_device_identity.log、restored_identity.json |

source_before/为原生产输入；trace_sources/、piggyback_sources/、piggyback_clean_sources/分别保留实验输入。全程BLE客户端串行，编程均等客户端结束。最终30个固件输入和43个Android输入、ready_manifest、APK哈希与第十二轮交付完全一致；未为未采用候选重跑全部RTL/Android回归。实际空口、手机GATT/UI/后台及手机吞吐仍待测；跨重启boot_id可能重复，重配置后删除手机未完成下载。音源仍为内置1秒测试音。
