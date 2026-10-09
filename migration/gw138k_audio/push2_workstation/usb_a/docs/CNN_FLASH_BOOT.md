# CNN 权重持久化与 Flash→DDR 启动

完整工作站把 FPGA 配置位流和 Basic Pitch 模型分别保存在板载外部 Flash。默认构建采用 `serial` 兼容传输：CPU 完成 DDR/音频/UI 启动自检后，片内 Flash 控制器先完整读取并校验模型，再重新读取、产生内部 `BPN1` 8N1 数据流，交给 full85 原封不动的模型解析器和 DDR 客户端。它使用片内连线，不经过 PC、USB 或外部串口；115200 波特率下模型装载约 9 秒，另加校验和 DDR 回读时间。

此前 `direct` 方案仍保留为实验路径：直接 SPI→DDR、载荷 CRC、DDR 回读 CRC。0x95 完整工程虽然 clk50 收敛且正常从 Flash 配置，实体原有 UART 路径也停在 DDR 回读，CPU DDR/UI 自检出现失败；因此 0x95 没有提升为 LATEST。独立 0x96 SRAM 探针完整读出 Flash 模型并通过本地 RAM CRC，证明 Flash 接线、字节序和载荷有效；探针不代表完整工作站或 DDR 已验收。0x98 SRAM 探针进一步验证实际 115200 波特率的内部 BPN1 传输和原解析器，完整模型本地 RAM 回读 CRC 同样通过。

默认 `serial` 方案保留 CNN、原模型解析器、DDR16 端口、CDC FIFO、命令缓冲的完整源文件和实例层级。空白/非法头或首遍载荷 CRC 错误时，模型解析器尚未接收任何数据，自动切回外部 UART。第二遍发生变化或 DDR 校验错误则显式失败，需要全局复位后恢复；不会把部分模型当成成功。

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

## direct 路径的启动与回退

1. 在 `clk_50m` 域同步 `memory_calibrated && memory_reset_n`，等待校准完成。
2. 拉低已注册的 CS；发送 `03 60 00 00`，用 SPI mode 0 读取头和载荷。50 MHz 时钟、半周期分频 4，SCK 为 6.25 MHz。
3. 在完整字边界暂停 SCK、保持 CS 低，等待现有 DDR 请求 FIFO 接收写入。地址和数据在反压期间保持稳定。
4. 校验 Flash 载荷 CRC；随后通过原有 DDR 端口逐字回读并独立计算 CRC。
5. 成功锁定模型。`basic_pitch_flash_io_guard` 仅在注册 CS 低时驱动共享 CLK/MOSI/CS/IO2/IO3；等待 DDR、复位、校验 DDR 和完成后均三态释放物理接口，由已有上拉/下拉维持闲置电平。`analysis_restart` 不会触发模型重载。模型更新后需要 FPGA 重加载或全局复位。
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
| `flash_wp_n` | P21 | D02/IO2，事务内高、闲置三态 |
| `flash_hold_n` | R21 | D03/IO3，事务内高、闲置三态 |

完整工程保留 `-use_mspi_as_gpio 1`、`-use_cpu_as_gpio 1`。内部 Flash CS/SCK 由触发器输出，物理输出使用 CS 作为总线所有权；IO2/3 闲置时不能固定驱动，以便配置/其他主机使用。避免状态译码毛刺形成伪 SPI 事务。Flash 上电配置由 Gowin 配置逻辑接管，用户态启动搬运使用同一组物理走线。实际 IO 放置和 Flash 启动验收以构建/实体报告为准。

新增约束仅豁免启动就绪同步器（direct 为校准同步器）的第一采样级，并给 MISO 增加相对 clk50 的 15 ns 输入延迟约束。既有音频、DDR、HDMI 时钟和时序检查没有放宽。当前完整工作站基线的整体时序未闭合；完成 Flash 功能验收不等于整个工程时序闭合。

## 构建与验证

在 `usb_a` 目录：

```sh
# 无硬件操作；SYN 不分配 UserCode。
python3 tools/build_workstation_flash_boot.py --flow syn

# 完整候选必须使用全仓库未占用的新 UserCode。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <八位新编号> --transport serial
# 当前修复候选采用标准路由，并收紧原缓存 RESET cone 的预算。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <另一新编号> --route-option 0 --tighten-cache-reset

# 实验性增量候选：实际 0x93 参考复用产生 12270 条未布通网络，当前发布使用全量 P&R。
# 仍重新综合，仅把已验证 full85 的路由作为 P&R 参考。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <另一新编号> --incremental-baseline

# SPI 物理端口模型、DDR 请求/响应反压、CRC 故障和 UART 回退测试。
python3 tools/test_cnn_flash_boot.py --output /tmp/cnn_flash_tests.json

# 默认兼容传输：完整首遍校验、第二遍变化、实际波特率、UART 回退、DDR CRC。
python3 tools/test_cnn_flash_serial_boot.py --output /tmp/cnn_flash_serial_tests.json

# 小型 Flash/local-RAM 探针的离线综合；无 UserCode、无硬件操作。
python3 tools/build_cnn_flash_probe.py --flow syn --transport serial --output <新目录>
# 探针全构建需新编号，仅用于临时 SRAM；不允许作为完整工作站固化。
python3 tools/build_cnn_flash_probe.py --flow all --transport serial --user-code <新编号> --output <新目录>

# 离线部署/回滚故障测试：使用已完成候选的真实 hash，所有硬件 I/O 用测试替身。
python3 tools/test_cnn_flash_deploy.py --build <完整结果目录>

# 原 CNN 两配置逐层哈希/谱面结果等价回归。
python3 sim/music/run_bp_config_ab.py --simulator verilator --frames 3 --win-len 2048
```

