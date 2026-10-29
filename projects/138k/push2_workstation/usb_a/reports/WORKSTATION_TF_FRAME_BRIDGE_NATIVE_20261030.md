# TF 原子 PCM 传输与取消 owner

2026-10-30。新增未选中的 `rtl/tf_audio/workstation_tf_frame_bridge.sv`，把 50 MHz
decoder 的同点 `{rate20,error,left16,right16}` 与独立 32-bit transport generation
打包，通过有界 FIFO 交给持续运行的 compute 域。它不使用旧 TF DAC sample tick
抽取 PCM，不改旧 TF bridge、top、profile、decoder、DDR 或识别分支。

源码身份为 `native-tf-frame-bridge-v1-a879430d988b77dd`，RTL SHA256：
`a879430d988b77dd367cee604a91a68db56c5b603eff07e8cefc80355448cf65`。
完整时钟、valid/ready、取消、quiet、源接入与物理门禁见
`rtl/tf_audio/WORKSTATION_TF_FRAME_BRIDGE_CONTRACT.md`。

## 取消与 quiesce

每个源 invalidate edge 将 binary generation 加一，并同拍注册 Gray。
compute 独立观察 generation，取消 held 和旧 FIFO 帧，不等新 PCM，也不等源 ACK。
源即使在最后一拍后停高／停低，最终取消仍能到达 compute。
首个 source edge 的身份存在证明独立于本地 FIFO release，因此 reset 后第一拍
clear 并立即停钟也能被观察。

新代 PCM 放行另受返回 Gray ACK 限制：compute ACK 每拍只单步追上已发布的
expected generation，源见匹配 ACK 和 identity valid 后才开放 ready。
两端同用 `INITIAL_GENERATION`，默认零；near-wrap 起点不会从零追数。
compute 连续 76.8 MHz、source 50 MHz 及有限身份不得在未观察期间完整复用
2^32 次的约束已明确记录。

quiesce 为源域保持请求。compute 撤销／排空、等待同步稳定并输出 compute 域
media quiet；源域另有匹配 generation 的 quiet ACK。恢复时 ready 等待 compute
quiesce 的回程解除，首帧不会被仍在退出的排空逻辑吞掉。stream 事务不复位 FIFO。

非 48/44.1 kHz 率在源握手时照常入队并保留真实 rate，但变成零/error 包并计数；
目的消费仍取决于 ready。实际 final router 对错率输出零/error 且不消费 TF 头，
所以文件 policy 必须明确失败并 invalidate，才能清除该代数据、恢复 decoder。
桥本身不发明自动率切换或抽样，也不保证不作取消的整机错率文件永不阻塞。
输入 error 与 PCM 整包保留，由 final router 处理其物理零输出。没有加入重采样。

## 回归

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_frame_bridge.py
```

测试使用维护的 `music_async_fifo`、真实 `tf_wav_chunk_parser`、
`tf_wav_pcm_decoder` 和实际 `workstation_final_pcm_router` 错率边界；在运行目录生成两个真实 stereo PCM16 WAV，各含八帧
正负非零左右声道及 16-bit 极值。header、PCM 和 rate 都由真实 decoder 产生。
source 50 MHz 与 compute 76.8 MHz 异步运行，队列缩为四帧以验证满载背压。

| 检查 | 默认 0 起点 | `0xfffffffd` 起点 |
| --- | --- | --- |
| 真实 WAV48／WAV44.1，golden 左右声道逐帧相同 | 16 帧通过 | 16 帧通过 |
| 源接受／compute 交付 | 47／35 | 47／35 |
| 显式 invalidate 事件 | 15 | 15，包含正常 wrap |
| 满队列源背压／held 目的背压 | 23／76 拍 | 23／76 拍 |
| 无 quiesce 的旧代 held／FIFO 自动取消 | 5 帧 | 5 帧 |
| 实际 router 错率保留头／policy cancel 恢复 | 1 帧 | 1 帧 |
| quiesce 排空 | 5 帧 | 5 帧 |
| 另一次在途 common reset 丢弃 | 1 帧 | 1 帧 |

每次目的握手都比较整包，并要求其 generation 匹配独立 expected identity。
普通背压时逐拍检查 valid 和 payload 不变。测试另外覆盖：

- 最后一次快速连续 invalidate 后，源立刻停高／停低；不再送 PCM，compute
  仍更新最终 identity、取消旧包。低停场景另完成 media quiet。
- common reset 后第一源拍 clear，并在本地 FIFO release 前立即停高；compute
  仍发布首 identity 并完成 media quiet。源恢复后首次新帧正常交付。
- 没有改 generation 的 quiesce/resume，第一恢复帧正常交付。
- 真实率 32 kHz 显式零/error、source error 保留、common reset 后旧包不泄露。
- 将 32 kHz 包连接实际 final router：产生 RATE_MISMATCH 零/error，TF 头仍保持且
  未被消费；调用方明确 invalidate 后旧头清除，新的 48 kHz 包正常交付。

精确输入哈希、编译命令、日志身份和计数见
`workstation_task_20261030/tf_frame_bridge_native.json`。两次编译及仿真成功，
验证期间输入未变化。最终验证目录为本机 cache 的 `tf-frame-bridge-v8`。
父级以 `tf-frame-bridge-parent-final` 独立复跑默认与回绕两组，指标一致，
两次编译日志为空，验证期间输入哈希不变；对应验证 SHA 也记录在机器文件。

## 集成边界与回退

真实取样点已只读核对：现 `tf_audio_ddr_path` 的 PCM valid/ready、stereo16 和
actual rate 均在 50 MHz；path、WAV decoder 和 parser 与所检 prepared 输入字节相同。
不能用旧 audio 域 `pcm_active` 和独立 `rate_sync` 代替此源契约。
真实播放接入时仍需保全 reader/playlist/recognition 及 owner3 TF DDR，定义共享
decoder ready 的缓冲／丢窗策略，并接入上层媒体授权和格式错误状态。

本阶段没有综合、P&R、真实 SD/FAT/DDR 播放、SRAM/Flash 或板级验收。
Gray 的位间 skew/max delay、同步器、FIFO payload 和 reset release 物理门禁尚未
接入新 profile；仿真通过不表示 routed CDC 成立。该源码没有位流身份或硬件接受身份。

回退为继续选择既有 TF 路径，新 owner 保持未选中；移除新增文件即可，不涉及冻结
baseline 或历史输入重建。
