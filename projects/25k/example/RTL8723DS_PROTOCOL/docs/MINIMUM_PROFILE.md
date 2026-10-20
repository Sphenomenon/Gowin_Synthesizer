# 25K 协议测试范围

接口依据 [138K 协议快照](BLUETOOTH_PROTOCOL_V1_REFERENCE.md)。当前版在最小命令基础上接入 [内置音频录音和下载](RECORDING_PROFILE.md)，完整合成器业务仍未接入。0.1.1 的无录音基线记录见 [历史联调说明](APP_INTEGRATION_0_1_1.md)。

## 通用协议与无线链路

- 保留句柄 1～8 的 GAP、GATT、FFF0/FFF1 测试服务；业务服务使用句柄 9～22，客户端按 UUID 发现。广播名 GW25K-PROTO，广播包含业务服务 UUID。
- ATT MTU 固定 23，特征值最多 20 字节。B1 分片每片 1～14 字节，最多 37 片/512 字节，片间超时 2 秒；检测乱序、token、保留位和长度错误，忽略精确的上一片重传。
- Command 支持 ATT Write Request；0.2.1 通过 0x0C 属性额外提供 Write Command，原确认写入始终兼容。Response 与 Transfer 使用各自通知，Prepare Write 不支持。无响应写入的协商、错误丢弃及同 ID 重试规则见 [提速说明](SPEED_OPTIMIZATION.md)。完整逻辑 CRC32 与长度验证后才调度；无效消息不推进请求高水位。
- 启动执行 HCI LE Rand；状态失败、长度错误或全零随机数时拒绝初始化。随机数用于非零 boot_id 与合法静态随机地址；普通重连保留身份，重启后身份改变。
- HELLO 要求 Response CCCD、版本 1.0、非零 nonce、首次 request_id=1。每次连接重新握手；断线清空会话、CCCD、分片与请求缓存，重新广播。
- 32 个已接受请求缓存，保存完整请求（最长 36 字节），比较 CRC 在内的全部字节。缓存内精确重试返回同一响应；READ 同时重建相同 DATA。支持请求冲突、旧 ID、会话要求；新请求拒绝不消耗 ID。
- 缓存按 60 秒或容量淘汰；任务结果使用单独 8 槽，完成后至少保留 60 秒。过期变更请求应查询实际状态。
- Capability flags=0x68，PCM 块 256 字节、窗口 1、录音槽 1。GET_STATUS valid_mask=4，仅录音组有效；Status Read 为一致摘要，声音/声部字段保持未提供标志。

## 实现边界

支持 HELLO、GET_STATUS、GET_OPERATION、REC_START/STOP/INFO/CLEAR、REC_OPEN/READ、TRANSFER_ACK、REC_CLOSE、TRANSFER_CANCEL。录音任务使用 GET_OPERATION 查询；未提供主动任务事件或状态订阅。参数、效果、SUBSCRIBE 等未实现命令返回 UNSUPPORTED。

录音源为 FPGA 内置循环 PCM ROM，最多 48000 帧，下载已提交的不可变前缀；没有麦克风、外部实时采样、DDR 录音或断电保存。录音对象普通断线保留，设备重启失效。详见录音说明。

25K 不支持参考工程的 distributed RAM，H5 收包/缓存、HCI 参数、请求缓存与音频 ROM 使用同步块 RAM，读取包含预取等待；原 vendor 包保持冻结。ACL 发送额度来自控制器 LE Read Buffer Size，最多使用 8 个，按当前连接完成包数回收。

当前启动与补丁下载仍为 UART 115200/8E1，完成补丁及 Reset 后再切换 921600/8E1，见 [运行期串口提速](UART_SPEED_OPTIMIZATION.md)。

默认 SESSION_MS=0 持续运行；正数保留限时测试语义。SW1 按住/释放各至少约 20 ms 可重启；计时器饱和避免长期运行回绕重新初始化。本地测试窗口在驱动正常运行期间开启，没有配对加密或身份认证。
