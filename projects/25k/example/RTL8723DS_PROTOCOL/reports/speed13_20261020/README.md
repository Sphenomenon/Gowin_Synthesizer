# 第十三轮：实测控制器能力、等待时间与连接间隔

本轮完成只读能力诊断、发送等待计数及三组各三次的原参数→区间参数→原参数实测。未证明区间参数带来吞吐收益，生产源码、生成源码和 SRAM 已恢复到第十二轮 22B4。Flash 未改写，APP 仍使用 0.2.8。持续提速目标仍在进行。

## 实测结果

| 参数/阶段 | 三次吞吐 B/s | 中位 B/s | 下载前后实际间隔 |
|---|---|---|---|
| 原请求 15 ms，前测 | 9296 / 9462 / 9579 | 9462 | 全部 15 ms |
| 请求 7.5–15 ms | 9754 / 9880 / 9493 | 9754 | 全部 15 ms |
| 原请求 15 ms，回测 | 9796 / 9979 / 9975 | 9975 | 全部 15 ms |

每次 OPEN_EXTENDED、8112 字节块、32768 字节 PCM、5 个 DATA 块。macOS ATT value182。九份原始通知均独立重组、验证逻辑 CRC32、PCM CRC32、连续偏移、对象身份和参考音频逐字节一致。参数范围改变后电脑仍使用 15 ms，回测原参数比候选更快，故不能把前后波动归因于该改动。没有将候选固化。

只读 HCI LE Read Local Supported Features(0x2003) 和 Read Maximum Data Length(0x202f) 均返回成功。三份 CRC16 有效样本一致：低32位特性 0x1，DLE bit5 和 2M PHY bit8 均为0；最大 TX/RX 均27字节、328µs。当前控制器固件未报告这些能力，不能靠强制251字节/2M命令提速。本轮未发设置数据长度命令。

原参数前测每次约3.42–3.53秒；ACL无可用额度的计数约2.41–2.50秒（69–71%），H5等待确认约0.21–0.22秒（6.2–6.5%）。这支持继续检查控制器额度返回和连接事件调度。两类计数可能重叠，计数采样含结束后FFF1读取，不能相加视为互斥耗时，也不能据此断言硬件速率上限。每份通知按27字节HCI分包推导约1299个物理ACL包，此为推导而非空口抓包。

## 诊断镜像与复现

| 镜像 | UserCode | 用途 | 记录 |
|---|---|---|---|
| 只读能力查询 | 2DD2 | FFF1 DL/CRC16 | [dle_build.json](dle_build.json)、[dle_capabilities.json](dle_capabilities.json) |
| 原15 ms计数 | 66D9 | FFF1 P2/CRC16、实际间隔 | [profile_build.json](profile_build.json)、[profile_summary.json](profile_summary.json) |
| 7.5–15 ms计数 | 47D9 | 仅改变最小请求间隔 | [range_build.json](range_build.json)、[range_inputs.json](range_inputs.json) |
| 最终恢复交付 | 22B4 | 原BTST、原15 ms请求 | [release_restore_program.log](release_restore_program.log)、[restored_identity.json](restored_identity.json) |

三个已加载诊断镜像的50MHz setup/hold均0/0；区间镜像Fmax50.399MHz。加载工具照常校验SHA、器件、安全位和时序。source_before/保存本轮修改前生产输入；diagnostic_sources/、profile_sources/、range_sources/保存相应诊断输入、工具与定向仿真。profile_build_declaration_order.json为尚未调整声明位置的早期构建，未编程；profile_build.json才是最终66D9。区间参数与原计数镜像只有最小请求间隔6/12差异。

能力查询仿真覆盖成功、不支持、畸形长度、命令顺序和独立CRC；计数定向仿真覆盖普通/增强连接、连接更新、失败状态/异连接句柄隔离、CRC以及H5/ACL原有行为。区间仿真验证请求字段、额度耗尽与归还、接受/拒绝终态、重复订阅仅请求一次。详见各 *_sim.log、[profile_simulations.json](profile_simulations.json)、[range_sim.log](range_sim.log)。最终生产输入已恢复并逐项匹配之前通过完整回归的版本，本轮未重跑整套RTL/Android回归。

执行 `python3 reports/speed13_20261020/audit_captures.py` 可离线复查三份能力样本与九份原始通知，结果为 [capture_audit.json](capture_audit.json)。全部BLE客户端顺序运行，编程均在客户端退出后执行。release_recording_cli_error.log仅记录首次传入不存在的 --wav 选项，参数解析即退出，未连接硬件；纠正命令后的 release_recording.json 才是完整音频复验。

完整音频复验结果和最终身份见 [summary.json](summary.json)。手机原生GATT/权限/UI/后台及手机吞吐仍未测；用户报告已断电重上电、DONE慢闪，但本轮未在诊断重载前读取原固件身份/无线结果，故不将该口述作为22B4物理上电验收。内置1秒立体声测试音与boot_id跨重启重复限制仍适用；重启或重配置后先删除手机未完成下载。