完整构建保留部署 full85 的源文件快照。默认 serial 只叠加 Flash 传输模块、模型输入连线、B138 来源/错误字段、顶层六个 Flash 引脚与约束；CNN/DDR 客户端源文件不变。`--transport direct` 才叠加此前的模型内存端口方案。可选增量 P&R 会复制并记录已验证 full85 `.pr` 的 SHA256，仍运行全新 RTL 综合；参考文件和所有输入在构建前后复核，不覆盖原候选。冻结的 DDR 仲裁、地址图、显示、延迟 DMA 文件逐一核对 SHA256；没有把工作区其他未提交的开发内容并入发布。

可选 `--retime-cache-read` 把权重缓存的地址有效性掩码与 BSRAM 数据同拍寄存，再组合选择有效输出，维持原来一拍读取延迟和越界读零。统计用八路固定索引计数代替动态数组索引，CNN 算术和计数语义保持一致。独立测试与冻结 full85 逐周期比较 1/31/7488 字缓存、随机反压/复位/越界地址，以及 10,000 周期统计计数；CNN 三帧回归的六层哈希和谱面结果一致。构建命令可加 `--retime-cache-read`，回归命令为 `python3 tools/test_cnn_cache_read_retime.py`。

每个结果目录包含 `cnn_model.bin`、模型 manifest、`workstation_inputs.json`、工具退出结果、资源审计。P&R 成功后才生成 `workstation_with_cnn.bin` 和带位流/模型 SHA256 的 `flash_bundle.json`。

可单独构建模型或打包已有位流：

```sh
python3 tools/build_cnn_flash_image.py \
  --mem rtl/music/weights/cnn_ddr_blob.mem --out /tmp/cnn_model.bin \
  --bitstream-bin <Gowin生成的Prj1.bin> --bundle /tmp/workstation_with_cnn.bin
```

仿真覆盖完整部署模型和 1/31/65536 字边界、校准等待、0 延迟与可变延迟 DDR 响应、随机阶段反压、中途复位、空白分区、头字段错误、Flash 载荷损坏、DDR 回读损坏、真实串行 UART 回退；三态适配器的独立其他主机激励检查 CLK/MOSI/CS/IO2/IO3 闲置释放与无争用，全部 SPI/DDR 测试同时穿过物理三态适配器。独立 NOR 端点检查 opcode/地址，独立 DDR 端点检查每个写入/回读地址和最终每个字，避免只比较状态机内部变量。

Flash 写入必须把模型分区和位流一起记录。原生 Arora V operation54 用于 `.fs` 位流；operation56（C Bin）用于原始模型 `.bin`/整区打包镜像，CLI 必须同时传 `--fsFile cnn_model.bin --mcuFile cnn_model.bin`：前者满足 CLI 的文件检查，后者提供原始字节；单传任一参数会导致无数据/零长度。该调用已用 operation66 与等价的文本 `.data.fs` 交叉校验实际 Flash 字节。镜像工具还输出逐字节等价的 `.data.fs` 容器，官方 `--filestransform 1` 还原结果与原始镜像一致。首次采用 raw-data 操作后须用 RTL 双 CRC 实读确认字节序/偏移；不能仅以 Programmer 的退出码代替自动搬运验收。禁止用 Bulk Erase 操作更新单个分区。实体操作需持有 debugger `2025030317` 的独占锁，写前/重加载后读回确切 UserCode。

验收时保留 UART 只读监听，先执行 SRAM Erase 仅清除易失配置，再执行 JTAG Reprogram（不提供 SRAM 位流），先等待实际目标 UserCode 与正常已配置状态（DONE bit13=1，配置错误 bits0..3 和 Auto_Boot 失败 bits4/9 必须为 0；本板正常值 `0x26020`。直接 SRAM 下载曾出现 `0x26230`，其 DONE 为 1 但自动启动失败位仍置位，不能作为 Flash 启动成功证据），再清空 UART 缓冲、持续接收两秒排空 FTDI 硬件旧包后，重新清空缓冲并读模型状态，要求来源=1 且模型状态=E，再记录多次重加载结果。物理断电/上电与耳机/显示/整曲验收需分别注明是否实际执行。

```sh
# 默认只校验工件与预览命令；实体写入显式加 --program。
python3 tools/deploy_cnn_flash_boot.py <完整结果目录>
```

部署工具先核对原 20 ns clk50 时序、full85 原本满足频率要求的 DDR/CPU/视频各时钟是否出现新退化、板上版本、Flash ID、冻结工件与独占锁。clk50 未闭合或原本通过的时钟退化时默认拒绝实体写入；`--allow-clock-regression`（旧名 `--allow-clk50-open`）仅用于临时的启动诊断，必须恢复基线且不得据此提升 LATEST。先写模型分区并校验地址零处旧位流仍完好，再写新配置位流；三次 SRAM Erase + JTAG Reprogram 后只读监听 UART，且先等待/核对目标 UserCode 和已配置状态；不在 FPGA 配置完成前解释 DDR/UART 报文，要求模型来源=Flash 且状态=E。失败时保存原始日志，并尝试恢复原 full85 配置位流；等待其 UserCode/配置状态通过后，单独通过 UART 恢复原 full85 的易失模型并执行启动检查。回滚上传在独立证据字段里记录，不计入新功能 Flash→DDR 验收。
