# Native TF clear/restart 完成握手（2026-10-30）

本阶段以显式 hold／真实 accepted-read drain／保持 clear token／四 FIFO ACK／DMA ACK／gate-open 返回替代固定十二个 source 周期等待。memory stopped-high／low 后，source 时间经过不会使 clear 完成；恢复 memory 后才按本地处理与零状态证明继续。新文件 capture 与 playback 的首 byte 都单独要求为 RIFF 的 `0x52`，避免 WAV 重同步掩盖旧 byte 前缀。

这是源码及离线真实维护模块回归通过的阶段记录，不是综合、布线、板上、SRAM 或 Flash 接受。此前旧实现污染证据保留在 [只读审查](WORKSTATION_TF_BYTE_CLEAR_PROTOCOL_AUDIT_20261030.md) 及固定 `26a93f7` 父级复现中，本报告不覆盖历史证据。

## 维护边界与来源

新增唯一命名的 runtime byte FIFO 和 DMA，path 仅在默认 0 的 `NATIVE_RUNTIME_PROTOCOL=1` 时选择它们；runtime service 显式启用。旧 `tf_async_byte_fifo.v`、`tf_audio_ddr_dma.v`、冻结 baseline／vendor／原 manifest 未修改。FIFO 来自维护原件 `e9a7c01f7e5a13569de361b4615099f56706e4bcb93701005938639b45c28148`；DMA 来自当前维护原件 `ac90bd9a06eea44162727169de24e887196b5746fbc29467e299caf9a66aa911`，不是不同 SHA 的 frozen DMA。

| 本阶段产品输入 | SHA-256 |
|---|---|
| `rtl/tf_audio/workstation_tf_runtime_service.sv` | `7766cd00f377f84b6127b3a2c76d46361160ddd8b0e2563de725ca9266f6a577` |
| `rtl/tf_audio/storage/tf_audio_ddr_path.v` | `38a197763e1b567a304ad71576947587d662393626e028f80469e50ac6b66ad0` |
| `rtl/tf_audio/workstation_tf_runtime_byte_fifo.sv` | `0fd5dcddb5d4fbda0af821fd2f46cf8f221b530d8f2be6aca58fc248fbcf3ee6` |
| `rtl/tf_audio/workstation_tf_runtime_dma.sv` | `bc1dcfad79af5777c27d7bfa65ae3b397ce103ca0a992b938027201877119752` |
| `rtl/tf_audio/workstation_tf_runtime_storage.provenance.json` | `6c2c6b964672e7981b5164a40626b994b9a9b2b56784c0a877f5492a33c2f39b` |

完整来源 SHA、所有 TB／runner／helper／contract 哈希和完整 compile argv 在 [机器记录](workstation_task_20261030/tf_runtime_clear_handshake.json)。profile/锁更新由独立来源阶段登记，本阶段不改变 accepted/pinned/default 选源。

## 协议实现

service 保存 path track 快照；track change、reader fault、restart、cancel 先进入受控关闸／排空边界。native path 的 track/fault 不再自行绕过 service 翻转 clear。只有前一 token 完成、frame bridge sourcequiet 及 accepted DDR read 真正排空后，service 才发布新 token；重复请求合并到 pending 选择，不覆盖在途 token。

FIFO clear 第一同步级仅进入第二级。每个本地域 hold 时归零本地 pointer／read valid，Gray 两级接收链持续运行；本地及远端第二级 pointer 为零并经过本地稳定资格后，才把当前 token 回为 ACK。ACK 不是请求到达指示。两端维持 hold，四端完成前不接纳流量；多位跳零只能发生在未完成全局 clear 的隔离窗口。

runtime DMA hold 关闭新请求、emit 与回填，保留已接受读响应的退休；处理 restart token 后清理私有 read/write buffer、等待状态和旧观察，零状态资格成立才 ACK。path 将四 FIFO ACK 和 DMA ACK 组成向量，经 50 MHz 两级资格确认，service 收齐才撤 memory hold，并等待实际 gate-open 返回。失败8超时维持 busy／hold，恢复后可清理但不会将失败文件自动重臂为播放成功。分析读取共用同一握手并保留 ready 首帧。

