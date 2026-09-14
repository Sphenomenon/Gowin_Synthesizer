# 共享显示数据布局 v1.0（P11/P12，阶段 2～3）

以新结果目录中冻结的 `Prj1` 构建输入、`rtl/display_data_layout_pkg.svh`、`display_data_writer.v` 和 `display_data_reader.v` 为准。这是工程内部的 DDR 数据 ABI，采用版本化描述符、双缓冲和 seqlock，不增加 USB 或外部总线协议。阶段 2 导出现有分析结果；阶段 3 已让 HDMI 从共享紧凑块重绘原 dashboard，阶段 4 已让 Push 读取同一提交记录的 64 位摘要；最终 RGB565 framebuffer 和 scanout 仍保留，Push 不直接读取完整三图 payload。

本文件取代此前阶段 1 草案中的错误地址和字段表。原生 DDR 地址单位是 **32 位 word**，byte address = word address × 4。P5 原生地址 `0x00200000` 对应物理 byte `0x00800000`，不是 `0x01000000`。既有结果目录中的旧草案仅作历史记录；此前没有发布本 ABI 的硬件消费者。

## 地址表

所有请求为 BL8，8 个 32 位 word（32 byte）；word 0 为 `data[31:0]`，小端解释。这里的物理 byte 地址不等于 AE350 的 CPU 总线地址。

| 区域 | 原生 word 地址 | 物理 byte 地址 | 大小/说明 |
|---|---|---|---|
| 原 HDMI framebuffer 0 | `0x00000000` | `0x00000000` | 保留 4 MiB，RGB565 1920×1080 |
| 原 HDMI framebuffer 1 | `0x00100000` | `0x00400000` | 保留 4 MiB |
| P5 兼容元数据 | `0x00200000` | `0x00800000` | 32 B，原 writer 保留 |
| 全局已提交记录 | `0x00200008` | `0x00800020` | 32 B |
| bank 0 / 1 提交头 | `0x00200010` / `0x00200018` | `0x00800040` / `0x00800060` | 各 32 B |
| bank 0 / 1 描述符表 | `0x00200020` / `0x00200060` | `0x00800080` / `0x00800180` | 各 256 B，4×64 B |
| bank 0 / 1 payload | `0x00210000` / `0x00220000` | `0x00840000` / `0x00880000` | 各 11,328 B，保留步长 256 KiB |
| AE350 DDR 映射区域 | `0x00400000` 起 | `0x01000000`～`0x017FFFFF` | CPU `0x10000000`～`0x107FFFFF` |

地址依据是当前 `ddr_frame_writer.v`、`ddr3_bist.v`、`gw138k_ahb_ddr.sv` 和上述 package。启动 BIST 只覆盖前 8 MiB，**不覆盖新增区域**。新区域与 AE350/UI 区域不重叠。

## 提交记录（全局及每 bank，8 word）

| word | 字段 | 定义 |
|---:|---|---|
| 0 | magic | `0x44535032`，DSP2 |
| 1 | version_bank_count | `[7:0]` minor=0，`[15:8]` major=1，`[23:16]` bank=0/1，`[31:24]` block count=4 |
| 2 | frame_sequence | 每次导出加 1，从 1 开始，32 位模计数；复位清零 |
| 3 | commit_sequence | `frame_sequence << 1`；写入期间 bank 头置最低位 1，提交后为偶数 |
| 4 | descriptor_base_word | 本 bank 描述符表原生地址 |
| 5 | flags | bit 0 waveform、1 bitmap、2 spectrum、3 metadata 有效，其余 0 |
| 6 | waveform_skipped | 波形采样器累计丢弃的 **sample_valid 次数** |
| 7 | analysis_skipped | 分析采样器累计丢弃的 **sample_valid 次数** |

skipped 不是丢帧数量，也不包含音频 observer 邮箱自身的 drop 计数。waveform、analysis 的 source sequence 独立；同一 display frame 可以引用上一轮 analysis。新的 frame_sequence 表示一次共同显示快照，不能据此声称三图来自同一段原始采样。

