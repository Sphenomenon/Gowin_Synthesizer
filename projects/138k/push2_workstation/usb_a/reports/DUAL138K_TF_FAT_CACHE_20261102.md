# Task3：FAST12 供给诊断与单扇区 FAT cache

本阶段以 `a070a620` 的 CRC 阶段为来源基础，在维护中的 TF file/native/runtime 三层增加默认关闭的 `FAT_SECTOR_CACHE`，并实现独立 512B FAT 元数据缓存。没有提高 SPI 时钟、扩大预填或音频 FIFO，没有复用音频数据 buffer，也没有全量重写 reader。新 DIRECT 的显式 `VERIFY_DATA_CRC=1`、`FAT_SECTOR_CACHE=1`、top 逆适配、来源锁和整机候选由协调者另行建立；本报告的子系统证据不代表整机候选已通过。

## 实测根因与变化

50 MHz、FAST12 的真实 SCK 为 `50MHz/[2×(12+1)] = 1.923077MHz`；每字节固定 208 clocks，裸上限 240384.6 B/s。旧 file owner 在每簇末尾完整重读 FAT 扇区。本测试磁盘为 1 sector/cluster、碎片链 stride=4，旧链实际出现 61 次数据读取和 61 次 FAT 读取，后者全部重复 LBA1。数据与元数据共用同一个 SPI owner，无法并行抵消这些字节。

原链的 cache 外仪器化副本没有改变业务行为，在独立目录复现了 7790 帧后的欠载，吻合历史实际 wire 失败；没有把“正确报出 underflow”当作供给成功。

| 项目 | 未缓存的实际 wire | 启用缓存后的实际 wire |
| --- | --- | --- |
| SPI payload 字节间隔 | 固定 208 clocks | 固定 208 clocks |
| 单 CMD17 请求间隔 | 110858 clocks | miss 保持原协议；命中省略 FAT CMD17 |
| 数据请求间隔 | 固定 221716 clocks | 110861 clocks ×84、221716 clocks ×2 |
| 长片段数据/FAT读取与命中 | 欠载前 61/61，均重读 FAT LBA1 | 完整 87/2，85 次命中，FAT LBA1→2 |
| 文件数据供给 | 稳态 115463.0 B/s | 有限片段 225671.9 B/s |
| 48k stereo16 所需 | 192000 B/s，存在永久差额 | 本测试片段满足要求 |
| 播放 oracle | 3072 帧预填后 162.294 ms、7790 帧欠载 | 48k、44.1k 各完成 11000 帧，再完成新任务 97 帧 |

原链 byte FIFO 峰值只有 1 byte，decoder byte stall 为 0；只有启动边界 1 拍的不可发起状态。因此主要问题是重复 FAT 字节，不是 decoder 吞吐或持续 sector_allow 阻塞。缓存后，48k/44.1k 的 byte 峰值为 830/3002，PCM 峰值均为 4096，出现正常 decoder 背压；所有有界队列保持容量内、完整 PCM oracle 和 LAST 一致、无供给欠载。统计 `min_PCM=1` 包含自然 EOS 的尾部排空，不能称为稳态最低余量。

长 WAV 实际长 44080B，共 **87** 个数据扇区；前期 86 扇区预算是估算，本报告以实际文件和命令计数纠正。每个长场景真实 card CMD17 共 94 次：挂载 3、首曲数据 87、首曲 FAT 2、新任务数据与 FAT 各 1。命中减少实际 SPI 命令，不是用缓存命中计数替代真实传输证据。

## 有效位、生命周期和来源链

缓存以精确 32-bit FAT LBA 作 key，只缓存 `READ_A_FILE` 的 FAT 元数据。每次 miss 开始即撤销旧有效位；必须严格收到 0..511 的全部字节，并由原 CRC-enabled sector owner 在 CRC/CS 释放后给出真实成功 `read_done`，才允许发布。启用 cache 而未启用 CRC、或 cache 参数取非法值，均由真实 native/file 配置检查拒绝。

命中使用同步 RAM 和 file owner 的本地 metadata-completion pipeline，不伪造 sector `read_done`，不新增 SD controller。既有 FAT16/32 entry 掩码、实际碎片链跟随、cluster 范围、精确链长和最后 EOC 校验保留。STOP、新任务、pending 生命周期操作、错误和 owner reset 撤销有效位、填充和 lookup 资格，迟到数据、done 或本地结果不能重新授权。无 SPI 事务的命中 lookup 可直接取消，不等待不存在的 transport ACK。

