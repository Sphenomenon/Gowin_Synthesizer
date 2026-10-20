# 第十五轮：实际H5/UART开销与8112字节块下的2Mbps复测

本轮测量实际独立ACK、业务帧、串口字符及模块独立ACK计数，并在当前OPEN_EXTENDED/8112字节块下重测921600→2Mbps。此前第八轮2Mbps使用460块，故本轮重新验证当前较少业务往返条件。持续提速目标保持进行。

## 计数证据

仅SRAM诊断FFF1返回U5标记、FPGA发出的独立ACK数、发出的host帧数、UART接受字符数、模块返回的独立ACK数、重试数、实际连接间隔及错误计数，并以CRC16保护。计数在UART握手/帧发送结束边界更新，不改变H5窗口1、原立即确认策略或ACL实际额度8。区间包含采样FFF1读响应等少量开销，不能当作纯音频或空口字节数。

每次32768字节、5个8112/尾块，原速前三次均1321个FPGA独立ACK、1302个host帧、56339/56339/56340个UART字符，模块独立ACK1287–1295；2Mbps为相同1321/1302、56339字符，模块独立ACK1302。所有采样区间重试、UART和协议错误增量为0，下载前后实际间隔均15ms。计数均模16/32/8位计算，原始FFF1及通知保存。

FPGA运行50MHz，921600四舍五入分频54，实际925925.93 baud；2Mbps分频25，实际2000000 baud。8E1每字符11bit：原速字符占线约0.669秒，2Mbps约0.310秒。工具JSON的serial_8e1_seconds使用名义baud估算（原速约0.672秒），离线[audit_serial.py](audit_serial.py)按实际分频重算。两者均非互斥耗时分解，串口工作可与控制器无线调度重叠。

## 速率对照

同一计数源、同一客户端、块长、传输协议与参数请求，仅运行期FAST_BAUD921600/2000000不同。初始化器两镜像均使用相同已验证FC17编码及不支持速率拒绝逻辑；启动115200/8E1和完整补丁不变。

| 阶段 | 吞吐B/s | 中位B/s |
|---|---|---|
| 921600前测 | 10161 / 9502 / 9498 | 9502 |
| 2Mbps | 9579 / 9495 / 9709 | 9579 |
| 921600回测 | 9752 / 9758 / 9216 | 9752 |

候选较前测中位约+0.81%，较原速回测约−1.78%，未证明稳定收益，故不采用。最终决策和恢复验收见[serial_audit.json](serial_audit.json)、[summary.json](summary.json)。这是一轮先后分组加回测，并非交替配对；不能只根据小幅中位差异宣称提速。实际字符发送时间明显下降而吞吐未相应增加，是控制器/无线调度仍占主导的证据，不能据此宣称硬件绝对上限。

最终恢复第十二轮22B4源码和SRAM，Flash未改写，APP仍0.2.8；30个固件输入、43个Android输入、ready_manifest及APK逐项身份相符。恢复后完整192000字节音频、参考WAV、READ/ACK_READ重放、非法CRC/范围原子拒绝及断线续传复验记录在release_recording.json。本轮未为未采用候选重跑完整RTL/Android回归。

## 镜像与验证

原速诊断D318 SHA256 `372f636893214089dcec7397480e7acb06bee08ecfac8ca63b345d90f5ab2fe8`，Fmax50.505MHz。2Mbps诊断D1C3 SHA256 `9ee7a10e8220ce2475ad8cec27eb8f0e40de1ac4ae298a181904cc1603cbc56e`，Fmax50.018MHz。两者均50MHz setup/hold0/0，正常程序门禁通过后才加载，未改写Flash。

UART计数仿真逐字符独立监视实际串口，核对发出的独立ACK、host帧总数与字符数，并校验禁用清零；GATT仿真检查全部字段/CRC、普通/增强连接、实际间隔更新、异连接句柄和失败事件隔离。50MHz/2Mbps系统仿真检查253字节补丁、切速、命令/无响应写、重连及诊断CRC；拒绝切速和未知速率在HCI前拒绝用例均通过。首个系统用例沿用BTST标记预期而失败，已保留uart_2m_old_marker_failure.log；随后针对U5诊断格式更正独立标记/错误/CRC检查，uart_2m_sim.log才是通过结果。本轮不将短补丁系统冒烟冒充完整30147补丁仿真，真实板卡仍完成全部初始化。

| 内容 | 记录 |
|---|---|
| 原速构建/输入/编程 | counter_build.json、counter_inputs.json、counter_program.log |
| 2Mbps构建/输入/编程 | counter_2m_build.json、counter_2m_inputs.json、counter_2m_program.log |
| 时序/仿真 | timing_checks.json、component_simulations.json、baud_simulations.json |
| 原速前三次/2Mbps三次/原速回测 | serial_baseline_*.json、serial_2m_*.json、serial_baseline_after_*.json |
| 独立计数CRC/逻辑CRC/PCM审计 | [audit_serial.py](audit_serial.py)、serial_audit.json |
| 最终交付恢复 | release_restore_program.log、release_recording.json、release_recording.wav、final_device_identity.log、restored_identity.json |

执行 `python3 reports/speed15_20261020/audit_serial.py` 重算各原始通知、全部PCM和串口计数。工具通知数组在清理后才序列化，故CLOSE/DELETE响应出现在数组中；离线重组全部CRC，唯独在与计数区间比较物理ACL数量时扣除采样之后的这两类响应。此区间精确推导1299个通知ACL包，实测1302个host帧还包含FFF1响应等。计数是实际H5帧/字符观测，ACL空口仍未直接抓取。

source_before/保存原交付源码；counter_sources/、counter_2m_sources/为诊断归档。计数工具和所有客户端顺序执行，编程等待客户端退出。手机原生GATT/权限/UI/后台及吞吐未测，跨重启boot_id可能重复；重新配置后删除手机未完成下载。仍为内置1秒测试音。
