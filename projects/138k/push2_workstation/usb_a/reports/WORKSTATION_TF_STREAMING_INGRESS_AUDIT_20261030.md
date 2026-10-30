# TF 即时播放流式入口审计（2026-10-30）

本阶段完成 M03 的固定来源审计和最小控制复现，**未实施无 DDR 播放，M03 保持未完成**。审计对象固定为提交 `4e0dc6cf250896aeb22a4af1f8450b3a20694279`，不随后续 live RTL、profile revision 或暂存路径变化。身份为 `native-tf-streaming-ingress-audit-v1-1560e63f137e21cc`，完整输入集 SHA-256 为 `1560e63f137e21cc3898cba09601d0f1d0ae19bd7a1a9e2b12a1cff98647fe7f`。

机器证据、固定来源哈希、代码位置及完整建议见 [tf_streaming_ingress_audit.json](workstation_task_20261030/tf_streaming_ingress_audit.json)。本阶段只新增该报告、JSON、一个测试 runner 和一个最小 fixture；产品 RTL、tools、profile、vendor、冻结对象和 task 方框均未修改。

## 1. 实际入口与来源

固定提交中的 `custom138k-workstation-v1` 声明 WAV、48 kHz／44.1 kHz。原生路径为：

```text
SD/FAT → capture byte FIFO 4 KiB → DDR DMA／ring
       → playback byte FIFO 4 KiB → tf_audio_decoder_ip
       → 85-bit generation/rate/PCM bridge → final PCM router
```

已有测试的 direct／buffer 只区分 `tf_audio_ddr_command_buffer` 接法，两者都读写 DDR。真正的直读参考是 `tf_sd_audio_pcm_player`：SD/FAT→4 KiB byte FIFO→held-ready skid→decoder，预填为2 KiB，整扇区准入余量为640 B；但其旧切曲、热拔卡、停止、清理和 EOF 状态不能直接替代 native owner 的已维护契约。

`workstation_runtime_profile.py` 显式替换 maintained `tf_audio_ddr_path`。SD/FAT reader、sector reader、SPI session 和旧 direct player 仍由锁定父输入提供；runner 从固定提交读取它们并与 `resource_rework_route0` 描述符逐项比较，身份相同。固定树内部分 owner 已晚于 revision4 的输入锁，本审计没有执行 prepare 或证明该树可通过 profile 锁闭包；后续新候选的独立 prepare 不能由本审计代替。

当前分析与播放互斥：mode1 将 decoder PCM 送播放桥且不投递 analysis，mode0 允许 analysis 的 hold／ready 背压。无 DDR 迁移必须保持这个归属，不增加播放等待分析的路径。TF 进入现有最终路由也不证明其经过合成器效果、实时变调／包络／混音；这些矩阵仍归 A03 等任务。

## 2. 已复现的传输成本

固定 sector 源 SHA-256 为 `259bedb80a6a54cf2048ae6cb2f40ec384108ae2743acb49b8acb70abf126504`。真实控制 FSM 在 IDLE 先完整执行 CMD17，仅切到 READING；之后对同一 target 再执行 CMD17，才转发512 B并给出逻辑 done。最小 fixture 从已初始化的 SDHC／IDLE 状态开始，使用成功 SPI session stub，观察到：

| 观测 | 数量 |
|---|---:|
| 外部 sector 请求 | 1 |
| 完整成功 SPI 会话 | 2 |
| 原始 session 字节 | 1024 |
| 文件侧转发字节 | 512 |
| 逻辑 done | 1 |
| spistart 上升沿 | 3 |

第三次 start 只持续一个50 MHz源时钟，在 req_hold 清除后撤回，未交付数据，不计第三次完整会话。让两个成功会话都转发字节的临时负控得到1024 B，fixture 在 `historical sector audit mismatch` 处拒绝它。

这证明历史控制行为，不是完整 SPI 线协议或实际卡的吞吐测量。fixture 手动设置初始化状态、替代 `tf_spi_session`，因此不验收初始化、MISO 时序、卡 token、CRC、重试或物理信号。

真实 session 源另将每次会话 `stopcycle` 固定为255。该阶段虽关闭 sck，内部仍按 SPI byte 时基递减；它构成255 byte-times 尾等待。即使完全忽略 CMD、响应、token、CRC、FAT 等额外耗时，旧 transport 的文件有效吞吐也只能满足：

