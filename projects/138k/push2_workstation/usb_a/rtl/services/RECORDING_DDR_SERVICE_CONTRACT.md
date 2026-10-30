# R00 原生录音生产组合

只有 `custom138k-workstation-r00-v1` 显式选择 `workstation_profile_r00_runtime.sv`。它保留条件 no-CNN 配置的其他功能，在真实 `hdmi_display` 内选择 owner8 队列／四位返回 owner，并把 `workstation_recording_runtime` 接到已完成的最终 I2S 物理帧。默认 runtime、条件 no-CNN、accepted/pinned、resource-only 和无 profile 入口继续使用原 DDR 仲裁与 BLE 短录音后备，不会因新增文件而选择本路径。

组合根只连接 PCM CDC、APB CDC、录音服务、正常封存桥和真实 native commit 桥。对象／引用／下载由服务及 `workstation_pcm_ddr_backend` 负责；已提交 ID、实际 rate、epoch、帧数和状态只有 backend 一份权威值。调用者提供非零 64-bit 对象 ID；本阶段不生成持久设备会话，不迁移 BLE task ID、CRC、续传协议或 Android 对象。

## PCM 与容量

输入为串行器实际完成的一帧 `{rate44, epoch, sequence, error, PCM16左右}`，不是 compute 请求或未播放的渲染结果。物理 PCM 高 16 位为左、低 16 位为右；组合器在进入后端时交换半字，后端及下载字节顺序为 left low byte、left high byte、right low byte、right high byte。98-bit observation FIFO 在 DDR UI 域持续消费，音频侧没有 ready。FIFO 满计 drop；loss 为持续失败条件。error/gap 只在有效帧上检查，空队列的无效 payload 不参与错误判定。失钟后 backend 在实际 UI 频率下 4 ms 报错，不复播旧样本。

唯一地址来源仍为 `rtl/ddr_address_map.vh` 的 `0x30500000..0x305fffff`，本阶段只使用首 64 KiB／16,384 个双声道 PCM16 帧。48 kHz 最多约 0.341333 秒，44.1 kHz 约 0.371519 秒。R00 prepare 从受锁 baseline 验证原 header 字节，再检查所有既有宏值保持，显式以维护的地址权威替换 staged `src/memory/ddr_address_map.vh`，记录原／新哈希；不修改 baseline 原件，不从旧地址推导新区域。

## AE350 服务入口

内部 APB 页为 `0xf8040000`，通过现有 `gw138k_apb_cdc` 到持续运行的 DDR UI 域。它不是新的 BLE 或 MIDI 协议。访问必须字对齐；写必须四个 byte strobe 全置位。未知寄存器／坏命令／无效状态返回总线错误且不产生操作。一个调用者串行访问，固件 API 在 `firmware/ae350/recording_service.h`；UI 不编码录音协议。

| offset | 内容 |
| --- | --- |
| 00 / 04 | ID `0x52434401`／能力 `0x00010007`：服务 v1、双率、64 KiB、owner8，未声明 BLE 新格式 |
| 08 | 命令：1 CREATE，2 SEAL，3 CANCEL，4 CLEAR，5 ACQUIRE，6 RELEASE，7 DOWNLOAD，8 POP_HEAD，9 RELEASE_HEAD |
| 0c | 低位 state[3:0]、failure[7:4]、seal pending[8]、reference held[9]、snapshot valid[10]、quiescent[11] |
| 10 / 14 / 18 | 暂存 ID low／high、容量帧数；不是已提交对象 |
| 1c / 20 / 24 / 28 / 2c / 30 | backend 对象 ID low／high、实际 Hz、epoch、帧数、native 已提交帧数 |
| 34 / 38 / 3c | capture FIFO 峰值、native 命令／读返回最大等待周期 |
| 40 / 44 | 暂存下载 byte offset／length |
| 48 | snapshot bytes[5:0]、last[6]、snapshot valid[7]、backend head valid[8]、本次 done sticky[9]／error sticky[10]、reference error[11] |
| 4c..68 | 原子 snapshot 的 8 个 32-bit word，仅低 bytes 字节有效，可乱序重复读取 |
| 6c / 70 | 最近观察的物理 sequence／累计 observation drop |