新 `workstation_tf_fat_sector_cache_v1.adaptation.json` 精确逆回上阶段 file/native/runtime 和原 CRC verifier 的字节，再执行原 CRC 验证主体。旧 CRC manifest 的 SHA256 仍为 `230b9436cab1b56311ef757f548ccf12705ff94ca7381b0e718aedfa7b0d17f4`；两份更早 manifest、vendor、原 basis/anchors 没有改写。新链重建仅用于验证，不作为生产输入回退。旧 sector/file wire runner 及旧 CRC provenance unittest 只在显式 `--direct-fat-cache-source-adaptation` 时接受此链；默认旧 verifier 继续拒绝新来源。

## 验证与真实资源

所有相对证据路径均位于 `~/.cache/gw138k-task3-20261101/`。探索中的 TB 调度修订及最初工具动态库配置失败日志保留，没有改写历史证据。

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 新来源链 | 3 tests、15 个内存来源漂移负控全部拒绝 | `fat-cache-provenance-v1.json` |
| 原 CRC 链的显式新入口 | 3 tests、12 个内存漂移负控全部拒绝 | `fat-cache-prior-crc-provenance-v1.json` |
| cache local | 全 128 word 内容/key、完整发布、短/乱序拒绝、取消/迟到/复位隔离；1 正例、5 个源码负控、2 个配置拒绝 | `fat-cache-local-v2/verification.json` |
| 旧默认 file | FAT16、FAT32、空目录、非法曲目、两种 transport failure，共 6 场景；cache/CRC 默认关闭 | `fat-cache-default-file-retention-v1/verification.json` |
| 新真实 wire | 7 场景、3 个源码负控全通过 | `fat-cache-wire-final-v1/verification.json`、`verification.seal.json` |
| 主线程独立复跑 local | 1 正例、5 源码负控、2 配置拒绝全通过 | `fat-cache-local-root-review-v1/verification.json` |
| 主线程独立复跑 wire | 两种长采样率、CRC_bad_FAT_fill、STOP_during_cache_lookup，共4场景通过；未重跑其他 wire 场景或3个 wire 负控 | `fat-cache-wire-root-review-v1/verification.json` |
| 实际 Gowin helper 综合 | 输出接 top、真实 VG/HTML 及连接 census | `fat-cache-gowin-synth-v2/verification.json` |

7 个 wire 场景包括两种长采样率、FAT16/FAT32 stride260 跨 key 碎片、错误 CRC 的首 FAT 填充、FAT payload 第511字节时 STOP、cache lookup pending 时 STOP。实际 SPI/FAT/WAV/PCM 链保留 FAST12=12、4096-byte/4096-frame 队列和3072帧预填；独立 50MHz 相位累加器持续产生音频 deadline。TB 的 token wait=1000 clocks、watchdog=500000 clocks 只用于有限数字卡场景，生产默认超时不变，不能据此声称通过生产最大 token 停顿。

错误 CRC 不发布 cache line，必须产生终态失败而不能 EOF；显式 owner reset/remount 后没有自动播放。STOP 填充覆盖完整 `512+2` 字节及 CS 高 8 clocks 排空后唯一取消成功；STOP lookup 确认没有真实 SPI 所有权并本地取消。每次恢复均需显式新任务，真实重读 FAT 并核对 97 个 PCM 帧。错 LBA 比较、提前发布有效位、忽略失效三个源码副本负控分别由具体功能断言拒绝，无 timeout 充数。seal 独立解析全部 10 个实际 VVP，每例 native/file/sector/session/CRC/cache 等 11 类 module 各唯一，并核对真实 card CMD17 总数。

独立综合使用 Gowin V1.9.12、GW5AST-LV138PG484AC2/I1 C、20ns TF clock。维护 helper 字节被原样复制至独立 cache，所有输入/输出通过 wrapper 接 top；独立 VG census 确认唯一 cache、唯一 SDPB，RAM 的 32 个 DO 位均到达 top OBUF，未因未使用输出而剪掉。

| 实际独立综合资源 | 数量 |
| --- | ---: |
| SDPB primitive / synthesis-equivalent BSRAM | 1 / 1 |
| FF（DFFCE） | 70 |
| LUT / INV | 35 / 1 |
| ALU | 50 |
| SSRAM | 0 |