## 描述符（每块 16 word，64 B）

描述符 i 地址为 `descriptor_base_word + i*16`。每块都有独立 magic、版本、长度和数据地址。

| word | 字段 | 定义 |
|---:|---|---|
| 0 | magic | `0x44535042`，DSPB |
| 1 | version_type_format | minor、major、type、format 各 8 位，自低到高 |
| 2 | frame_sequence | 四块与提交头一致 |
| 3 | source_sequence | waveform 用采样序号；bitmap/columns 用 analysis 序号；metadata 用 display frame 序号 |
| 4 | sample_rate_hz | 48000；metadata 为 0 |
| 5 | window_trigger | `[15:0]` 源采样长度，`[23:16]` 配置种类，`[31:24]` 超时样本数的 log2 |
| 6 | valid_length | 下表逻辑元素数，无效分析块为 0 |
| 7 | flags | bit 0 有效，其余 0，不混入 memory status |
| 8 | payload_base_word | 原生 DDR word 地址 |
| 9 | payload_words | 分配的 32 位 word 数，无效块仍占相同长度 |
| 10 | skipped_samples | 对应采样器计数，metadata 为 0 |
| 11 | display_gain | bitmap 的增益指数，其余 0 |
| 12 | aux0 | bitmap 高低 16 位各为 256；spectrum 高 16 位=853、低 16 位=2 |
| 13 | aux1 | spectrum 对数高度上限 224，其余 0 |
| 14 | reserved | 0 |
| 15 | bank_header_word | 用于读取前后校验的 bank 提交头地址 |

配置种类：0=无窗/无触发，1=现有六极平滑触发（仅触发信号平滑，波形本身不滤波），2=2048 点 periodic Hann。waveform `window_trigger=0x0D010200`（512 点、8192 样本超时）；bitmap=`0x00000800`；spectrum=`0x00020800`；metadata=0。字段描述采样器配置，不包含本次实际触发原因或时间戳。

## 数据块

| type=format | 内容 | bank 内 word 偏移 | payload_words | valid_length |
|---:|---|---:|---:|---:|
| 1 | waveform：有符号 Q1.31，每 word 一个样本 | `0x0000` | 512 | 512 |
| 2 | 李萨如：现有 MID/SIDE 256×256 一位位图 | `0x0200` | 2048 | 65536 像素 |
| 3 | 频谱：现有 512 个对数列，每列 L8、R8 | `0x0A00` | 256 | 512 列 |
| 4 | 效果及状态元数据 | `0x0B00` | 16 | 16 word |

bitmap 线性地址 `y*256+x`，每 BL8 按 bit 0～255 打包；包含现有增益和 MID/SIDE 映射，**不是原始 I/Q 或 L/R 样本**。spectrum 每列低 8 位为 L、高 8 位为 R，每 word 两列、每 BL8 十六列；输入 FFT bin 2～853 经现有映射形成 512 个对数列，**不是线性 FFT bins**。先共享已有紧凑结果，后续若消费者需要原始 I/Q 或频谱复数值，再新增 format，不能改变现有字段含义。

metadata word 0～7 的布局沿用 P5 原 256 位记录：

| word | 内容 |
|---:|---|
| 0 | 帧开始时的 memory status：bit 0 calibrated、1 BIST done、2 BIST failed、3 front valid、4 fetch/arbiter fault、5 underrun、6 memory PLL locked、7 video locked |
| 1 / 2 | waveform skipped / waveform source sequence |
| 3 / 4 / 5 | waveform snapshot status / voices mask / peak |
| 6 | `[2:0]` effect mask，`[8:3]` effect order，其余 0，沿用 P10 编码 |
| 7 | P5 magic `0x44495350`，DISP |
| 8 / 9 | analysis source sequence / skipped |
| 10 | `[31:16]` 左声道 peak，`[15:0]` 右声道 peak |
| 11 / 12 / 13 | image gain / 四块 valid flags / 48000 Hz |
| 14 / 15 | 0 |

