# I2S 音源保护窗口与真实 D 链路验证（2026-10-31）

修复 `workstation_i2s_serializer.sv` 对明确源撤销的分类及 running／prefill 状态，保留全部物理输出时钟与完成 slot。生产文件 SHA256：`abd0c52bfa1f638ff1c88ae449bd912e92a9a9148753d18d1260f232af3bf8a6`。未改变音源取消、公共参数或数值函数的采样时间。

原 D 测试在新旧完整 `d_process` 函数下都失败，12个PANIC相位没有任何underrun增量。逐次日志确认：每采样率在owner开始／退出时各有2个source guard槽，被主动撤销的预取PCM误计为deadline underrun。每个局部流4次，48→44.1切换会复位该计数，整轮实际8次；最终汇总只显示最后局部流的4次。

本次保留连续PCM时间线：当前串行帧完整结束，受阻及guard槽继续输出PCM0＋error并递增sequence，作为明确源撤销累计 `source_error_count_o`；未受阻slot真正缺样仍原样累计 `underrun_count_o`。保护期间旧完成帧不会重新报告running，旧预取不会报告prefill，迟到响应仍消费并拒收；guard结束后仅新匹配返回恢复有效PCM。源撤销错误帧仍然存在，录音／分析须按原契约处理，不能称为无错误帧。`PCM_FRAME_CONTRACT.md` 已记录该语义。

验证结果：

- 新source-hold独立测试在48k／44.1k各覆盖bit3／24／51三种开始相位，逐位检查BCK／LRCK周期、完整旧帧、PCM16／padding及完成tap，连续53个完成帧；每rate保留24个源撤销zero/error槽，再故意漏掉一个真实render，产生恰好1次underrun。每rate28个good与25个明确error。旧serializer在完全相同bench因保护中running／prefill冒脉冲失败。
- 真实 D 的 APB／CDC owner→完整效果→一次主音量→实际DCS／I2S输出链通过：1918个物理完成帧、1913次原函数 `core_ce` 对比、1917个显示快照与已完成I2S身份／PCM／error逐项一致；12次正式USB PANIC（10次in-flight）通过。每rate143个dry、32个drive、32个crush、547个wet帧，最终underrun为0；fault／各drop／display fault／deadline miss均0。相同修复配完整旧数值函数重跑，得到完全相同指标。
- 通用AE350 runtime重新通过：1454帧、1436个good、18个明确error、119个原PCM、37个半音量PCM、9次history clear及446个wet product；保留MIDI、CPU／HCI fencing、TF、两采样率。
- 既有serializer、AE350 boundaries、两种振荡器offset的真实frame bridge，以及默认PDN4／startup1028的clock＋I2S测试全部通过。后者覆盖48→44.1→48、4个局部流34帧、真实CDC排空／预填／running及失钟恢复。

测试完善过程中的失败也保留：最初chorus历史不足、USB lifecycle fixture缺少valid／data握手、第二rate未先经真实命令恢复dry，均只修改测试；随后严格underrun断言才定位上述生产缺陷，断言未放宽。所有日志、结果JSON、输入身份及失败路径见同名JSON。

本报告证明离线模型中的正式APB／DSP／串行及显示快照一致性。DDR为有序模型、时钟为理想振荡器；不等同真实HCI／SBC／A2DP输入、HDMI像素、实板DAC、录音手机下载、P&R或硬件验收。新候选必须重新保留实际资源、时序及位流身份。撤回修复须恢复原serializer并重新构建，不能复用已改变输入的候选身份。