CREATE 不提前确认：命令在总线 CDC 中保持，等下一真实有效帧才执行并返回成功。该沿帧不录入，实际 rate/epoch 冻结为该帧元数据，first sequence 为该帧 sequence+1（含回绕）；随后下一连续帧开始采集。等待超过 4 ms 返回总线错误，不创建对象。坏来源、未就绪、seal hold 或同拍正常 seal 均拒绝创建。CPU observer reset 可以撤销尚未确认的总线命令；写失败也可能已经提交，API 不自动重试。

SEAL 只要求正常封存，不丢弃已采集帧。媒体准备第三 owner 在 normal seal 后等待 immutable READY 且 native 已发布采集写排空才返回 done；EMPTY 可立即无事完成，错误状态返回失败类别 12，后端详细错误从对象页读取。这个确认是采集写边界；READY 对象的独立下载及引用可在确认后和采样率切换期间继续，不构成全 owner8 读事务的静默屏障。hold 在整个采样率切换期间阻止 CREATE／CLEAR／CANCEL。已封存对象的 rate/epoch 不随系统后续切换变化，下载继续解释该对象自己的格式。

PCM observation 的 destination_loss_seen 是 controller 生命周期内的 sticky 健康标记。任一次观测丢帧（包括没有录音对象时）都会使当前采集失败，并拒绝之后的 CREATE；CLEAR、CPU observer reset 和重新 acquire 都不恢复来源健康，恢复需要 controller reset 后重新观测真实有效帧。此处保留 fail-closed 策略，未实现对象生命周期内清除健康标记的业务命令。

维护 C API 只由 R00 profile 显式加入 ROM；enabled／no-CNN 仍编译原五个源文件。所有调用都有固定次数的总线读写且不会自动重试。poll 跨独立寄存器读，是 advisory 状态：ID 双读只检测对象身份变化，CAPTURE 中 frames／committed 可以在读之间增长。READY 的对象描述符不可变；下载数据必须通过 POP_HEAD 的原子窗口读取。调用方必须保证单 caller，写调用传输失败不代表业务未执行。

CANCEL 是显式业务作废，不能代替正常切换 seal。native bridge 的 submitted 位只有真实 owner8 native 接受才能清除；slot/core ready 不可提交 backend 帧数。返回由四位 owner 账本路由，response pulse 与数据共同寄存。transport fault 同拍关闭新的对象／下载输出，已有发布命令和读仍按账本排空；超时不能冒充返回完成。

## 引用、快照与复位

READY 对象在引用持有期间不可 clear。ACQUIRE 使用暂存 ID 精确匹配对象；DOWNLOAD 范围必须完全位于 frames*4，非对齐 offset/尾段允许。POP_HEAD 将一个真实 backend beat 的 data/bytes/last 原子捕获并推进 backend；CPU 可以慢速或乱序读取八个 word，RELEASE_HEAD 后才允许下一个 POP。空 snapshot 读取报错。release/cancel/fault 即时阻止旧 snapshot 交付；读超时／迟到返回沿用后端 generation fencing。

CPU observer reset 只清总线暂存／snapshot 并 release 下载引用，已接受读必须真实返回并排空，录音及已封存对象不清除。调用者重置后需要重新读取对象并以明确 offset 开始新下载，不宣称此前 snapshot 连续交付。共同 DDR／仲裁账本／backend reset 才清对象和 channel。当前 reset 仍依赖视频／DDR 组合边界；该行为要在候选验收中单列。

## 验证与剩余门禁

本阶段目标是正式编译选择和真实 RTL 的“物理 PCM→owner8 写→DDR→对象读出”，不是再增加未选择组件。保留旧 BLE RAM，因此不能声称释放历史 32 块 BSRAM；新增 FIFO／预取和仲裁成本必须用同配置综合／P&R 实测。最终 PCM/新 seal CDC 的物理时序、完整 reset/CDC/PLL、DDR 服务上界、并发无音频欠载、非静音板录音、BLE 对象迁移／CRC、Android 真机、长录音和 SRAM/Flash 均未因源验证而接受。R00／R01／R02 方框保持未完成。
