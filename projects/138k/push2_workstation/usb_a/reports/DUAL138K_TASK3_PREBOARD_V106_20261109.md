# v106：完整综合通过，物理门禁仍失败

两板来源和完整综合已封存，**尚未交付可加载配对**。结构化身份、配置、输入及证据哈希见[JSON](DUAL138K_TASK3_PREBOARD_V106_20261109.json)。未操作板卡、SRAM 或 Flash。

| 项目 | M | W |
|---|---|---|
| 候选身份后缀 | `663347f84112b7f9` | `60e682f7cd950d4c` |
| 完整综合门禁 | 32/32 | 29/29 |
| 暂存／实际编译文件 | 750／289 | 739／202 |
| 源码锁 | 1144 | 1198 |
| 综合 Register／LUT／ALU | 57321／69211／17526 | 46689／58198／15925 |
| 综合 BSRAM 等效／SSRAM | 212／235 | 253／779 |
| 物理身份 | v36 `D21109E4` | v35 `D21109E3` |
| 物理结果 | 2309 条未布通，无完整 STA／可用位流 | 完整布通，setup −1.715 ns，禁止加载 |

M 仅在上板前配置启用现有 validated shared cache 的 native raster admission/lease，退役重复 local capture/alignment；默认 renderer 保留。完整真实 DDR writer/reader/cache 和 1920×1080 对照通过：1036800 beats、2073600 pixels、174960 次停顿、10 个错误反例；spectrum512、XY65536 和默认配置均覆盖。相对前一完整 M 综合减少 678 FF、1550 LUT、291 ALU。新映射的 21 个 CPU release 消费引脚经 reset-inclusive next-Q、原有归纳及 RAM 地址检查后加入 v16 清单；保留 v15 及原失败审计。

W 修复 CANCEL ready 同边沿 cofactor，并选用实际 sample/event admission。实际综合网表回归六项全部通过、无 skip，覆盖 M cancel、TF 108 个 payload CE、W batch/window 及 generation successor 证明、788 个 tag/held 和 2210 个 delay placement 单元及错误反例。既有 17 项来源和三项 cache raster 单元测试通过。

两板独立 prepare 的全部暂存字节和候选身份一致。M 元数据字节也一致；W 有目录相关固件诊断元数据差异，不声称 W 所有元数据逐字节一致。综合复用以完整编译输入闭包为前提：M 复用 v104，W 经 v104 复用 v100，未改 VG。

M v36 P2R0 在 1215.76 秒后 PR0004 退出，输入未变；部分物理报告为 Logic88877、Register57321、CLS59916/69120、BSRAM253/340、DSP120.5/298。未布通结果不能用于 STA 或上板放行。W v35 编译 VG 与 v106 相同，767.38 秒完成布线；全局 setup／hold／recovery／removal 为 **−1.715／+0.140／+2.324／+0.278 ns**。PLL、DDR 启动、held 子门禁及显式有限检查通过，全局 setup 仍失败。

W 最新最差路径为 DDR tag 校验→即时 transport fault→client ready→CNN 暂存请求 FIFO 退队；其余负路径涉及录音 identity fence、raw fetch-end/completion 和发送控制。后续修复以这些实际路径为依据。M 需继续定位拥塞并完成路由，两板均需最终身份绑定的全局／显式 STA、CDC／PLL、资源及复现通过。[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仅为待放行步骤。task2、单板、冻结基线及历史失败均保留。
