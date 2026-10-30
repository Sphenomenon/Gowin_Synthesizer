# 原生 TF 扇区入口：线级验证检查点（2026-10-30）

本检查点完成 M03 入口审计后的第一个独立源码阶段：新增未被任何工作站 profile 选择的原生 SD sector/session owner，修复单次请求重复 CMD17、255-byte 尾等待、加速后 token 耐心缩短及缺失 R1 被默认零值混淆的问题。**没有接入文件播放，也没有取消当前 TF 播放的 DDR 中转。M03、M01 及整机验收仍未完成。** 前置分析见[入口审计](WORKSTATION_TF_STREAMING_INGRESS_AUDIT_20261030.md)。

## 来源与选择边界

隔离实现以审计提交 `728eac7` 为起点。原生模块位于 `rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv` 与 `workstation_tf_spi_session.sv`；出处、GPL-3.0 许可位置、冻结输入及新文件 SHA-256 在同目录 `workstation_tf_sd_sector_reader.provenance.json`。新 session 保留原文件全部说明，仅增加模块名、声明及实际 R1/ACMD 响应捕获的 valid 保持位，并清理一处原尾空格；校验器按精确锚点验证其与冻结原文件之间的全部差异，只用于核对已维护源码，不生成生产 RTL。

原始 `tang_mp3/vendor/tf_sd_spi_sector_reader.v`、`tf_spi_session.v`、`tang_mp3/sd/tf_sd_file_reader.v`、`tf_sd_audio_pcm_player.v`、所有 baseline、原始 manifest、构建器与 profile 均未修改。运行器校验四个原输入的固定哈希。当前文件 reader 仍实例化原 `tf_sd_spi_sector_reader`；resource/native runtime 的已选文件集合未添加新模块。原入口与实验模块保持不同名称，没有别名替换，也未新增生产构建入口。

本轮固定验证身份：

```text
native-tf-sd-sector-wire-v1-37cc187fb7b60c93
source_set_sha256: 37cc187fb7b60c937977fd4630a6319b938266453fb74b508ef9dff17d741916
sector sha256: 8f1961c951f3622ed6253bf0b1c42879f5b1950bc6a9e4a5ef40b5a01b546110
session sha256: 704e9b62caa4ef79c01f1d2b4c1c61b2e2bd55f93c83ae90bb573c9e71c0a6c8
```

完整源码哈希、配置、命令、结果及负例日志保存在 [JSON 证据](workstation_task_20261030/tf_sd_sector_native_wire.json)。仿真程序、编译输出与临时突变文件保存在 checkout 外的 cache，不作为生产输入。

## sector/session 契约

- `card_stat=8` 时仅接受 `start` 上升沿，接受时锁存扇区参数。忙时上升沿丢弃，保持高电平跨过完成边界也不追加请求；下一次请求须先释放再重新拉高。`card_type` 与状态 0—9 沿用原含义，新增终态 `FAULT=10`。
- 一次接受请求只有一个 CMD17。SDHC 使用扇区号，SDv2/SDv1 使用原有 32-bit 字节地址转换。收到有效 R1=0 与 FE token 后才输出 `raddr=0..511` 的 512 个字节；后续两个 CRC 字节仅排空，不输出给消费者。
- 接口没有字节背压，消费者必须在开始前预留完整 512-byte 扇区容量；不能通过停顿实时采样等待 SD。本阶段没有新增播放/分析消费者。
- 一个 CS 高的字节时钟释放总线，随后完成会话；删除旧 255-byte CS 低尾等待。`done` 单周期，仅表示该扇区会话已完成，不能代替 PCM EOF 或物理输出完成。
- session 的 `cmdrsp_valid/acmdrsp_valid` 仅在实际捕获 bit7=0 的 R1 字节时置位，保持至会话结束/复位。sector 初始化、数据转发与成功判定都要求真实 valid；缺失 R1、非零 R1、丢 token 均不能报告扇区成功。
- 读错误锁存 `read_error`，`read_error_code=1` 表示有有效成功 R1 但没有 token，`2` 表示无有效 R1 或错误 R1。保持 FAULT、CS 高、不自动重发 CMD17、不接受新 start，直到整个 owner 显式复位。底层会话仍按有界响应窗口、token 窗口及数据/尾部长度退出，失败不会成为无限读等待。
- 拉低 `rstn` 立即撤销 SPI 会话及数据输出，并重新初始化卡。线级回归覆盖等待 token 和已接收 73 个 payload 字节时复位、重新初始化、读取另一扇区，防止旧数据/旧完成泄漏。未来整合仍须由媒体 owner 的取消/代次协议包围这个复位边界。

默认 source clock 为 50 MHz，init divider=100，read divider=12。保持 `f_SPI=f_clk/[2(divider+1)]`；初始时钟须由调用方保持在卡初始化要求内。有效 divider 为 2—255，FAST=0 继承 init；拒绝 1、256 等会被旧 8-bit 计数器钳制/截断的配置。`TOKEN_WAIT_CLOCKS=8,320,000`，转换为向上取整的 SPI byte 数，计数溢出和零窗口均拒绝：

