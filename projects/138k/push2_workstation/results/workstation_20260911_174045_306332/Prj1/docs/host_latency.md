# 主机输入与串口延迟调查

2026-09-08，本机 COM26 的 PING/ACK 往返时间用高分辨率时钟重测后仍约 **17 ms**。本轮修正了主机计时、演奏命令调度和音色预加载，但 **输入到音频输出不超过 10 ms 的目标尚未通过端到端验证**。D2XX 的 LatencyTimer 设置为 1 ms 没有带来稳定的实测改善。

GUI 已改为有界异步发送：ACK 返回前可以继续发送后续就绪命令。实物生产传输 API 的 1000 次测试全部收到 ACK，每 4 ms 注入一次 PING 时，计划事件到写串口的等待中位数为 **0.721 ms**，P95 为 **1.446 ms**，最大 **1.683 ms**。这是合成输入的主机调度测量，尚非真实键盘或耳机测量。

本文记录主机侧证据与当前软件行为。FPGA 的计时定义见[全链路检测](latency.md)和[声部起音检测](voice_onset.md)。

本机 Python 为 `C:\Espressif\tools\python\python.exe`，版本 3.11.15；pyserial 为 3.5。`time.get_clock_info("monotonic")` 返回 `GetTickCount64()`、分辨率 0.015625 秒，实际相邻变化为 15/16 ms。`perf_counter` 使用 `QueryPerformanceCounter()`，报告分辨率为 100 ns。

旧截图的约 31 ms 排队、16 ms RTT 会受到上述计时量化影响，不能据其小数位判断精度，也不能减去一个固定值作为校正。量化不代表全部延迟都是假的：独立 QPC 测量仍确认约 17 ms 的真实往返等待。当前 GUI 回调、队列提交、串口写入、ACK 接收及相关期限统一使用 `perf_counter`；主机时钟与 FPGA 时钟仍未同步。

**实测记录**

以下均为同一 COM26、115200 baud、合法 PING/ACK 事务；没有演奏测试音。单位为 ms，表中数值保留三位小数。原始逐笔数据归档在 `docs/evidence/`，文件名中的 `after` 只表示后一次试验。

| 配置 | 次数 | 中位数 | P95 | 最大值 | 原始数据 |
| --- | ---: | ---: | ---: | ---: | --- |
| 原 VCP/pyserial，QPC 独立计时 | 40 | 16.997 | 17.051 | 18.469 | [before](evidence/serial_latency_before_20260908.json) |
| D2XX 设置 1 ms 后关闭，再打开 VCP，第 1 轮 | 40 | 16.996 | 17.031 | 17.131 | [d2xx_trial](evidence/serial_latency_d2xx_trial_20260908.json) |
| 同上，关闭 VCP 后重新打开，第 2 轮 | 40 | 16.996 | 17.052 | 17.114 | [d2xx_trial](evidence/serial_latency_d2xx_trial_20260908.json) |
| 保持 D2XX 会话，设置并回读 LatencyTimer=1 | 100 | 16.984 | 17.014 | 17.031 | [after](evidence/serial_latency_after_20260908.json) |

最后一组有 99/100 次 RTT 超过 10 ms，最短一次为 3.949 ms。前两次 VCP 重开试验的首包约 2 ms，后续又回到约 17 ms，因此首包或最小值不能作为稳定低延迟的证明。

板载桥的真实芯片是 **BL616C-50-Q2I-QFN40**，原理图来源见[硬件说明](hardware.md)。COM26 枚举为 FTDI 兼容的 `0403:6010` 通道 B，串号 `2025030317B`，D2XX 返回 `device_type=4`、`USB Debugger B`；这些兼容描述不代表板上装有真实 FT2232C。

