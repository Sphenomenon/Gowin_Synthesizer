# BLE 状态与历史 GAO 解码

本例默认构建不插入 GAO。此目录的 `decode_status.py` 用于离线分析已经保存的原实板 CSV；不构建、下载或采集 FPGA。原 GAO 配置和位流保存在 [archive/gao_20261016](../archive/gao_20261016/README.md)，其中的跨 JTAG 时钟 hold 违例尚未签核。

在例程根目录执行：

```sh
python3 debug/decode_status.py reports/hardware_20261016/ble_status_20261016_001418_174723_core0_window0.csv --output reports/ble_status_decoded_new.json
```

CSV 中的信号数值按 Gowin 导出的十六进制解析；时间轴是导出标签，不能用来推算 UART 波特率或真实经过时间。原文件共 128 个样本且所有信号恒定：flags=`0F`、H5=`80`、init=`0B`、error=0、ROM=2、补丁片数=120、HCI 命令数低 8 位=132。即采样时已初始化和连接、未订阅、未报告失败。真实读取与通知结果由 [主机实测报告](../reports/hardware_20261016/ble_hardware_20261016.json) 证明。

USB1 为 SE0、activity=0、SE0 sticky=1，只说明该次被动监测未见跳变。这个例程既不发送 USB 数据也不解码协议，不能用这些值认定 USB 枚举或故障。

## 驱动状态表

顶层保留 `status[767:0]`，每字 32 位，字 n 对应 `status[n*32 +: 32]`。下表为 RTL 定义，普通构建保留网络不代表已安装 GAO 核。原 CSV 只采集其中部分字段。

| 字 | 含义 |
|---|---|
| 0 / 1 | 魔数 `0x42545647` / 格式版本 1 |
| 2 | bit0 outputs_active、1 H5 link_up、2 initialized、3 connected、4 subscribed、5 failed、6 session_ended；bits9～11 hci_valid_mask |
| 3 | enable 后的 uptime_ms |
| 4 | bits7:0 H5 状态、15:8 初始化状态、23:16 GATT 状态 |
| 5 | bits31:24 error_code、23:16 last_status、15:0 last_opcode |
| 6 / 7 | 已发 HCI 命令数 / 完成补丁分片数，成功时为 120 分片 |
| 8 / 9 / 10 | H5 RX 帧数 / TX 帧数 / 重传计数 |
| 11 / 12 / 13 | UART 错误 / 协议错误 / 通知计数 |
| 14 / 15 / 16 / 17 | ACL RX / ATT 请求 / 完成包 / 应用错误计数 |
| 18 / 19 | 蓝牙地址低 32 位 / 高 16 位 |
| 20 | bits7:0 ROM 版本、19:8 连接 handle |
| 21 | GATT 运行毫秒数 |
| 22 / 23 | CLK_HZ / BAUD，当前为 50000000 / 115200 |

| 错误码 | 含义 |
|---|---|
| 1 | 初始化阶段传输失败 |
| 2 | HCI 响应超时 |
| 3 | HCI 状态非零 |
| 4 | 芯片型号不符 |
| 5 | ROM 不为 2 |
| 6 | 地址响应长度异常 |
| 7 | 补丁分片回显异常 |
| 8 | 启动后 5 秒仍未建立 H5 |
| 9 | 运行中传输失败 |

定位错误时应同时记录 last_opcode、last_status、H5 状态和 UART / 协议错误计数。初始化后模组自行重启时，原包不会自动重新执行完整固件与 HCI 初始化，使用 SW1 重开会话。`h5_link_up=1` 单独不能代表初始化完成。
