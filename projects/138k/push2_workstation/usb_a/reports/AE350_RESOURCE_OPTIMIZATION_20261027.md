# AE350 分工与第一轮 BLE 资源优化（2026-10-27）

本轮只改源码、做子系统仿真和 BLE 独立综合，没有整机综合、P&R、位流生成或板卡操作。原生开发候选更新为 `custom138k-native-integration-20261027-a25`；720p 两个开发配置同步使用当天的 a25 身份，accepted full83 / timing85 来源不切换。板上 B3 不变。

## AE350 能释放多少 CLS

AE350 已经执行 UI／服务固件；把几个小控制状态机再次搬过去，收益有限。真正值得迁移的是 BLE 的 ATT／GATT、命令会话、重试缓存和录制／下载业务控制。UART、H5、ACL 搬运以及连续 PCM 采样仍留在 RTL。

以下来自 a23 原始层级综合报告，不是模块 CLS 实测。父子项已扣除重叠，`recording.encoder` 包含在 recording 中，不再单独相加。

| 可迁移范围 | LUT | ALU | LUT＋ALU | CLS 毛分摊参考 |
|---|---:|---:|---:|---:|
| GATT 自身，不含 command_endpoint | 8,207 | 366 | 8,573 | 约 5,805 |
| command_endpoint 自身，不含 recording | 2,486 | 351 | 2,837 | 约 1,921 |
| 第一阶段：以上两项 | 10,693 | 717 | **11,410** | **约 7,726** |
| 后续 recording 整棵业务子树 | 4,905 | 969 | 5,874 | 约 3,977 |
| application 整棵子树 | 15,598 | 1,686 | **17,284** | **约 11,703** |

分摊公式为 `该项综合 LUT/ALU × 62,275 / 91,975`。62,275 是 B3 整机物理 CLS；91,975 是 a23 综合 LUT＋ALU。它只能说明量级，不能预测模块独立打包和整机重布局后的实际差值。第一阶段的毛规模约 7.7k CLS，净收益还须扣除 APB 邮箱、跨域和缓冲；**本轮没有实现或验证 CPU 业务卸载，不把这笔数记为已节省**。

下一步只需要在现有 APB 上增加有界的包交接接口，软件替换非实时业务处理，不建设通用总线／DMA 框架。先确认 CPU 最长服务间隔和软件 ROM／栈预算；现有启动 ROM 16 KiB、工作 RAM 8 KiB，不能把录音和大回复队列直接堆进去。大数据按既有 `rtl/ddr_address_map.vh` 管理。音频采样、公共参数的唯一应用点、18-bit 事件和现有线规不变。

## 已落地的两项优化

1. GATT `packet` 从 264 字节改为 **32 字节头部缓存**。现有 ATT 业务片段和 UUID 检查只读取前 31 字节；长 HCI 完成事件改为接收时逐项累计匹配 handle 的 16-bit 完成数。全部报文仍按原长度接收，原 HCI／事件结构校验通过后才补充 TX credit。没有把接收 MTU 限制成 32，也没有删除长事件支持。
2. 32 项请求缓存的 ID＋时间戳共 **256 字节**，允许显式选择存储类型；25K 默认仍选 block RAM，138K 原生 wrapper 选 distributed RAM。请求／回复主体、PCM、Delay FIFO 均不改成逻辑存储；缓存容量、32-bit 时间戳、60 秒重放寿命和 nonce 语义不变。

第一项消除不必要的长缓存和动态读选择器。减少 FF 是伴随结果，不是为了压低并不紧张的 FF 总量。第二项是小范围 BSRAM／逻辑交换，资源比较必须计入新增 RAM16。

## 同口径 BLE 独立综合

Gowin 1.9.12.03，`GW5AST-LV138PG484AC2/I1`、device version C、`workstation_bluetooth` 顶层、SystemVerilog 2017。基准使用 a23 准备目录中的 BLE；wrapper 与修改前 HEAD 字节相同，core、command、recording、initializer 也核对相同。候选使用当前第一方源及现有 `prepare_adapted.py`，只在独立输出中运行 `run syn`。

| 指标 | 基准 | 当前 | 差值 |
|---|---:|---:|---:|
| LUT | 17,567 | 15,731 | **−1,836** |
| ALU | 2,383 | 2,321 | **−62** |
| LUT＋ALU | 19,950 | 18,052 | **−1,898** |
| Register | 9,723 | 7,878 | −1,845 |
| RAM16 实例 | 4 | 40 | ＋36 |
| Logic 代理值：LUT＋ALU＋6×RAM16 | 19,974 | 18,292 | **−1,682** |
| 综合 XML 的 BSRAM | 65 | 63 | −2 |
| SDPX9B 原语 | 2，均 36-bit | 0 | −2 个宽原语 |
| 18 Kbit 块等效预算，沿用现有宽度转换 | 67 | 63 | **−4** |
| 独立综合耗时 | 140.392 s | 128.502 s | 不含整机 P&R |

BSRAM 不能只看 XML：基准是 44 SDPB＋16 pROM＋3 SP＋2 宽 SDPX9B；现有物理流程把两个宽原语转换成四块。候选保留前 63 个原语，消除 SDPX9B。**预计整机业务 BSRAM 可由 321 降至 317，但尚未整机 P&R，不能当作物理实测；GAO 额外一块也不能忽略。**

按 B3 的 Logic／CLS 比例粗算，本轮约是 **1.1k CLS 的优化量级**，不是已确认的 CLS 差值。AE350 7.7k 的毛预算包含这里覆盖的逻辑，不能与本轮收益直接相加。

曾局部试验把旧 BTST 的 18 字节 CRC 改成逐字节复用，结果总 LUT 反而升至 18,093、ALU 2,386；该实现已经撤回。另两块 256-byte 缓冲改 distributed 的方案也没有并入。没有为追求“共享”保留负收益实现。