```text
f_spi = 50,000,000 / [2 × (divider+1)]
R_raw = f_spi / 8
R_file ≤ R_raw × 512 / [2 × (512+255)]
```

| FAST divider | SPI MHz | 原始 kB/s | 旧 transport 乐观文件上界 kB/s | 每簇1扇区且额外FAT读取的上界 kB/s | 固定40000-byte token窗口 ms |
|---:|---:|---:|---:|---:|---:|
| 12 | 1.923 | 240.4 | 80.2 | 40.1 | 166.4 |
| 6 | 3.571 | 446.4 | 149.0 | 74.5 | 89.6 |
| 3 | 6.250 | 781.2 | 260.8 | 130.4 | 51.2 |
| 2 | 8.333 | 1041.7 | 347.7 | 173.8 | 38.4 |

kB/s 为十进制。FAT reader 在每个 cluster 转换时读整个 FAT sector，没有带 tag 的复用缓存；最坏1-sector cluster 每个 data sector 再付出一个 FAT sector，上表最后吞吐列再减半。它们是根据固定源计算的**乐观上界**，不是已达到的速率。

native path 硬编码 FAST12。旧 transport 即使提高到有效最小 divider2，无 FAT 时上界347.7 kB/s仍低于48 kHz stereo32的384.0 kB/s，也低于44.1 kHz stereo32的352.8 kB/s；FAST12上界也低于两种 stereo16。FIFO可吸收短停顿，不能补足长期吞吐差额。现有 WAV 支持8／16／24／32-bit mono／stereo，迁移不能静默裁成 stereo16。

## 3. 可执行的最小实现边界

1. **先修 native sector 控制。** 仅把必要的可归属适配提升到版本化 native owner，保留 GPL／原来源与差异证据，显式替换旧模块；不改 vendor 或 baseline 字节。去除重复完整 CMD17，修清 req_hold 收尾，按实际 SD 契约约束尾部 CS／空闲时钟。继续复用原 SPI session，除非其必要变化也单独提升为受检适配；不复制整条工程或增加长期编号 builder。
2. **分频与 token 耐心一起定义。** `tf_spi_session` 的分频寄存器只有8-bit，小于2会钳到2；在合法2..255范围，50 MHz下最大 SPI 为8.333 MHz。FAST0表示恢复 init divider，FAST1也会钳到 divider2；大于255会截断，现有代码没有参数范围保护，不能把截断后的波形当作支持的高速模式，新适配应显式拒绝越界。提速候选须验证新板 IO、MISO、卡和音频并发，不能因理论速率合适就认定可用。40000-byte窗口在提速后会由166.4 ms缩成89.6／51.2／38.4 ms，可能破坏历史长 token 等待修复；新适配应保留至少原166.4 ms的显式时间预算，播放失效后也不能通过过早重发 CMD17制造 abort 风暴。历史约100 ms依据来自原源码／报告，本轮未重新核对 SD 规范。
3. **FAT cache是优化，不是最坏保证。** 一个512 B sector cache加 tag／valid，可复用同一 FAT16／FAT32 sector内的大量连续链 lookup；任意碎片仍可能每次 miss。连续 cluster descriptor 必须经真实 FAT 验证，不可假定 cluster+1。缓存复位／拔卡／重插失效，metadata扇区不能进入音频字节流；仍只有一个传输 owner。
4. **在既有 path 内加默认关闭的 no-DDR ingress 分支。** 复用同一 reader、热拔卡策略及 decoder，只把 capture／playback／DMA三段替换为源域 byte FIFO＋held-ready skid，DDR请求固定无效。service继续拥有run／pause／stop／失败／generation／控制mailbox，顶层只接线。最小方案可让互斥的分析与播放都消费direct ingress；若保留分析DDR模式，分支选择必须锁到一次session并在quiesce/restart后切换，不能组合切FIFO。保留其它DDR客户端、地址图及当前回退路径，不因审计预先重分配TF banks。
5. **在解码后设置普通32-bit PCM预填队列。** 它在50 MHz源域承载大缓存，85-bit rate／generation跨域桥继续保持浅队列，避免大队列每帧复制元数据。format-ready和prefill-ready分开，短文件有经验证的EOF释放。pause继续保留精确下一帧；stop仍等待已建立的清理／generation／末次inactive mailbox ACK，迟到旧sector尾部必须丢弃。

这些是后续实现建议，当前没有修改或启用任何产品分支。MP3／FLAC源码保留，但不从当前 WAV profile 的结果推导压缩音频已流式验收。

