# CNN 权重持久化与 Flash→DDR 启动

完整工作站可把 FPGA 配置位流和 Basic Pitch 模型分别保存在板载外部 Flash。用户逻辑启动、DDR 校准完成后，`basic_pitch_boot_model_loader` 使用只读 SPI 从模型分区搬运权重，再完整回读 DDR 校验。两次 CRC 都通过才发布 `model_status=E`；CNN 原有等待模型就绪的条件保持有效。

模型镜像是现有 `rtl/music/weights/cnn_ddr_blob.mem` 的 52,239 个 16-bit 系数，104,478 字节，CRC32 `AF01A61B`。它不含 PCM、音频文件头、演奏录音或推流内容。镜像构建工具只接受严格的 16-bit 十六进制字表并检查字数。该模型位于独立外部 Flash 分区，启动逻辑没有模型 ROM、没有新增 BSRAM。

## 分区与镜像

| 地址/大小 | 内容 |
|---|---|
| `0x000000..0x5FFFFF`，最多 6 MiB | FPGA 配置位流；当前 full85 二进制 5,283,212 字节 |
| `0x600000..0x60001F`，32 字节 | `BPF1` 模型头 |
| `0x600020..0x61983D`，104,478 字节 | little-endian 16-bit 模型字 |
| `0x10100000..0x1011981D`，DDR byte address | 模型启动后所在的已有 CNN DDR 区 |

模型镜像总长度 104,510 字节；完整打包镜像 6,395,966 字节（位流至模型分区之间填 `0xFF`）。构建器检查分区按 64 KiB 对齐、配置区没有侵入模型区、模型字数严格匹配、镜像没有超过 16 MiB/24-bit 地址范围，任何超限都报错。

头字段如下，所有整数均 little-endian：

| 偏移 | 长度 | 字段 |
|---|---|---|
| 0 | 4 | magic `BPF1` |
| 4 | 2 | 格式版本 `1` |
| 6 | 2 | 头长度 `32` |
| 8 | 4 | 载荷长度 `104478` |
| 12 | 4 | 标准 reflected CRC32（poly `EDB88320`，init/final xor `FFFFFFFF`） |
| 16 | 4 | 字数 `52239`，也是模型 ABI 长度检查 |
| 20 | 12 | 保留字段，必须为 0 |

`basic_pitch_flash_map.svh` 是 RTL 地址常量。打包器默认地址与此一致；调整分区必须一起调整 RTL 和镜像构建参数。

## 启动与回退

1. 在 `clk_50m` 域同步 `memory_calibrated && memory_reset_n`，等待校准完成。
2. 拉低已注册的 CS；发送 `03 60 00 00`，用 SPI mode 0 读取头和载荷。50 MHz 时钟、半周期分频 4，SCK 为 6.25 MHz。
3. 在完整字边界暂停 SCK、保持 CS 低，等待现有 DDR 请求 FIFO 接收写入。地址和数据在反压期间保持稳定。
4. 校验 Flash 载荷 CRC；随后通过原有 DDR 端口逐字回读并独立计算 CRC。
5. 成功锁定模型、释放 Flash 接口。`analysis_restart` 不会触发模型重载。模型更新后需要 FPGA 重加载或全局复位。
6. 头错误、Flash CRC 错误、DDR CRC 错误分别记为阶段 1/2/3；此时自动释放原有 `BPN1` UART 装载器。UART 上传仍执行自己的载荷/DDR 双 CRC。

UART 回退等待状态可继续运行原工具：

```sh
python3 tools/upload_cnn_ddr_uart.py \
  --port /dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0
```

成功的 Flash 模型不会被随后收到的 UART 字节改写。分析运行不依赖 PC 上传或 TF 卡内的模型文件。

B138 最后一字的原字段 `[5:2]` 仍是模型状态（`E` 成功）。新增 `[9:8]` 来源：0=Flash 启动中、1=Flash 双 CRC 通过、2=UART 路径、3=片内 ROM 配置。在 UART 回退等待状态 0，`[7:6]` 显示 Flash 失败阶段；UART 工作时恢复为 UART 校验失败阶段。

## 板级接口

