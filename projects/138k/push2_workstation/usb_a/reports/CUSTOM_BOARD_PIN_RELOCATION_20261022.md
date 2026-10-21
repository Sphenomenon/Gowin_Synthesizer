# 自定义 138K：显式引脚重定位配置与验证

日期：2026-10-22，Asia/Shanghai。承接[三份网表候选](CUSTOM_BOARD_PINMAP_20261022.md)和用户已确认的 USB2 接入要求。

本文保留 v1 的生成身份、哈希及当时的 59 项测试结果。后续请求综合／上板／固化时发现了电气阻断，当前 v2 增加明确检查；结果见[上板前检查](CUSTOM_BOARD_PREFLIGHT_20261022.md)，不能继续把本轮位置验证解释为可固化。

## 1. 交付范围与身份

本轮把候选表接成现有 `build.py` 的独立 `--prepare-pinout custom-138k` 入口，版本化[底板配置](../boards/custom_138k/pinout.json)、[生成工具](../tools/workstation_pinout.py)与[回归](../sim/test_workstation_pinout.py)。使用方法见[配置说明](../boards/custom_138k/README.md)。不是新增编号生产 builder，不复制整机，不改冻结基线、vendor 或整机 RTL。

- 配置身份：`custom_138k_usb2_20261022_pinout_v1`。
- 设备：`GW5AST-LV138PG484AC2/I1`；同一 30354 核心板仍是显式前提。
- 工作区起点：Git `3e1475e0f4c498d2171cb17269422ca6cb37d305` 加本轮未提交配置／工具／测试／文档；精确生成输入由下列哈希确定，不把起点提交冒充包含这些新文件的提交。
- 来源策略：`explicit_custom_board_pinout`；阶段 `offline_pinout_only`；`synthesis_allowed=false`。
- 位流身份：无，`bitstream_sha256=null`。硬件验收、SRAM 部署、Flash 部署均为 `false`，没有继承 full83／full85／原生装配候选的验收或发布身份。

## 2. 来源闭包

原始网表目录 `~/Documents/fpga补充文档/` 保持只读。不是复制网名中的旧球位：功放仅用于追踪连接器、RN 两侧和 DAC 端点，实际位置取自底板网络。

| 输入 | SHA256 | 网络／节点 |
|---|---|---:|
| `Netlist_my_138k_2026-10-21.tel` | `deff91f6c48be8d66241e32107b88f7eea47ad2bf6c5b607b139c4b85c33a121` | 185／737 |
| `功放.tel` | `b0ae6b2be4b59a60244a98ea870fc701bb4e8186123b7cb54cf79e22ea628b75` | 100／492 |
| `蓝牙.tel` | `832e1eae56a744f8535899f57caea097f51419e2eb210186a492c182e5091eb2` | 21／88 |
| `boards/custom_138k/pinout.json` | `4ae36c3a4af766bb1c6f515a0b867f913e35f40769ad04888b759d210733bd2a` | 配置 |
| `tools/workstation_pinout.py` | `858506d9a15489047d7304085f8f8b114b925ade49caad4a41cf5c2c82b10428` | 位置生成 |
| `tools/workstation_baselines.py` | `96db9cf95c8747f68ffd4c9949f6774baa51eda6a43b8ff314d9a7aa14167ac0` | 锁定来源读取 |
| `build.py` | `9a3e846cb9d4300af6c987e7201074388da71395d85d25b417c3d0e82c764819` | 显式入口 |

`accepted_full83` 的清单 SHA256 为 `9bc6482b5885b9bc635d5089589e62aad6adf182a1822e2945a54be024c12717`，其锁定 `constraints/tang_mega_138k.cst` SHA256 为 `9004791f6a568dbce950b4a2d55c51c9c88647e6fe333ec3ca51faf2fbac1bc0`。通过现有基线 API 校验闭包后，仅读取未变的核心板固定位置／电气约束；不因此采用 full83 的 USB、音频、HDMI 旧板实现。

## 3. 实际生成结果

执行：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-pinout custom-138k \
  --netlist-dir "$HOME/Documents/fpga补充文档"