HTML utilization 把 INV 计入 LUT-equivalent 时为 36，不能与 35 个 LUT primitive 混用。本阶段没有 P&R，`physical_routed_BSRAM_count=null`；独立 helper 综合不是整机 M 资源增量或完整时序结论，也没有新位流身份。

## 文件及封存

改动共 16 个代码/契约/测试文件及本报告。以下均相对 `projects/138k/push2_workstation/usb_a/`；协调者负责后续提交、推送、`task3.md` 和新整机候选。

| 文件组 | 文件 |
| --- | --- |
| 默认关闭的三层参数与集成 | `rtl/tf_audio/storage/workstation_tf_file_reader.sv`、`rtl/tf_audio/workstation_tf_direct_native_v1.sv`、`rtl/tf_audio/workstation_tf_direct_runtime_service.sv` |
| 新 cache、独立来源链和契约 | `rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv`、`rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.adaptation.json`、`rtl/tf_audio/storage/WORKSTATION_TF_FAT_SECTOR_CACHE_V1_CONTRACT.md` |
| 新验证链及旧链显式入口 | `tools/workstation_tf_fat_cache_provenance.py`、`tools/workstation_tf_sd_crc16_provenance.py` |
| 来源测试 | `sim/test_workstation_tf_fat_cache_provenance.py`、`sim/test_workstation_tf_sd_crc16_provenance.py` |
| 旧默认 runner 显式入口 | `sim/tf_audio/run_workstation_tf_sd_sector_wire.py`、`sim/tf_audio/run_workstation_tf_file_reader_wire.py` |
| 新 local 测试 | `sim/tf_audio/tb_workstation_tf_fat_cache_local.sv`、`sim/tf_audio/run_workstation_tf_fat_cache_local.py` |
| 新 wire 测试 | `sim/tf_audio/tb_workstation_tf_fat_cache_wire.sv`、`sim/tf_audio/run_workstation_tf_fat_cache_wire.py` |

综合封存为 `fat-cache-local-stage-final-seal-v1.json`，SHA256 `52a0d0906ff4ef92e50670a031aa1a0cecb2b366e6d4f6cadede33ba452fb6ac`，包含全部16输入和局部证据身份，封存时现树哈希一致。主要证据：

| 证据 | SHA256 |
| --- | --- |
| 原 FAST12 诊断 | `ee81ac5247f3fe359b02397bac34aad03c5583bf518820e97f83ba9b3dcfbb54` |
| 新 wire verification | `f728fa10174cf1d93a6a5c51e8cf31d4cb3a8072011e341daa32b16cf8871109` |
| 新 wire seal | `a3dfa248730dcac9630d4037416e04a572e44fdc1052d0b753f87b9932caa02e` |
| 主线程 local verification | `50da287a295a0e414e344fef987a972dff4c90b1475c387981b2e76db7b813ca` |
| 主线程 wire verification | `28987e05c4f1a65cc34f6ca93ee09bfb7d34b277096b4e8a02ef10c90bb752e5` |
| 实际 helper 综合 verification | `a748d8c2284b4ec1d6a1b5bd8e3893082411018a1eb8ad96d8c8247cc27843b1` |

## 实际限制与回退

跨不同 FAT LBA 的任意长碎片链可能每次 miss，仍只有约115463 B/s。短 stride260 场景验证了这种布局的内容和 key 正确性，没有证明其无限期实时播放。真实 TF 卡的 token 抖动、长停顿和累计赤字未测试；有限数字卡供给通过不能替代实际硬件带宽或控制到 DAC 声音时延。全机 CDC、r3 的实际新节点覆盖、PLL、P&R、完整 STA 和32声部/普通/矢量音源等保留检查仍需新整机候选验证。

音频 payload 继续在 CRC verdict 前流出，坏前缀可能进入或被 PCM 消费；cache 只隔离 FAT 元数据，不是音频 validated-sector 原子发布。共享同一 RAM 处理每个音频 sector 会覆盖 FAT line，因此本阶段保留独立元数据缓存，未扩展成数据缓存重写。

回退为已提交 `a070a620` 的 W+CRC 阶段与 immutable v13；默认关闭也不自动改变 accepted profile。目标双板均未连接电脑，当前已连接板属于其他 branch，未操作。无 SRAM/Flash 操作，`release_ready=false`、`deployment_allowed=false`。
