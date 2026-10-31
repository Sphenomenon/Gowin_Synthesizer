# 回放元数据 BSRAM：完整原生候选综合对照

固定源码 `d745697`，实际候选
`custom138k-workstation-ae350-business-v1-1a806f236eaef843`，614 staged／272 enabled。
保持 ILM／DLM 各64 KiB、启动 ROM64 KiB、PLL_R0 与独立 RTC 的原配置。
实际 Gowin V1.9.12 综合退出0，耗时368.985秒，全部输入前后保持。
对照为[固定 RTC 整机综合](WORKSTATION_AE350_BUSINESS_RTC_SYNTHESIS_20261031.md)的
`0981b403bb531b2b`；两份614项 staged 库存仅两个编译 RTL 及它们的两个来源副本不同。

| 综合资源 | RTC 对照 | metadata BSRAM | 变化 |
|---|---:|---:|---:|
| Logic | 97,375 | 97,095 | −280 |
| LUT | 78,754 | 78,715 | −39 |
| ALU | 16,767 | 16,766 | −1 |
| RAM16 | 309 | 269 | −40 |
| Register | 62,876 | 62,883 | +7 |
| 综合 BSRAM | 245 | 248 | +3 |

实际 VG 的 `g_block_metadata.ids/times/sizes` 分别为一块32／32／16-bit SDPB，
同一50 MHz时钟、32槽、完整写掩码、同步 bypass 读，复位端无效；三个存储模块内
没有分布式 RAM。Logic 按 LUT＋ALU＋6×RAM16 计算，不等于物理 CLS。
本次148条原有警告保持，无 AG 组合环诊断；VG SHA256为
`903cd61c606b6419bd45ee2004b3e9d93520509d2e6cdb2ee4654ca52e0cf916`。

真实新 VG 的时钟回归5项／28个负控、最终 PCM/context 的两项正向与已安装约束
边界检查通过；RTC回归13项中10项通过、3项显式外部前置跳过。
RTC保持寄存器直连唯一不透明 `RiscV_AE350_SOC/rtc_tick`，这里只授予综合网表可见
边界证明，没有看穿加密硬核或取得物理 RTC 接受。层次资源加法与HTML总量一致。
完整旧 native 审计器仍拒绝新 runtime 身份／层次，未把它记为功能门禁通过。

综合工具额外产生 `Prj1.gprj.user`，故 prepare-only verifier 不能直接接受综合目录。
原 prepare 已独立验证，全部登记文件与复制前库存另行逐项哈希，额外文件保留。
前序 parser等价／官方 SDPB／C-APB 功能证据继续引用
[主树复验](WORKSTATION_CPU_REPLAY_METADATA_BSRAM_MAIN_20261031.md)，组件资源另见
[同功能组件综合](WORKSTATION_CPU_REPLAY_METADATA_RESOURCE_20261031.md)。

父级包 `~/.cache/gw138k-task-20261030/native-business-metadata-full-parent-v1`
保存456份源码快照及1382个外部文件身份，seal
`9ed551d5fae1a8acaf438c896b879623522a4575f3287c0f939cd34bf728153f`，
独立 verifier通过。机器结果见
[cpu_replay_metadata_full_synthesis.json](workstation_task_20261030/cpu_replay_metadata_full_synthesis.json)。
尚无该身份的P&R、物理BSRAM／CLS、routed STA、完整CDC／PLL、CPU服务期限或手机
音频接受；没有位流、板卡操作、SRAM或Flash部署。回退使用固定RTC对照的来源及配置，
不改旧候选或把本次综合结果转授给后续共享HCI／CPU解码配置。