| read divider | 默认 token bytes | token 窗口下界（50-MHz clocks） | 配置耐心 |
| --- | ---: | ---: | ---: |
| 12 | 40,000 | 8,320,000 | 166.4 ms |
| 6 | 74,286 | 8,320,032 | 166.4 ms |
| 3 | 130,000 | 8,320,000 | 166.4 ms |
| 2 | 173,334 | 8,320,032 | 166.4 ms |

这只是保留既有 wall-time 耐心，未宣称测得卡的服务上界或音频所需持续吞吐。

## 验证结果

`run_workstation_tf_sd_sector_wire.py` 的卡模型只连接公开 SPI 和 sector 端口，按 SCK 边沿收 MOSI、发 R1/token/payload/CRC；执行实际 CMD0、CMD8、CMD55/ACMD41、CMD58、CMD16 或 SDv1 CMD1 初始化。没有强制 DUT 状态、层次寄存器赋值或 session stub。

21 个执行项全部符合预期：10 组正向配置、5 个行为突变/历史负例、6 个无效配置拒绝。八组完整矩阵包含 div12/6/3/2、FAST=0、div255，以及 SDv2/SDv1 字节寻址。每组覆盖即时和迟到 token、地址输入在接受后改变、忙时请求与跨完成保持 start、丢 token、错误 R1、无 R1 但随后发送 FE+完整数据、两类在途复位及重启。共核验 42 个完整成功扇区和 16 次中途取消；每个成功请求严格一个 CMD17、512 payload、两个 CRC、零额外 CS 低尾字节及至少八个 CS 高释放时钟。

两组生产窗口测试在 div12/div2 分别等待接近 40,000/173,334 SPI 字节的 token，仍各自仅发一个 CMD17；接受至完成分别为 8,430,025 与 8,345,427 source clocks。它们证明窗口按真实时钟保留，不能当作健康卡每个扇区都可如此停顿的音频预算。

负例有明确检出点：

| 负例 | 检出结果 |
| --- | --- |
| 固定 token=40,000，div2 生产窗口 | 迟到 token 读取失败，无法冒充成功 |
| 恢复 read stopcycle=255 | 线级检测 `tail=255` |
| payload 地址偏一 | 第一个字节地址比较失败 |
| 冻结历史 controller＋真实原 session | 一次请求实测 `CMD17=2, CRC=4, tail=510, release=2`；拒绝 |
| 绕过实际 R1-valid 的数据/完成门 | 无 R1 仍错误输出 512 字节；终态断言拒绝 |

历史负例只在 cache 中增加模块名/测试端口兼容，并保持请求地址稳定、留出原 token 前四字节空隙，以测量其重复传输；不更改原控制器、原 session 或产品输入。其结果补足前置审计的 controller stub 范围。

额外运行 `sim/test_current_workstation_sources.py`，10 项通过；原 `tb_tf_wav_formats`、`tb_tf_wav_chunk_parser` 通过，8/16/24/32-bit、mono/stereo、RIFF chunk 路径未收窄。它们仍是原 WAV 解码链回归，不代表新 sector 已与文件/解码器联合。Verilator lint 可展开两个新模块；保留原 session 的两处 3-bit 零扩展为 4-bit 的既有 width 警告，未屏蔽或修改 vendor 字节。未执行综合、P&R、板卡操作、SRAM/Flash。

父级在冻结的隔离 checkout 独立重跑全部 21 项，输入身份及每项指标与原结果一致；合入主 checkout 后再次逐项核对 9 个实际输入，并重跑来源边界 10 项通过。独立证据见 [tf_sd_sector_native_wire_parent.json](workstation_task_20261030/tf_sd_sector_native_wire_parent.json)。所有工作站 profile 仍选择原读取 owner。

复现：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_sd_sector_wire.py \
  --output /tmp/workstation_tf_sd_sector_wire_fresh
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

## 后续接入条件与回滚

下一阶段须显式适配实际 file reader/热插拔/取消 owner，检查源码选择与身份，再验证 FAT 元数据读取/缓存、所有既有 WAV 格式、输入停顿和 PCM FIFO 预算。CRC 仍未校验，不能由这个会话成功推断中途拔卡或数据完整性；初始化重试保持旧有行为，外层仍需卡故障看门狗。卡服务边界、实际吞吐、无 DDR 的请求证据、双采样率预填充/欠载、分析慢端隔离、EOF 最后物理帧确认、同配置资源净变化及 P&R/实板均另行验证。

本阶段回滚只需撤销新增 owner、provenance、fixture/runner 与本报告/JSON；没有改变 profile 或部署状态。后续真正选择新 owner 时须用新的候选身份和明示来源，不能沿用本离线检查点作为接受位流。
