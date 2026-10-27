# a26 资源优化：整机综合、布局布线与验板交付

日期：2026-10-27，UTC+08:00。用户要求“综合布局布线，我来上板验证”。本轮只生成、核对和交付位流，没有连接板卡、SRAM 下载或 Flash 操作。

## 交付

```text
out/resource_a26_C11027C1/C11027C1.fs
UserCode: 0xC11027C1
GAOCRC: 27C1
器件: GW5AST-LV138PG484AC2/I1，C 版
视频: 1920×1080，60 Hz
SHA256: 91101332be8d8d5ac3511cc36227d77ab0fe2511f5869efb90c657b55ee1386a
```

同目录提供 `C11027C1.gao`、`verification.json`、`SHA256SUMS` 和简短验板说明。位流与原始实现输出 `out/workstation_resource_a26_20261027_c1_physical/impl/pnr/ao_0.fs` 逐字节相同。

本次交付用于用户验板，不标记硬件验收或发布完成。AE350 业务卸载仍未实施；这里只验证此前 BLE 缓存与解析优化的整机效果。

## 实际资源：与当前回退 B3 同口径

对照为原 1080p60 B3／`0xC11026B3`，两版均保留同样的 16-bit、1024-depth GAO。以下读取实际 P&R `.rpt.txt`，不再使用逐模块 CLS 分摊值。

| 资源 | B3 | C1／a26 | 差值 |
|---|---:|---:|---:|
| CLS | 62,275 | **61,184** | **−1,091** |
| Logic | 94,676 | **91,903** | **−2,773** |
| Register | 57,037 | 54,181 | −2,856 |
| 业务 BSRAM | 321 | **317** | **−4** |
| GAO BSRAM，报告另列 | 1 | 1 | 0 |
| BSRAM 总计，含 GAO | 322 | **318 / 340** | **−4，剩余 22** |
| DSP | 156.5 | 156.5 | 0 |

CLS 利用率为 **88.52%**；含 GAO 的 BSRAM 利用率为 **93.53%**。上一轮约 1.8k CLS 仅为比例估算，**本次布局后实际节省是 1,091 CLS**，不能把估算当作实测。

整机综合 XML 的 LUT 为 76,650→73,630，ALU 为 15,325→15,292，BSRAM 为 274→272。XML 少两个宽 RAM 原语与物理少四块 BSRAM 是不同计数口径，P&R 已确认后者。

## 时序与离线检查

| 项目 | B3 | C1／a26 |
|---|---:|---:|
| 最差 setup | −0.394 ns | **+0.003 ns** |
| 最差 hold | +0.085 ns | **+0.050 ns** |
| 最差 recovery | +2.942 ns | +3.016 ns |
| 最差 removal | +0.250 ns | +0.250 ns |

数值 STA 和详细路径无负余量，最小 pulse-width 余量为 +0.791 ns，无 pulse-width 违规。**setup 仅 3 ps，余量很小，不代替板级验证。**

- 原严格时序检查返回 1，唯一原因是 `clock summary inventory differs from the native plan`：GAO 引入额外的 `tck_pad_i`，周期 50 ns；全部原生业务时钟仍在，未发现时钟缺失、频率变化或负路径。保留该真实检查结果，没有修改检查器或放宽时钟清单来宣称发布通过。
- PLL／DDR 配置、公共 CDC、原生 routed CDC／DDR hold 路径检查均通过。GAO 的时钟与 16 个观测信号布局也已核对。
- 历史 routed 检查器只为 a23 执行 DDR hold 路径分支；本轮以单一精确锚点在内存中延伸到 a24～a26，保持原阈值和检查。原脚本未改；原文和适配后哈希记录在 `routes_checker_adapter.json`。
- 工具仍报告 `PR1014`：GAO 采样使用的 `clk_50m_d` 有通用时钟路由提示，保留在构建日志中，不隐藏警告。

## 构建来源与耗时

业务 RTL 来自 `42153e9`，原生输入身份为 `custom138k-native-integration-20261027-a26`。既有 `build.py --prepare-custom-board --hdmi-mode 1080p60` 准备完整 230 项编译输入；没有选择 accepted/full83 或 720p 分支。