[Sipeed 官方更新说明](https://github.com/sipeed/sipeed_wiki/blob/main/docs/hardware/en/tang/common-doc/update_debugger.md#latest-firmware)列出 Mega NEO 的 BL616 调试器固件版本 `2025030317`，与本机串号对应。公开的前代 [BL702 调试器源码](https://github.com/sipeed/RV-Debugger-BL702/blob/main/firmware/app/usb2uartjtag/usbd_ftdi.c)存在 EventChar 请求空实现，不能据兼容 API 返回成功推断全部功能有效。但未找到可对应本机 BL616 版本的公开源码，**目前无法确认约 17 ms 具体来自固件提交周期还是主机驱动聚合，也没有证据证明固件硬编码了 16 ms**。

**本轮主机软件修正**

[串口事务](../tools/instrument_backend/transport.py)新增最多 16 包在途的异步 API。每次 write 只写一个完整 12 字节请求，前一 write 返回后至少等待 `max(1.5 ms, 120/baud + 0.4 ms)`；不因线程晚醒而追赶突发。接收端只读取已经排队的字节，保留残帧，消费同次读取的全部 ACK，以 sequence/opcode 匹配各包独立 QPC 时间。没有自动重放。CLI 保持逐条等待回复的命令语义；GUI 使用异步 API。延迟敏感路径不调用 `flush()`。

[工作线程](../tools/instrument_backend/worker.py)在单一串口所有者线程中分别调度写入和收 ACK。前台优先，已就绪声部的 NOTE_ON 可越过其他声部参数；同一槽的 NOTE_ON 必须等其先前参数全部成功 ACK。松键取消尚未派发的起音，PANIC 清除待发队列，并按 UART 顺序排在已派发数据之后。窗口已满、同槽参数未确认或瞬间输入超过串口吞吐时仍会等待，因此不能给所有负载承诺 10 ms。

[GUI](../tools/instrument_ui/app.py)连接成功后，将每个声部的六项音色参数作为后台任务预加载。只有同一批六项参数全部成功 ACK，才将该槽标为就绪；界面显示准备进度。32 槽共 192 次参数事务；这些参数可以在限定窗口内流水发送，不再把 192 次往返串行累加为准备时间。准备状态仍以成功 ACK 为准。

预加载在每次发送决策时让位于前台；前台声音命令提交及完成后，后台准备等待约 500 ms 的空闲再继续。同一声部的新前台操作会取消该槽尚未发送的旧预加载，旧 ACK 不得把已取消参数重新标为就绪。后台任务没有用户输入时间戳，不纳入按键排队统计。

Windows 松键去掉原有固定 12 ms 延后；X11 自动重复合并使用事件空闲回调，原始松键时刻在回调入口记录。

状态与延迟快照开始前等待先前在途命令收尾，防止声音 generation 错配；开始后只保留一个快照索引在途，新前台命令可在其 ACK 返回前打断快照。迟到 ACK 被消费，半份数据不发布。

显示“音色就绪 32/32”且参数未变化时，按键只需发送 NOTE_ON。尚未准备好的槽，或音色发生变化的槽，仍先完成参数下发再触发，不能声称首次冷启动也只有一个事务。NOTE_OFF 与 PANIC 的优先处理保留。GUI 将一批 ACK 的界面重绘合并，减少诊断查询造成的重复刷新；显示更新时间不等于声音发生时间。

通信超时或不完整写入后，普通事务被隔离，不自动重发或重连。GUI 在原句柄上尽力发送一次独立 PANIC 并有限等待确认，随后关闭；已尝试的清理 PANIC 不重复发送。若清音 ACK 缺失，日志明确写为未确认。单纯 PING 探针的 `close()` 保持无声，不自动发送 PANIC。

默认 `auto` 保持使用操作系统 VCP/pyserial。D2XX 仅通过显式 `--serial-backend ftdi` 选择，用于诊断对照；它验证精确通道 B 身份、连接期间设置并回读 1 ms、关闭前尝试恢复原值。`profile.latency_ms=1` 是设置回读，**不是实测链路延迟，也不是自动加速成功标志**。其实现不修改注册表、不复位整个 USB 设备、不操作 JTAG 通道 A。

**有界发送的实物证据**

原位流、同一 COM26、115200 baud，发送内容均为 PING：

- 整批一次 write 的 8/12 包出现缺 ACK；按完整包、至少 1.5 ms 间隔发送，32 组 × 32 包为 **1024/1024 ACK**。这验证了当前试验条件，不是永久无丢包保证。[节奏对照](evidence/serial_ping_pacing_20260908.json)、[压力原始记录](evidence/serial_ping_pacing_stress_20260908.json)。
- 生产异步 API：1000 次、计划间隔 4 ms，1000 ACK，最大 5 包在途；发送等待中位数 0.721 ms / P95 1.446 ms / 最大 1.683 ms。RTT 仍为中位数 11.152 ms / 最大 20.210 ms，表明改善来自发送不再等 ACK，尚未证明桥接本身变快。[逐笔证据](evidence/serial_pipeline_1000_20260908.json)。
- 生产 GUI 工作线程的提交/派发/ACK 路径：200 个合成 PING 事件全部收到 ACK，实际输入间隔约 4.08 ms；提交→写串口中位数 **0.526 ms** / P95 **1.152 ms** / 最大 **1.639 ms**。探针只替换连接/关闭，禁用音符、参数及 PANIC，测试未覆盖真实键盘回调或模拟音频。[工作线程证据](evidence/serial_worker_200_20260908.json)、[探针源快照](evidence/measure_worker_ping_20260908.py.txt)。
- 随后重开普通同步会话：100 次 RTT 中位数 16.976 ms / 最大 18.875 ms，100/100 超过 10 ms。write 调用中位数 0.056 ms，read 调用累计中位数 16.866 ms；write 返回快不等于字节已到 FPGA，因此这些数字不能单独定位 USB 去回程。[拆分计时](evidence/serial_blocking_retest_20260908.json)。
- 真实 115200 RTL 仿真连续 8/12/64 包均通过；包内增加 400 μs 停顿会触发当前解析超时，丢失该包后恢复。实物缺 ACK 的具体方向尚未定位，本轮采用已经实测的包间节奏，不改 FPGA 解析器或追加 ACK 填充。[仿真与输入哈希](evidence/uart_pacing_115200.json)。

**如何复测与判定**

先断开 GUI 对同一端口的连接，在项目目录运行以下 PING 对照；工具只测串口往返，不触发 NOTE_ON、不应用音色、不发送 PANIC：

```powershell
python tools/serial_latency_probe.py --port COM26 --serial-backend pyserial --count 100 --output build/serial_latency_vcp_retest.json
python tools/serial_latency_probe.py --port COM26 --pipeline --count 1000 --interval-ms 4 --output build/serial_pipeline_retest.json
# 可选诊断对照，无稳定加速证据
python tools/serial_latency_probe.py --port COM26 --serial-backend ftdi --count 100 --output build/serial_latency_d2xx_retest.json
```

两种后端依次测试，每组结束关闭连接，再独立重开复测。保留逐笔数据、P50/P95/最大值、超过 10 ms 的次数、Python 时钟与设备配置。孤立首包变快不判定改善。

VCP 的设备注册表 `LatencyTimer` 读到 16。此前写入尝试因实际 Windows 进程权限返回 `WinError 5`，不是自动审批拒绝；没有完成该设置变更。[配置脚本](../tools/configure_serial_latency.ps1)默认只读检查，用户随后执行 `-Apply` 时，脚本再次确认窗口未提升到管理员，设置仍未应用。本轮异步 GUI 不依赖该设置；它仅保留为可选驱动对照，不能记为已解决。

必须退出并重新启动旧 GUI 进程，单纯断开再连接不会加载新的 Python 代码。随后在 GUI 等待音色准备完成，用同一音色、声部和包络分别测试空闲单音、连续演奏及开启诊断查询时的排队变化，并保留匹配的 0E/0F 记录。无须为本轮主机修改重新构建 FPGA；若位流或包络同时改变，应另记条件，避免混淆对照。

PING RTT 包含去程与回程，不能除以二当作单向发送延迟，也不能直接加上 FPGA 时长当作输入到声音延迟。0F 从 FPGA 命令提交开始，排除了主机排队和 USB 去程；它的很小读数不能证明整个输入链路达到 10 ms。

0E 只能用同一次主机事务及其 FPGA 记录推导有依据的区间。记 Q 为 GUI 回调到写入，R 为 RTT，A 为 FPGA 首 UART start 到 ACK 就绪，D 为同一起点到目标数字输出端点，则数字输出延迟位于 `[Q+D, Q+R-A+D]`。区间上界不超过 10 ms 才能为该次事件提供保守的数字链路达标证据；上界超过 10 ms 也不能反过来证明真实单向延迟一定超过 10 ms。

数字端点为 PT8211 对应立体声帧最后一位发送完成。物理按键到操作系统回调、DAC 模拟滤波、功放、耳机与声学传播不在计数范围内；模拟输出或可闻起音的 10 ms 要求仍需外部测量。当前结论是主机计时和调度已修正，串口路径瓶颈及端到端达标验证继续待测。

主机最终回归为 **233 项 Python/Tk 全部通过**，其中 27 项为异步 worker 对抗检查。测试使用虚拟时间验证正确性，未用测试耗时冒充实物延迟；COM26 数值单独来自上述实物记录。[日志](evidence/python_host_latency_20260908.log)、[源码与证据哈希](evidence/verification_inputs_host_latency_20260908.json)。