## 4. 健康缓存预算与欠载终态

需要同时规定健康长时吞吐和**最大累计供给短缺**，不能只验证一次最长 token，或允许每个扇区都停50 ms。48 kHz／44.1 kHz stereo32输入分别为384000／352800 B/s；decoder输出PCM16对分别为192000／176400 B/s。下表为待验证的50 ms累计PCM短缺资格目标：

| 模式 | 50 ms需保留帧数 | PCM字节 | 3072帧预填时长 | 4096帧容量时长 |
|---|---:|---:|---:|---:|
| 48 kHz | 2400 | 9600 | 64.00 ms | 85.33 ms |
| 44.1 kHz | 2205 | 8820 | 69.66 ms | 92.88 ms |

一个候选是4096帧／16 KiB PCM、3072帧预填，另为浅桥16帧、decoder／skid、请求相位和已启动整扇区保留余量。加4 KiB ingress与512 B FAT cache合计约20.5 KiB。按容量估计旧两只4 KiB FIFO约4块BSRAM，新组合约11块，**可能净增约7块**；这是容量估算，既不是已综合资源，也不是P&R物理块数，不能写成节省。实际映射、其它控制逻辑及净成本需同配置比较。

50 ms只是资格目标，没有从当前消费卡量测得到。4／5秒watchdog用于故障判断／恢复，不能当成必须无缝覆盖的时长。超出健康预算或实际缺帧时，现有final PCM router继续按采样节拍计TF_UNDERRUN、交付带错误零帧；后续owner应锁存一次失败、作废旧代次、保持静音并清理，等待显式重启。不重复最后一帧，不把持续补零当成功，不暂停计算或I2S；健康服务失约与CARD故障分开记录。

自然EOF仍有独立缺口：raw EOF、decoder drained、PCM队列空、桥排空与最后物理I2S帧ACK不能混用。旧`pcm_end`是字节／FIFO条件，不证明有序物理结束。新队列不得让短文件永等预填，也不得把尾部metadata当PCM；若没有新增明确EOS／last-frame确认，本阶段后仍需标注EOF无成功排空证明。

## 5. 复现与后续验收

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_streaming_ingress_audit.py \
  --output /tmp/tf-ingress-fixed-audit
```

输出目录必须不存在。runner以`git show`读取固定提交的17项审计输入并记录哈希，编译固定sector源与最小fixture，不读取未来live产品或私有staging。正常控制复现和转发双会话负控均通过预期判定，runner／fixture前后哈希一致。Icarus保留固定sector未声明time unit的原有timescale警告；没有为消除警告改写被审计源。`git diff --check`通过。

后续实现至少覆盖：实际SPI线级SDHC／SDSC初始化和单请求单CMD、时间化token等待／错误；FAT16／32最碎片1-sector cluster与cache命中／失效；两率mono／stereo所有WAV位深、RIFF未知chunk／奇数pad／尾metadata／短文件／截断；预填、持续恢复吞吐、累计deficit、满队列整sector余量、分析慢端隔离；pause、stop、取消、换率、拔卡、停钟及迟到旧代次；缺帧可见错误与终态，物理EOF；对应播放DDR客户端接受读写均0，并验证其它DDR客户端正常。

去掉整sector余量、提前预填、重新引入DDR转运、吞掉underrun或接收旧generation等负控应分别被拒绝。之后复跑既有来源、service／clear／stop／frame bridge／final router，独立做同配置综合和P&R资源／时序／CDC，再做实际SD／I2S／声画并发板测。本审计未prepare、综合、P&R、生成位流、操作JTAG／板卡、写SRAM或Flash。撤回只需移除本阶段四个新增审计文件，不影响产品或部署状态。

## 父级独立复验

父级在新目录独立运行固定revision的runner，再次得到1个逻辑请求、2次完整SPI会话、1024个raw／512个forward bytes及1次逻辑done；转发两次读取的负控被拒绝。输入身份与所有分频／吞吐／缓存推导逐项等于冻结子阶段。原始结果见 [tf_streaming_ingress_audit_parent.json](workstation_task_20261030/tf_streaming_ingress_audit_parent.json)，SHA-256 `bbde03d1303e4a943d48586bde5d7690a7bb3353b75ea0fdc9168eb9d92db599`。该控制复现不包含线级SD模型或实际卡；M03实现和验收仍未完成。
