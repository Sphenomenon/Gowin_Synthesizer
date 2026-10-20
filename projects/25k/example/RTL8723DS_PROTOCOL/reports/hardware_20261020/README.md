# 138K v1 最小命令协议在 25K 的实板验收

2026-10-20，北京时间。**最小命令收发通过**：同一最终镜像完成两次 SRAM 启动、三次 BLE 连接和 20 条业务响应校验；自动重连、重传、错误处理及重启 boot_id 变化均通过。汇总见 [summary.json](summary.json)，功能边界见 [最小实现范围](../../docs/MINIMUM_PROFILE.md)。

## 最终镜像

| 项目 | 结果 |
|---|---|
| 器件与时钟 | GW5A-LV25MG121NC1/I0，50 MHz |
| 构建 | `builds/20261020_024629_137760/impl/pnr/ble_protocol.fs` |
| SHA256 | `72d6d72f81312f58ac47dba95e647fc85898d8a80f2db94d6bbde368a11b44fc` |
| UserCode / 下载后 Status | `00002764` / `70022020` |
| 时序 | Fmax 55.529 MHz；setup/hold 违例均为 0 |
| 物理资源 | 10377 LUT，6270 寄存器，8797/11520 CLS，27/56 BSRAM |
| 下载 | JTAG 2.5 MHz，SRAM Program+Verify；未写 Flash |

最终下载两次均校验成功，见 [02:47:50 下载](sram_ble_20261020_024750_051229.json) 和 [02:48:35 下载](sram_ble_20261020_024835_114983.json)。构建清单、综合/PnR 日志、时序与资源报告均保存在本目录。

24 个硬件构建输入逐一与最终构建暂存目录比对一致，哈希保存在 [tested_inputs.json](tested_inputs.json)。测试工具哈希见 [tested_tools.json](tested_tools.json)。原包 MANIFEST 中 40 个文件与 138K 参考工程一致，见 [reference_comparison.json](reference_comparison.json)。

## 命令及无线验证

[首次启动记录](protocol_random_address.json) 完成两个连接，第二个连接由 FPGA 断线后重新广播恢复，无需重载镜像。两连接使用不同 nonce，boot_id 均为 `3ea7756a7d4eead4`。

| 检查 | 实测结果 |
|---|---|
| 广播与数据库 | 名称 GW25K-PROTO，128 bit 服务 UUID 正确；五个业务特征和属性均可发现 |
| Capability | 20 字节，major=1，value_limit=20，max_logical_message=512，boot_id 非零 |
| 能力宣告 | capabilities=0、max_pcm_chunk=0、recording_slots=0，未宣称具备录音或合成器控制 |
| Status Read | 20 字节一致摘要，模式和声部为未知值 0xFF |
| HELLO | Write with response 分片写入，收到 40 字节逻辑响应，boot_id/revision/nonce/CRC32 正确 |
| GET_STATUS | 收到 84 字节逻辑响应，64 字节 payload，valid_mask=0、窗口 flag=8，CRC32 正确 |
| 重传 | HELLO 和 GET_STATUS 重传均返回逐字节相同的缓存响应；首片精确重复可继续完成消息 |
| 请求冲突 | 同 ID 不同内容返回 REQUEST_CONFLICT=0x86 |
| 未知命令 | 返回 UNSUPPORTED=0x80；随后复用未接受的 ID 执行 GET_STATUS 成功 |
| 坏 CRC | request_id=99 的损坏消息无业务响应；后续 ID=4 成功，证明错误没有消费高水位 |
| 乱序 | ATT Application Error=0x80；后续合法命令成功 |
| 自动重连 | 断开后重新扫描、发现服务、订阅并用新的 nonce 从 ID=1 建立会话成功 |

[重启后记录](protocol_after_restart.json) 完成第三个连接，再次检查命令及错误路径，boot_id 变为 `7d4eead4fa9dd5a8`。两次 SRAM 启动的 boot_id 与系统设备标识对照见 [boot_id_restart.json](boot_id_restart.json)。该单连接记录中的 `automatic_reconnect_passed=false` 表示此轮未运行第二次连接；自动重连验收依据前述双连接记录。

每条命令的完整请求/响应十六进制均在 JSON 中；归档时再次独立校验了 20 条响应的逻辑长度和 CRC32。boot_id 来自真实控制器 HCI LE Rand，普通重连保持、设备重新启动后改变；这两次观测不构成随机数统计质量测试。

## 仿真和构建适配

[simulation.json](simulation.json) 记录 9/9 组回归通过，原始日志在其对应 `reports/simulations/20261020_024630_301273/`：命令状态机、板级生命周期、H5 同步缓存、原 FFF1/GATT、完整 UART8E1/H5 系统、错误 ROM、失败 LE Rand、全零 LE Rand、主机编解码。

命令单元回归覆盖 512 字节消息、分片错误/超时/重试、nonce、32 条完整请求比较与响应重放、60 秒到期及容量淘汰。完整 UART 模型从原厂二进制重建补丁并逐字节核对 30147 字节/120 片，再验证新服务、HELLO/GET_STATUS 分片通知、断线重新广播及新会话。无效 LE Rand 在开启广播前停止初始化。

138K 的 distributed RAM 优化在 25K 不受支持，早期布局失败；最终改为同步块 RAM 和对应读取等待，资源下降后完成布局及全部回归。这些失败产物没有用于下载。

首个可布通候选曾在同一公共地址广播新 UUID，但 macOS 返回旧 FFF0 数据库，失败记录保留为 [protocol_first.json](protocol_first.json) / [host_service_cache.json](host_service_cache.json)。最终镜像通过 HCI 设置基于启动随机数的标准静态随机地址后，真实服务发现和全部命令测试通过；未清理系统缓存或更改系统蓝牙设置。

## 复现和限制

进入例程目录，准备安装 `tools/requirements-ble.txt` 的 Python 环境后执行：

```sh
python3 program_sram.py --manifest reports/ready_build.json --frequency 2.5MHz
python3 tools/protocol_check.py --output reports/protocol_next.json
```

默认两个连接，工具会在测试结束断开。若 180 秒会话已经到期，按 SW1 重开会话或重新加载 SRAM。新输出使用不同文件名，保留本次证据。

本例只实现 HELLO/GET_STATUS 最小闭环；没有参数写入、合成器、效果或录音数据通路。Status 中无效组填 0，客户端必须检查 valid_mask。Status/Transfer 数据库项存在，但未实现业务订阅调度或文件传输。没有新增 GAO；内部初始化与时序由仿真/报告验证，实际命令和无线行为由本板验证。180 秒生命周期保持原设定，未宣称常驻运行。