默认 path 的新参数为 0；checked inverse 逐个精确锚点移除新增 opt-in 适配后，还原前一维护输入，再经已有逆适配逐字节等于 immutable `resource_rework_route0` 原件。双真实 path 完整输出逐拍对照通过。

## 离线验证

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_runtime_clear.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/tf-runtime-clear-protocol-final-v2
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
git diff --check
```

最终 runner identity 为 `native-tf-runtime-clear-v1-0edb43cc2c787d5d`，完整源集合 SHA 为 `0edb43cc2c787d5d8a997c74501b4a5f2304160609c2e10b50f310a652ee72c9`；nominal identity 为 `native-tf-runtime-service-v4-dacf720d5f98e7bc`。runner 前后输入 seal 一致。新独立复跑的 output 路径也属于集合记录，identity 应重新生成。

| 回归 | direct | 实际 command buffer |
|---|---:|---:|
| 普通 TF 场景 | 22 | 22 |
| PCM／analysis／暂停零帧 | 677／128／6 | 677／128／6 |
| 专用 clear 场景 | 6 | 6 |
| memory stopped-high／low | 2／3 | 2／3 |
| 四 FIFO ACK 变化／多位指针归零 | 60／28 | 60／28 |
| capture／playback 首 RIFF byte | 9／9 | 9／9 |
| 受控 token 变化／analysis restart | 15／1 | 15／1 |
| 专用完整 PCM 交付 | 198 | 198 |

专用场景覆盖持有旧 read_buf 的同曲 restart、换曲 restart、clear 在途重复请求、cancel+memory 停钟超时及恢复、reader fault／卡恢复不自动重臂、analysis hold／恢复首帧。逐域断言检查 ACK 当前 token、处理完成前本地及远端零状态、非 unit pointer 隔离、gate 不早于 DMA processed token、新 token 不早于前次 ACK／read drain、restart 同沿无旧 emit。默认回归为 128 PCM 帧及 12,531 次逐拍输出比较。

临时 ACK-bypass path 将 `runtime_clear_done_o` 固定为1，负向执行在 10,950 ns 被 `source pointer nonunit jump escaped clear isolation` 明确拒绝；该副本没有改维护输入。保留的 combinational memory_quiet 负向副本也被拒绝。专用与普通全部正向退出0；10项 current-workstation source tests 和 diff whitespace 检查通过。编译无 implicit declaration；仅有 inherited-timescale 提示及 default reference 中两个被关闭新协议忽略的未连接 opt-in 输入提示。

## 新综合与物理复核门槛

新增 `g_runtime_capture`／`g_runtime_playback`／`g_runtime_dma` generate scopes，且 Gray 接收第一级现在直接接 Gray register，原 clear LUT gating 已移除。**旧 synthesis/VG selectors 必须按失配失败，不能据旧网表名继续声称 CDC 接受。** 后续必须基于新 VG 重新枚举精确 FF 位映射、时钟归属和第一同步级扇出，审查四组 Gray flight/skew、held token/ACK、clear 多位跳零隔离及 routed CDC/reset。此阶段没有做该物理接受，也没有放松时钟或 false path。

仍使用理想有序单 outstanding DDR 模型和 SD/FAT byte-boundary fixture；不模拟模拟毛刺／亚稳态，独立 memory reset 或 late/reordered response 仍依赖整机守护。TF 仍经过 DDR ring/staging，本次不是最终 no-DDR 即点即播迁移；EOF 也不是有序 EOS／实际输出排空成功。新媒体 stop-before-rate-switch 接口将作为后续单独变更。

回退时回退本实现阶段，保留缺陷审查与历史证据；新的 release 输入必须有新候选 identity，不能复用任何已接受 identity。

## 父级独立复验

父级在 `tf-runtime-clear-parent-final` 新目录重编译并运行完整 runner，普通 direct／buffer、默认逐拍对照、两组专用 clear 用例与负向 ACK-bypass 均通过。仅规范化生成文件的输出目录后，所有输入内容哈希与子代理一致；全部指标逐项相同，原始证据 SHA 与源哈希见 [独立复验 JSON](workstation_task_20261030/tf_runtime_clear_parent.json)。这仍是离线协议验证，不代替新综合及物理／板端验收。