| FPGA 端口 | PG484A 引脚 | 板级用途 |
|---|---|---|
| `flash_clk` | L12 | CCLK / MSPI_CLK |
| `flash_cs_n` | T19 | MCS_N |
| `flash_mosi` | P22 | D00/MOSI |
| `flash_miso` | R22 | D01/DIN |
| `flash_wp_n` | P21 | D02/IO2，用户态固定高 |
| `flash_hold_n` | R21 | D03/IO3，用户态固定高 |

完整工程保留 `-use_mspi_as_gpio 1`、`-use_cpu_as_gpio 1`。Flash CS/SCK 由触发器输出，避免状态译码毛刺形成伪 SPI 事务。Flash 上电配置由 Gowin 配置逻辑接管，用户态启动搬运使用同一组物理走线。实际 IO 放置和 Flash 启动验收以构建/实体报告为准。

新增约束仅豁免校准同步器第一采样级，并给 MISO 增加相对 clk50 的 15 ns 输入延迟约束。既有音频、DDR、HDMI 时钟和时序检查没有放宽。当前完整工作站基线的整体时序未闭合；完成 Flash 功能验收不等于整个工程时序闭合。

## 构建与验证

在 `usb_a` 目录：

```sh
# 无硬件操作；SYN 不分配 UserCode。
python3 tools/build_workstation_flash_boot.py --flow syn

# 完整候选必须使用全仓库未占用的新 UserCode。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <八位新编号>

# SPI 物理端口模型、DDR 请求/响应反压、CRC 故障和 UART 回退测试。
python3 tools/test_cnn_flash_boot.py --output /tmp/cnn_flash_tests.json

# 原 CNN 两配置逐层哈希/谱面结果等价回归。
python3 sim/music/run_bp_config_ab.py --simulator verilator --frames 3 --win-len 2048
```

完整构建保留部署 full85 的源文件快照，叠加 Flash 启动模块、Basic Pitch 边界、顶层六个 Flash 引脚和相应约束。冻结的 DDR 仲裁、地址图、显示、延迟 DMA 文件逐一核对 SHA256；没有把工作区其他未提交的开发内容并入发布。

每个结果目录包含 `cnn_model.bin`、模型 manifest、`workstation_inputs.json`、工具退出结果、资源审计。P&R 成功后才生成 `workstation_with_cnn.bin` 和带位流/模型 SHA256 的 `flash_bundle.json`。

可单独构建模型或打包已有位流：

```sh
python3 tools/build_cnn_flash_image.py \
  --mem rtl/music/weights/cnn_ddr_blob.mem --out /tmp/cnn_model.bin \
  --bitstream-bin <Gowin生成的Prj1.bin> --bundle /tmp/workstation_with_cnn.bin
```

仿真覆盖完整部署模型和 1/31/65536 字边界、校准等待、0 延迟与可变延迟 DDR 响应、随机阶段反压、中途复位、空白分区、头字段错误、Flash 载荷损坏、DDR 回读损坏、真实串行 UART 回退。独立 NOR 端点检查 opcode/地址，独立 DDR 端点检查每个写入/回读地址和最终每个字，避免只比较状态机内部变量。

Flash 写入必须把模型分区和位流一起记录。原生 Arora V operation54 用于 `.fs` 位流；operation56（C Bin）用于原始模型 `.bin`/整区打包镜像，CLI 文件参数同样使用 `--fsFile`（此模式忽略 `--mcuFile`）。首次采用 raw-data 操作后须用 RTL 双 CRC 实读确认字节序/偏移；不能仅以 Programmer 的退出码代替自动搬运验收。禁止用 Bulk Erase 操作更新单个分区。实体操作需持有 debugger `2025030317` 的独占锁，写前/重加载后读回确切 UserCode。

验收时保留 UART 只读监听，执行 JTAG Reprogram（不提供 SRAM 位流），要求来源=1 且模型状态=E，再记录多次重加载结果。物理断电/上电与耳机/显示/整曲验收需分别注明是否实际执行。

```sh
# 默认只校验工件与预览命令；实体写入显式加 --program。
python3 tools/deploy_cnn_flash_boot.py <完整结果目录>
```

部署工具先核对板上版本、Flash ID、冻结工件与独占锁。先写模型分区并校验地址零处旧位流仍完好，再写新配置位流；三次 JTAG Reprogram 后只读监听 UART，要求模型来源=Flash 且状态=E。失败时保存原始日志，并尝试恢复原 full85 配置位流。
