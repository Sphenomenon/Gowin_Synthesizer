# Task3 手机 PCM 窗口分块 v2

这是显式双板配置的内部 LCD 合同，不改变 PCM1 寄存器、BLE/HCI 线规、SBC 解码或 M 的采样/DSP owner。旧端点默认 `PHONE_WINDOW_BLOCK=0`；新配置同时选择 `BLOCK_PCM=1` 和 `PHONE_WINDOW_BLOCK=1`。完整 boot/peer/session/generation 能力交换必须匹配 version 2、features `0x80080601`。旧 block6 v1 不能授予新手机通道资格。

W 的真实 Classic/SBC 固件继续通过原 F806 PCM1 APB CDC、命令仲裁器请求 M。只有 target=PCM1、完整四字节、对齐的 `0x800..0xffc` 窗口写允许 posted：本地完成仅表示进入有界暂存。W 保留一个最多 5 字的 building 块和一个最多 5 字的 in-flight 块，最多暂存 10 个 stereo16 字；不另建播放/录音对象。连续地址合并，地址跳转、满块、部分块 12,500 个 50MHz 周期超时、后续非 posted 操作会触发 flush。达到容量时背压 APB，不能覆盖旧项。

ch15 载荷低 96 bit 为 `{base_address32, first_word_sequence32, context_token32}`，随后按低位起放 1..5 个 PCM32 字；长度 `12+4*n`，未用高位必须为零。token 为本次已 ARM 的配对 generation；两侧完整身份及顺序仍由外层传输和 ARM 绑定。M 检查完整地址范围、对齐、块内不越界、序号连续、非零 token、填充和单块占用。未经 ARM、重复、越序、越界或忙时发送均失败并立即消费报文，不占住共享 RX。

M 只保存一个块，逐字经原 `gw138k_apb_cdc` 到原 `workstation_ae350_pcm_owner`。每字先稳定地址一拍，等待真实完成，再撤销 valid，等待 ready 回低；不直接写 owner 的 memory/bitmap/owned。成功后用原 ch7、kind3、完整 common96 返回 `{first_sequence32,error1,next_sequence32}`。ACK 是实际 RAM 写完成水位，**不是播放完成**；只有之后的原 COMMIT/SELECT 及最终实际音频路径能证明相应阶段。

W 只允许一个块在途。每次匹配成功 ACK 后才释放它；所有其他操作（含 PCM 读、key/descriptor、ARM/COMMIT/SELECT/STOP/CANCEL、非完整窗口写和 clock 请求）都等待 building 及 in-flight 清空后才交给原 RPC。它们仍返回原 M owner 结果，不本地模拟空槽、时钟、命令 ID 或播放状态。这样 COMMIT 不会越过 posted 数据；原 owner 仍验证 key、帧 bitmap、序列及槽所有权。无效/错误 ACK、序号耗尽、owner 错误或有限等待超时撤销手机分支；之前的本地写 ACK 不能解释为远端应用保证，后续屏障会返回错误。

发送/ACK/本地等待以及逐字 owner 等待默认各有 50,000 本地周期期限；CPU、采样及网络时钟不同，不能把这些期限加总成物理延迟承诺。断链、PANIC、身份变化、HCI/owner readiness 丢失或能力资格丢失清空暂存并撤销原手机会话，基础合成/DAC 采样继续。M 故障撤销原 PCM owner 的 session，执行其既有静音/历史清理；新配对 generation 必须重新协商及 ARM，旧块/ACK 不能重启旧流。Flash 和硬件部署资格不受本合同改变。

## 预算与验证范围

理想连续满块时，一条 48k stereo16 手机流需 9,600 个 ch15 块及同数完成 ACK，每方向固定 52B 外帧各 **499,200B/s**；五字聚合相对逐字请求/响应减少 80% 数据事务。连续五帧的首帧聚合等待最多约 83.3µs，零散写另受 flush 期限影响。块间等 ACK、CDC、控制 RPC、维护和仲裁均须另计。128 帧原 PCM1 槽不能跨越 COMMIT，至少 26 块，因此按 375 槽/秒约 **507,000B/s/方向**，还没有计入低频 PCM1 状态/key/COMMIT 和时钟命令。

两条 M→W block6 分析/录音满载为 832,000B/s；加手机 ACK 后 M→W 约 1,339,000B/s（25,750 个固定外帧/秒），另加信用、原 RPC、结果、状态和维护。W→M 手机数据约 507,000B/s，另计控制。既有理想线模型的 32,250～34,921 包/秒只能作局部容量参考，不能相减得到有保证的余量；真实三流及实际固件轮询必须独立检验。TF 分析可以背压，真实演奏与最终录音 tap 不等待远端。

模块仿真、真实端点/CDC/PCM owner 验证、完整候选综合、物理 LCD 吞吐/抖动/往返延迟、手机 RF/SBC、D 效果及 DAC 分别记录。生产持续能力位和总延迟有效位继续关闭。目标板未接入时不能据模型宣称持续手机音频、D 模式实板或控制到声音延迟已验收。