全量综合完成后，发现综合审计器对 `endswith` 的多后缀调用误用了位置参数。修正为 tuple，提交为 `f4b4b76`；原生 prepare 回归增加实际执行审计器直到缺失综合日志边界的检查，避免只测 prepare 而漏过该问题。相关 prepare、accepted 来源和 implementation 回归分别 1／10／15 项通过。

为避免因非编译工具的一行修复再做全量综合，重新 prepare 到 `out/workstation_resource_a26_20261027_c1_checked/`，逐项核对新旧编译输入：除补丁 ROM 绝对路径重定位到同字节 ROM 外，所有 staged 输入相同；源快照只有审计器变化。复用本轮刚生成的同一个完整综合网表和报告，重新执行修正后的完整综合审计，通过。原始 prepare、原始清单和复用比较记录均保留，没有改写旧清单。

物理实现使用原有 `workstation_custom_board_implementation.prepare`，CST／SDC 与 B3 精确相同，包括三个 DDR 硬资源位置和 `wloadn_3_s0` 的 `R[40:50]C[70:90]` hold 区域。配置为 place 2、route 0、replicate 0；保留全部时钟和例外，没有增量 P&R 数据库、降频、删功能或第二轮参数扫描。

完整 P&R 从 **11:31:28.915 至 12:24:48.005**，耗时 **3,199.089 秒，约 53 分 19 秒**，返回 0。只做了一次整机综合和一次完整 P&R。

机器可读证据、输入哈希、位流标识和原始报告哈希见 [physical_c11027c1.json](ae350_resources_20261027/physical_c11027c1.json)。完整工具产物保留在忽略的 `out/`，不作为新的生产源码来源。

## 用户验板与回退

建议优先确认下载后的 UserCode 为 `0xC11027C1`，再检查 DDR 校准／BIST、1080p60 显示及闪烁、最终音频／主音量、USB 交互、BLE 连接和短录音下载。不要把离线通过等同于此前的显示闪烁、暖重配置依赖或 BLE 链路问题已消失。

本轮没有改变实际板上内容。需要回退时，原 B3 位流仍为：

```text
out/official_ddr_ab_20261026_01/c11026b3/impl/pnr/ao_0.fs
UserCode: 0xC11026B3
SHA256: a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c
```

## 后续授权：SRAM 下载与身份读回

2026-10-27 12:42，用户进一步明确要求“烧进sram”。前述未操作板卡的说明对应此前构建交付阶段；本节单独记录随后发生的部署，不改写原离线证据。

使用相同 C1 位流，下载前再次核对 SHA256；持有 `/tmp/gw138k_20261025.lock` 排他锁，目标为 `GW5AST-138C`、cable-index 5、location 54。仅执行 operation 0／2／0，即独立读身份、SRAM Program、再次独立读身份。

| 阶段 | 返回码 | 实际身份／结果 |
|---|---:|---|
| 写前独立读取 | 0 | ID `0x0001081B`，UserCode **`0xC1102515`** |
| SRAM Program | 0 | 100%，`Finished.` |
| 写后独立读取 | 0 | ID `0x0001081B`，UserCode **`0xC11027C1`** |

写前读回的是 C1102515，不能因为历史 B3 回退记录而假定本次写前仍是 B3。请求 JTAG 频率为 0.9 MHz，Program 日志记录工具自动更新为 15 MHz；未将请求频率当作整个写入过程的实际频率。

SRAM 下载和独立 UserCode 核对成功，未执行 SRAM 位流逐位回读。**未操作 Flash、未断电、未用其它位流预初始化。** 本次没有采集功能运行结果，声画、DDR、USB／BLE 仍待用户验收；不把身份读回标记为整机硬件通过。

完整命令、时间及日志哈希见 [sram_c11027c1.json](ae350_resources_20261027/sram_c11027c1.json)，原始日志位于 `out/workstation_resource_a26_20261027_c1_physical/sram_deployment_20261027_124221/`。
