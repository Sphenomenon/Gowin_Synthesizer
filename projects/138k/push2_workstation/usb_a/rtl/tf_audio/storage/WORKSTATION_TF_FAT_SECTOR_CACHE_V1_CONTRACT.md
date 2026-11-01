# 显式选择的单扇区 FAT cache

`FAT_SECTOR_CACHE` 在维护中的 file、direct-native 和 direct-runtime 三层默认 `0`。启用必须同时设置 `VERIFY_DATA_CRC=1`，否则 file owner 拒绝配置。DIRECT profile 的显式选择、来源锁和候选身份另行建立；默认参数、SPI 分频、token 超时、byte/PCM FIFO 与 `PREFILL_FRAMES` 均不改变。

缓存仅保存 `READ_A_FILE` 使用的一个完整 FAT 元数据扇区，不保存音频。512B 以 128×32-bit 同步 RAM 组织，按真实 SPI 字节序每四字节组装写入。精确的 32-bit FAT LBA 是 key；FAT16 的两个 16-bit entry 共用一个 word，FAT32 每个 word 对应一个 entry，既有 FAT16/32 掩码、有效 cluster、链长和最后 EOC 校验保持有效。碎片文件仍逐 entry 跟随实际 FAT，不假设相邻 cluster。

填充开始即撤销旧 line 的有效位。只有严格按 `0..511` 完整收到 512 个真实 payload 字节，且原 CRC-enabled sector owner 在 payload、两 CRC 字节及 CS 高释放后给出真实成功 `read_done`，才发布 line。缺失、重复或乱序字节、CRC/transport 错误不能发布。缓存没有第二 SD controller，也不向 sector owner 伪造 `read_done`。

命中后由同步 RAM 返回实际 entry，再通过 file owner 的本地 metadata-completion pipeline 应用。它不使用不存在的 SPI 事务或 CRC 完成事件。数据 sector 的完整空间预约与无背压 payload 接收不变；metadata lookup 不占用音频 byte FIFO。无 SPI 请求在途的本地 lookup 可以直接取消，不等待 transport ACK。

STOP、pending STOP、`track_start`/pending 新任务、file/sector error 及 owner reset 均撤销有效位和填充/lookup 资格。输出 hit/result 在生命周期 fence 当下即受门控。被取消填充的迟到 payload/done 不能重新发布，被取消 lookup 的迟到本地完成不能应用；后续任务必须真实重读 FAT。新任务和 STOP 的原优先级、失败取消语义、最终 EOC 与成功 EOF 区分保持。

`workstation_tf_fat_sector_cache_v1.adaptation.json` 是独立严格来源链。它先将 file/native/runtime 和新增显式验证入口逆回 `a070a620` 的 CRC 阶段原字节，再调用原 CRC 验证主体核对不变的 CRC manifest、原 manifest/vendor、旧 basis 和精确 anchors。`tools/workstation_tf_fat_cache_provenance.py` 的重建仅用于验证，不写源码、不作为生产回退。旧 CRC manifest 的 SHA256 仍为 `230b9436cab1b56311ef757f548ccf12705ff94ca7381b0e718aedfa7b0d17f4`。

旧 sector/file wire runner 需显式 `--direct-fat-cache-source-adaptation` 才接受新链，它们的 DUT 仍关闭 cache 和 CRC。旧 CRC provenance unittest 在新源码树上同样需要此显式 flag；不带 flag 的旧 CRC verifier 继续拒绝新来源。新行为由独立 cache local/wire 测试验证，旧默认测试不能算作缓存供给证据。

独立 Gowin V1.9.12 / GW5AST-LV138PG484AC2/I1 C 综合已生成单个 SDPB，报告为 1 个 synthesis-equivalent BSRAM、70 FF、35 LUT、1 INV、50 ALU、0 SSRAM；32 位 RAM 输出均连接到 top 输出，未被剪掉。这只证明独立 helper 的实际综合映射，未做 P&R，不能替代整机资源增量、routed physical BSRAM 或时序验收。当前单行可能在跨 FAT LBA 的极端碎片布局中反复 miss；这时原平均带宽缺口仍可能存在。实际 TF 卡的 token 抖动、最大累计供给赤字、板上时延、完整 routed timing/CDC 和 DAC 音频还需独立验收。

音频 payload 仍在最终 CRC verdict 之前流出，本缓存没有实现 validated-data-sector 的原子发布。把同一 RAM 同时用作每个音频 sector 的 CRC staging 会覆盖 FAT line，可能失去此带宽收益；那需要独立数据缓冲及有界容量协议，属于后续单独评估。
