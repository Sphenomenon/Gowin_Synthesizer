# R00 无本机屏配置与来源闭包（2026-10-30）

用户确认本轮暂缓 LCD、触摸和 Wi-Fi，使用 HDMI 与 Push／25K。新增显式 `custom138k-workstation-r00-no-local-panel-v1`，保留 R00 owner8、双率音频、三效果、HDMI、USB 显示、TF 与 BLE。原三个 profile 的 LCD 选择继续启用；accepted／pinned 输入不改。宽 tag RAM 的独立功能、故障注入与 helper-only 资源结果见[tag RAM 源码阶段](WORKSTATION_RUNTIME_TAG_RAM_SOURCE_20261030.md)。

新 provider 在限定宏作用域内包裹原 R00 provider，不复制业务实现。只退役 `workstation_lcd`、专属 31.5 MHz PLL／复位／快照 CDC 及源文件，21 位 LCD 输出固定低，背光关闭；仍保留已核对的物理引脚约束。准备端、时钟审计与输出审计共用显式选择，旧配置默认 true；关闭路径拒绝残留 LCD 层次／时钟，并检查实际 GND→OBUF。原四 provider 的有效预处理 token 身份受独立回归保护。

维护复位工具同时安装精确的三 CLEAR 约束，只覆盖 `u_native_usb/audio_owner_reset.release_q` 三只同步器自身的异步断言／释放输入。末级 Q 到 12 个功能计数寄存器及 11 个下游 release 寄存器的路径不加新例外，级间 Q→D 继续计时；source／结构／负控不等于物理 recovery/removal 已通过。shared 审计新增严格 R00 与无本机屏模式，固定配置、来源与实际网表身份，旧 generic／no-CNN 策略保持；新录音 CDC 不在该 88 行范围内。

四份配置锁各含 367 项版本化输入，真实 prepare 和逐份来源检查通过：

| 配置 | 新候选摘要 | staged / enabled |
|---|---|---:|
| 原 enabled | `0bdda0d0c8914b9b` | 571 / 260 |
| 原 no-CNN | `0b301f5739f0cb48` | 572 / 260 |
| 原 R00 | `86893249ca9da0a2` | 584 / 267 |
| R00 无本机屏 | `e855a1e8a8e6f181` | 584 / 266 |

前三份相对各自上一阶段仅四项 staged 字节变化：tag helper、共享 top 两份副本、SDC。去掉新增三 CLEAR 行后 SDC 与前序逐字一致。无本机屏与本阶段 R00 对比仅增加独立 provider、移除 LCD 源，修改 GPRJ 编译选择和 SDC；不把未选择的依赖当成已编译功能。全部输入哈希、差异和测试日志身份在[机器记录](workstation_task_20261030/r00_no_local_panel_source.json)。

本阶段记录 142 项无跳过检查，包括四份来源各 12 项、profile 20 项、R00 7 项、新配置 6 项与篡改、no-panel precision 8 项、panel 8 项、reset 9 项、accepted 来源 17 项，以及时钟／旧 R00 与 no-CNN shared 检查。时钟工具测试初次因 PATH 无 `gw_sh` 在进程启动前失败；综合完成后显式选实际工具重新通过，三项纯源码检查另列。旧 R00／no-CNN 的实际网表检查仍只属于其原候选。

新配置已另建逐字核验的不可变综合副本；其后发现的 PCM reply consumer closure 和 shared `flags_meta_3` 别名检查均按失败保留，不能因源码／prepare 通过升级为全部 CDC。新综合、资源、实际端点与后续物理实验分别记录；本报告不宣告整机资源净收益、路由、时序或硬件通过。无 SRAM／Flash 操作，不改变既有部署身份；相关整机任务方框保持未完成。源码回退使用原显式 R00 profile，并按其实际输入重新验证，不能把改过源码的新候选称作旧验收版本。