输入哈希、综合资源及网表 SHA256 摘要见 `ae350_resources_20261027/summary.json`；完整中间产物在忽略目录 `out/ble_storage_20261027/`，不是生产输入。源代码中的有效实现是本报告列出的三个 BLE 第一方模块和 138K wrapper。

## 验证与短迭代入口

- BLE 定向回归 8 项通过：包括真实 UART/H5 补丁启动、GATT、实流 PCM、录制回放／断线、32 项缓存驱逐及 59,999／60,000 ms 边界。
- 新增长事件回归覆盖 63 handles、缓存头部以外的匹配项、16-bit 大完成数、foreign handles、截断、错误 HCI 长度和空列表。
- 另跑 B2 compact、B3 bulk MTU 23／64／247、direct DATA 五项，通过；原有测试夹具保留。
- accepted 来源回归 10 项、原生完整 prepare 闭包 1 项、HDMI 模式 11 项、implementation 脚本离线回归 15 项通过。未运行整机综合／P&R，未宣称 routed timing、硬件或部署通过。

以后对 BLE 的修改可先准备候选，再只综合这个子系统：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_bluetooth.py
python3 projects/138k/push2_workstation/usb_a/tools/synthesize_workstation_bluetooth.py \
  --stage <prepared-output>/workstation/Prj1 \
  --output <new-component-output>
```

该入口只复制 BLE 已准备输入，记录哈希、XML 和实际 RAM 原语，**没有 `run all`／P&R／烧录步骤**。输入仍由现有 prepare 流程产生，不增加第二套生产来源。本轮实际候选局部综合约两分钟；积累一批有收益的修改后再跑一次完整 P&R 确认 CLS、物理 BSRAM 和时序。

回退：撤回本轮源码补丁即可回到此前开发实现；没有生成新位流，SRAM／Flash 和已部署 B3 无需操作。

## 后续小步：a26 回复工作缓存

前两笔已推送提交为 `7856649`（流式完成事件及缓存元数据）和 `b480310`（局部综合工具及预算）。以下是其后的独立增量，不改写 a25 的历史测量。

`ble_protocol_command.reply` 原有 128 字节，但 GET_STATUS 是最长的命令回复，固定 84 字节；录音命令最大 payload 为 48 字节，加协议头和 CRC 共 68 字节。大块 DATA 使用独立 transfer 通路，不占这个数组。工作缓存因此收紧为 84 字节；32 项重放缓存的 128-byte 槽位及末尾 recording ID 元数据保持不变。

回复生成、CRC 尾部、缓存重放三种写入归并到一个写端口，工作缓存映射为 12 个 `RAM16SDP4`。opcode／result 两个字节单独保持，避免 DATA 分类检查为数组引入额外读端口；新回复和缓存重放都更新这两个字节。读取仍为组合读，不增加接口周期；未添加越界保护器、通用队列或新的业务调度层。

同一 Gowin 局部综合设置下的 A/B：

| 指标 | a25 已提交 | 只缩容至 84 字节 | a26 单写端口＋分布式 RAM | a26 相对 a25 |
|---|---:|---:|---:|---:|
| LUT | 15,731 | 15,285 | **14,669** | **−1,062** |
| ALU | 2,321 | 2,319 | **2,318** | −3 |
| Register | 7,878 | 7,525 | 6,868 | −1,010 |
| RAM16 | 40 | 40 | 52 | ＋12 |
| Logic 代理：LUT＋ALU＋6×RAM16 | 18,292 | 17,844 | **17,299** | **−993** |
| 综合 XML BSRAM | 63 | 63 | 63 | 0 |
| 耗时 | 128.502 s | 126.811 s | 123.580 s | 无整机 P&R |

相对最初 BLE 基准，累计 LUT **−2,898**、ALU **−65**、计入新增 RAM16 的 Logic 代理值 **−2,675**，对应约 **1.8k CLS 量级**，仍不是布局后的 CLS 实测。预计物理 BSRAM 节省仍是 4 块，没有因为本次回复缓存变化而多记收益。AE350 软件卸载仍未实施，7.7k 的应用层毛预算不能与这里累加。

验证：BLE 8 项回归通过，增加最长 84-byte 回复在消费者停顿、时钟和 elapsed_ms 继续推进时的逐字节稳定性检查；两个元数据存储配置均覆盖。B2 compact、B3 bulk MTU 23／64／247 和 direct DATA 共 5 项另测通过，保留成功 DATA 分类、重放、错误回复和原 B1 行为。accepted 来源 10 项、原生完整 prepare 1 项、视频模式 11 项、implementation 离线检查 15 项通过。

原生开发输入身份更新为 `custom138k-native-integration-20261027-a26`，两个 720p 派生配置同步更新；现有检查逐项延续，没有改 accepted 锁定源。输入哈希及网表标识见 `ae350_resources_20261027/reply_cache_a26.json`。局部 A/B 产物在忽略目录 `out/ble_storage_20261027/reply84/` 和 `reply_ram84/`，不是生产输入。本次没有全量综合、P&R、位流或板级操作；后续集中一次整机 P&R 才能确认实际 CLS、BSRAM 和时序。

本增量可独立撤回以恢复 a25；已部署 B3 不受影响。

后续已完成 a26 整机综合与 P&R：实测 CLS −1,091、业务 BSRAM −4（317＋GAO 1），setup +0.003 ns。位流 `0xC11027C1` 交由用户验板，非硬件验收；时序清单中的 GAO JTAG 时钟差异单独保留。精确身份、资源、时序与回退见 [整机实现交付](WORKSTATION_RESOURCE_A26_PHYSICAL_20261027.md)。
