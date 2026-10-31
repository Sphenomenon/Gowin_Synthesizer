# AE350 runtime / PCM 独立源码审查与真实 C–RTL 桥接

日期：2026-10-31。状态：源码及离线联合验证通过；B04 实板、持续流、持久配对后端仍未验收。本次未修改运行时或 RTL 实现，未调用综合、布局布线、JTAG、SRAM 或 Flash。

## 固定输入与独立审查

独立树以 `d15ae75` 的 HCI、metadata BSRAM、RTC 装配为底，导入冻结 runtime `01ed9c973993dc2daf4f7a51ef716a5673c44169` 与 PCM `0652ce04d7720c3db185a4d91888ba1c2fb845b9`，本地联合源码基底为 `9c32437d880f3486540ee522ae9bea9ddc40f1f6`。本次新增三份可复用测试和本文／机器记录。各基底的原始来源和历史证据保持原样。

独立重核 runtime 作者封存通过：5862 份源码、2888 份输出和 6320 份工具文件；PCM 作者封存通过 133 份文件。实际 ROM 链接的 87 份输入与联合树一致，原 C–native HCI cosim 的 11 份可映射联合源码一致。原 HCI cosim 的 3316 checks 属于已封存证据的身份复核；本次没有重复执行该 cosim。

源码检查确认：

- `start.S → services_main → background_init/step` 接到真实 runtime 根。启动控制等待、UI 分片绘图、present 等待和稳态服务均泵后台；每次 firmware pump 固定四个 transport slice、最多一次 SBC decode。这是工作量界限，尚非实测 CPU 服务期限。
- HCI 的 source token 与 transport token 分开，COMMIT 不算接受；实际 accepted／transport-done／response-delivered 精确退休。RX 复制前后复核 epoch／ticket／owner／type／length，持有期间刷新 retired。身份变化不向新 epoch 写旧 fence。
- runtime 在完整 submit 接受前保留同一个 frame／PCM／decoded 块；部分写入仅 REJECTED，超时或不确定结果封锁并取消。PCM owner 另以 controller／generation／stream／rate／physical 五字段、严格新 stream、实际物理上下文约束 ARM／COMMIT。
- session 是 ready 异步关闭、同步释放的保持 bundle。源切换经真实效果历史清理、serial hold 和 cancel epoch；BT PCM 使用现有效果，主音量仍只在唯一最终 router 应用。
- 实际固件安装不可用 bond callbacks 并明确 `enabled=0`。实际 PCM 能力 `0x67` 的 bit 3／4 为 false；C 在 bit 3 为零时返回未就绪，先于 ARM、时钟或源切换。没有以 RAM 假装持久存储或填造总延迟。

复制原 `link-v10` 到独立证据目录后，用真实 ELF／disassembly／`.ci`／`.su` 重跑 callback 和栈闭包：171 个 reviewed JALR、200 个全机 non-return JALR、21 个必需实际根，保守峰值 1904 B／16384 B。未遗漏站点、未知 target、来源漂移、容量溢出四个负控均被拒绝。全机 200 个站点不全是 `services_main` 可达回调；闭包验证逐一处理实际可达站点。该结果不是实板 watermark 或周期证明。

## 真实 C–APB/CDC–PCM–DSP–I2S 桥接

新增入口：`sim/audio/run_ae350_pcm_native_cosim.py`，配套 `.cpp` 和 `.sv`。使用真实 `pcm_media.c`、`audio_clock_service.c` 与原 controlled runtime 源清单；APB 每次传输真实跨到 compute 域，PCM 进入原效果、唯一最终音量和原 serializer。按 BCK／LRCK／SD 逐位解码，并逐帧比对最终 tap。DDR 是保留真实数据的有序 owner-6 模型。

最终 baseline 与三个负控均直接使用显式联合 profile 的 `prepare-v6`，candidate `3961efe8f7b81db7`。此前 `prepare-v3` 测试消费的 46 份 stage HDL／include／`.mem` 与 v6 也逐字一致，另存绑定记录；最终 v2 baseline 已直接对 v6 重跑。

实际 PL 始终报告 `0x67`。测试先让真实 C 在两种请求率下确认 bit 3 为零时无 PCM 写、时钟调用或源命令；也验证未知 delay bit 被拒绝。后续使用明确的 C 读包装，仅在测试场景返回 bit 3，驱动尚未实板开启的路径。该包装不修改 PL、不启用实际固件、不证明持续漂移或吞吐。