status/voices/peak 属于波形捕获末尾；effect mask/order 和 memory status 在 renderer start 锁存。这些字段组成同一显示快照，但不是同一音频采样时刻的原子观测。P11 在导出开始锁存完整记录。旧 P5 固定地址仍由原 writer 在帧尾写入，长时间 DDR 背压下其 waveform 计数可能已更新；需要帧一致性的消费者应使用新 descriptor，不将旧 P5 固定地址当作本协议的提交头。

## 写入、提交与读接口

writer 在 memory UI 100 MHz 域复用原有 DDR writer 槽位：`req_valid/req_ready, req_addr[28:0], req_wdata[255:0]`，阻塞时保持请求和数据。由单请求寄存桥保存请求，真实 DDR 接受时 ACK 像素 writer，下一拍 ACK 共享 writer；原 scanout 优先级、CPU/writer 轮转及 read response tags 保留。初始化清零全局头和两个 bank 头，完成后才允许 renderer start。

每帧依次执行：

1. renderer start 冻结原有波形与 analysis front bank，锁存卡片状态。
2. 下一 UI 周期获取完整元数据；目标 bank 头写 odd generation。
3. 复用 RAM 读端口导出三个 payload；分析未就绪时位图/列全零且 valid length=0。
4. 写 metadata、四个描述符，再写目标 bank 的 even 提交头。
5. 最后写全局 even 提交记录，释放导出阶段，继续原 HDMI 光栅渲染。

bank 每次交替，数据端无新的 CDC、无 audio ready 信号。背压只延长显示保持时间，采样器沿用已有双缓冲/丢弃观察样本的逻辑。每帧 365 个 BL8 写请求，合计 11,680 B；冷启动另有 3 个 BL8 清零请求。66,560 个源元素各用三个 UI 周期读取，加写入约 2.00 ms，不含 DDR 背压和原 framebuffer 渲染；60 帧/秒约增加 0.701 MB/s。

reader 接口沿用 `read_valid/read_ready/read_addr[28:0]` 与 `read_rsp_valid/read_rsp_data[255:0]`。P12 的 HDMI reader 已实例化，并遵循以下快照规则；后续 Push 或外部消费者也不能仅锁存 bank 号后无限期读取：

1. 读取全局记录并检查 magic/版本/有效位，取得 frame sequence 和 bank。
2. 读取 bank 头，要求 generation 为偶数且与全局 frame/descriptor 匹配。
3. 把所需描述符和紧凑 payload 读入本地工作缓存。
4. 再读同一 bank 头，要求头字段/序号未变且仍为偶数；满足后才交换本地显示缓存。
5. 不满足则丢弃这次工作缓存，继续显示上次通过校验的本地缓存。

双 bank 本身不能保护任意慢的 Push 读者：第二次复用会覆盖旧 bank，前后 seqlock 校验负责检测。P12 HDMI reader 只在完整校验后发布缓存；P13 Push 读取的是该提交事件携带的摘要，不从尚未校验的 DDR 数据发送 USB 像素。读者不阻塞写者，也不为每个消费者复制完整 HDMI framebuffer。复位时丢弃旧快照；必须在计数回绕前完成一次快照读取。这里保证 DDR 数据帧一致性；全局提交先于 HDMI framebuffer 完成，不能当作“已上屏”通知。

## 阶段边界

目前 P12/P13 HDMI 使用共享 DDR 数据块装载到本地显示缓存后重绘，逐像素仿真检查视觉内容与 P10 原本地 RAM 渲染一致。P13 已把 64 位 committed summary 跨到 USB 48 MHz，Push 屏幕在原 frame_capture 时锁存共享 effect mask；USB-A 线协议和现有 448 位反馈邮箱未改。未来自制屏可复用描述符，暂不添加传输层。现有完整 RGB565 framebuffer 仍生成并扫描，因此不宣称已经减少 framebuffer 带宽；P12 为 HDMI reader 缓存增加 6 个 BSRAM，P13 摘要 CDC 不增加 BSRAM。实际刷新节奏、输入到声音/画面的延迟仍须实体测量。