```

本次输出在 `usb_a/results/custom_138k_pinout_20261022_005248_521448/`，生成结果留在忽略目录，不把位置草案添加到现有工程或作为可下载输入。

| 产物 | SHA256 |
|---|---|
| `custom_138k.locations.cst` | `282a251a97016aa774b14277ba534c1d29c57ca05b6b8a87bd9afd08bace352b` |
| `pinout.json` | `dc0cc55e9bf0c6bc83f3ac3250282e967ae08902dae36fa78006432bdabf17c6` |

实际规划 **101 个端口、110 个物理球位，无重复占用**：

| 分组 | 端口数 | 处理 |
|---|---:|---|
| 核心板 | 69 | 66 个 `ddr_*` 与时钟／两根调试 UART；138 条原 `IO_LOC`／`IO_PORT` 保持 |
| 功放／DAC | 10 | 按同号排线及明确列出的 RN 配对假设 |
| USB2 ULPI | 12 | 8 位 DATA、CLK／DIR／NXT／STP |
| TF SPI | 4 | MISO AA15、MOSI W14、SCK V15、CS W15 |
| HDMI TMDS | 4 | 保留合法原生差分对；四对均标记待串行极性补偿 |
| HDMI HPD／CEC | 2 | K13／K14；K14 不再作为旧使能输出 |

功放 `hp_bck=A16`、`hp_ws=B16`、`hp_din=A15`、`dac_mclk=D17`、`dac_pdn_n=C17`；MCLK 不占用 USB2 DATA7 的 B17。保留另 13 个 TF／振荡器／开关／JTAG／配置相关球位。蓝牙记录 15 根信号和反序连接关系，核对八个电源／地触点；除 T14 外未猜测只有连接器端点的 BGA。

已从生成文件重新解析全部位置，与计划逐一比较，并与前一报告的音频／ULPI／TF 共 26 个位置比较一致。全部核心板行与锁定原文比较一致，四对 HDMI 都需要反相且标记 `implemented=false`；网表和四项生成配方哈希均从实际文件复算一致。

生成器拒绝输入哈希漂移、缺文件、路径逃逸、端点断开、错误 bank、重复端口／球位、侵占保留脚、旧 Dock 端口遗留和原生差分对漂移。输出必须为新目录且不得置于输入目录内；CLI 拒绝混入整机／综合／发布选项，不写 latest 或部署索引，不生成 `.gprj`／位流。

## 4. 验证结果

以下 **59 项测试全部通过，无跳过**：

| 命令（位于 `usb_a/sim/`） | 结果 |
|---|---:|
| `python3 test_workstation_pinout.py` | 20／20 |
| `python3 test_current_workstation_sources.py` | 10／10 |
| `python3 test_stage_usb_firmware.py` | 6／6 |
| `GW138K_VERIFY_CLEAN_PREPARE=1 python3 test_workstation_baselines.py` | 23／23 |

最后一项在无私有历史暂存的本地干净 clone 中比较三个整机 prepare 路径，文件输入哈希完全一致：

| 路径 | 文件数 | 输入清单 SHA256 |
|---|---:|---|
| `--current-workstation` | 424 | `40528a5a405aa1cdc746a5a14f843672130af899087afbca11a8802c5c02add8` |
| `--current-workstation --cnn-timing85` | 424 | `cfc8b8d3d703b6a7e9b349ab475ece24d1debcce9da645a6cc8844c591fdacb4` |
| `--resource-rework --resource-timing` | 442 | `a51c5b0a2b27b665b20449578cae23a4bd9727d323956ca2e7b320ec5702b096` |

同时通过既有 trace CDC 仿真（1338 次时钟检查、128 种电平组合及复位）和 lifecycle scoreboard（36395 接受、36235 播放、160 取消），损坏锁定输入时拒绝新建输出。它们证明旧来源边界未被新位置入口混入，不证明 USB2 ULPI 或新 DAC 已可运行。

## 5. 未完成项与回退

音频排线同号、RN1／RN2 内部配对、蓝牙排线反序和同一核心板仍为显式物理前提；网表本身已足够推进本阶段，不要求重新提供整份原理图。

后续需在独立的新板原生装配中实现端口／复位和完整 IO 电气约束、USB2 ULPI Host 与域交接、DAC 型号对应的串行格式／MCLK／上电静音、四路 TMDS 极性补偿及 CEC 安全处理。不能直接把旧软 PHY D+/D−、`pt8211_tx`、`pa_en` 或 `hdmi_tx_en` 改名当成已接通新硬件。Push／25K 仍轮流使用同一 USB-A 口，不引入同时连接或 High-Speed 假设。

本次没有综合、P&R、全板时序／CDC／PLL 验收、物理音频／HDMI／USB 验收、SRAM 下载或 Flash 写入。完整新板候选必须另有源身份、约束和位流哈希及独立离线／实板证据。

回退：继续使用原有 full83／pinned timing85／resource-timing 的显式选择和既有部署记录；本入口没有替换它们的 RTL、`p11.cst` 或冻结输入，无需刷板。保留生成结果以供核对，不删除历史目录或无关用户文件。