最终结果：

| 观察项 | 结果 |
|---|---:|
| I2S 引脚解码并与完成 tap 比对的物理帧 | 1644 |
| 精确直接双声道 PCM 帧 | 181 |
| 半档主音量的精确 PCM 帧 | 37 |
| mono 复制到左右声道的精确帧 | 150 |
| 完整块／提交前逐字核对的实际 RAM words | 24／3072 |
| 实际 APB reads／writes，其中窗口 writes | 711／3395，其中 3089 |
| 效果历史清理／非零 chorus 结果 | 8／360 |
| 最大 APB 等待周期 | 7 |

覆盖完整 128 帧块分八次、每次最多 16 个 stereo word；最后一次前不接受／不提交；四槽满时不覆盖、不发命令；回收后循环复用；部分块取消；实际 APB 在途 CPU 复位；旧 stream 不可再 ARM；HCI epoch／generation 撤销；保存旧 C 对象后取消新 epoch 不影响新 owner；持音状态保留；48 kHz 与 44.1 kHz 实际输出上下文。合唱检查等待原有 480 帧延迟线，mono 精确值检查等待现有增益 slew，未更改算法。

三个真实联合负控分别破坏能力 gate、部分块返回值、mono 右声道地址，均在预期的 C 约束或实际 RAM 整块断言处失败。fixture 的 mono 样本数组中未用的尾部显式置零，使该负控确定；原始开发迭代日志保留在外部目录。

复现（从 `usb_a`）：

```sh
python3 sim/audio/run_ae350_pcm_native_cosim.py --project <prepared-Prj1> --output <new-output>
python3 sim/audio/run_ae350_pcm_native_cosim.py --project <prepared-Prj1> --output <new-negative-output> --negative-control mono-channel
```

另两个负控名为 `capability-gate`、`partial-accept`。输出目录必须不存在。runner 固定实际输入与工具身份，核对运行期间无输入漂移，并保存编译／执行命令、日志和输出哈希。

## 联合 profile 与旧 64 KiB 闭包

独立阅读 `workstation_classic_runtime.py`，确认联合选择使用实际 enabled HDL 与 relative-include 预处理，唯一 provider／PCM 源、ROM128 与实际 C 根同绑定。候选 CDC 限制 held payload 10 ns、前两级同步器 2 ns，仅具体异步关闭／CLEAR 端点例外。HCI bundle 约束来源是实际 initializer `boot_id` 和 flow `generations/active/is_le`；没有把组合输出名当寄存器。物理端点解析、ready 恢复、switch-inhibit／serial-hold 传播和 routed STA 明确尚未验收。

旧 64 KiB review 兼容更新亦独立通过：只变 `ui_main.c` 与 `ui_runtime.c` 两个源码身份，全部 73 个站点／targets 保持；真实旧固件完整 disassembly SHA256 仍为 `4b75454ea9517d560d1c0efef744d5d974965e5060bcffe77ae60318620d8f1c`。用实际 `.ci`／`.su`／disassembly 重跑得到相同 1344 B 栈峰值，旧来源 manifest 与未知 target 两负控均拒绝。该更新不放宽机器闭包。

## 证据与仍待完成

外部证据根：`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-runtime-pcm-independent-review-v1/`。最终四目录为 `native-pcm-final-{baseline,capability-mutant,partial-mutant,mono-mutant}-v2`，各有 `verification.json`。另有 `link-v10-independent/`、`foundation-joint-source-binding.json`、`profile-v6-consumed-byte-binding.json` 和 `legacy-64k-review-independent.json`。精确身份及结果见[机器记录](workstation_task_20261030/ae350_runtime_pcm_independent_review.json)。

本 fixture 使用注入的已解码 PCM，不执行完整 HCI／SBC runtime；原有 SBC 向量与 HCI cosim 分别保持其范围。持久 bond 后端、完整栈到实际 PCM 的持续业务、手机互通、解码周期／最长服务间隔、短队列长期频差、总延迟、物理 CDC／P&R／资源、实板栈 watermark 与音频验收仍独立待做。B04 保持未完成；本次没有新的板卡或部署结论。
