# 双 138K v28 完整物理结果

两板完整综合审计通过，并各自完成 P&R、产生位流；**尚未时序闭合，不放行 SRAM**。本阶段未识别、连接或操作板卡，未写 SRAM／Flash。逐项来源、配置、输入、位流、资源、STA 与失败证据哈希见[机器可读记录](DUAL138K_TASK3_PREBOARD_V28_20261108.json)。v27、task2、单板和历史回退保持。

| 板 | v28 候选后缀 | UserCode | 完整综合门禁 | 物理 BSRAM / CLS | setup / hold / recovery / removal (ns) |
| --- | --- | --- | --- | --- | --- |
| M A11 | `87dfef2ac623ccd3` | `D21108AB` | 26/26 | 253/340；61172/69120 | −4.013 / −1.957 / −1.500 / +0.278 |
| W B12 | `a01772798a28ac80` | `D21108BC` | 25/25 | 287/340；56291/69120 | −3.028 / +0.042 / +1.608 / +0.281 |

M 位流 SHA-256：`5a7182177dc29372175b4e29c5c08dc9d4ba750fb52c87441b4b6a449d52f68e`。W 位流：`448525897c33d95a6c926564217c684a992806bfd9e4d740cde7f72fdcb21e48`。这些是失败候选的诊断产物，不能当作上板批准。

M 保留交互、统一参数、普通32／矢量8声部、基础音频、本地混响与最终输出；W 实际承担 CNN、手机接收／解码与唯一录音对象。未移除既有 TF／识别／Push、手机 D 模式或录音下载路径。CAP3 持续手机准入仍关闭。

## 修复及实际结果

W B11 的宽区域 GROUP 仍在约束解析时消耗约124.5 GB并被内核终止。B12 改为只约束实际 tag→delay 返回因果锥与已证明的 held FF：128个tag FF、257个返回FF、76个组合原语、280个held FF，共741个。9130个旧原语仍作审阅清单，不再全部放置。单行 GROUP／GRP_LOC 保持全部有限约束和同拍故障语义。B12 1220.88秒完成，峰值进程树 footprint约6.95 GiB，输入无漂移；没有重复旧的内存耗尽。

M A10 在两个49-CFU角区各堆入174个held FF，留下964条未布通网络。A11 保留已成功的 F808 角区，把 PANIC／PCM 放入独立区域，每区最多82 FF；485.08秒完成全部布线。PCM响应／PANIC仍有短hold路径，后续必须依据实际clock skew扩大飞行时间，保持max10/min1.8 ns与原生hold检查。

M 的指定DDR初始化路径 `ddr_init_internal_r_s0/Q → wloadn_3_s0/D` 现为 **+2.429 ns hold**，网延迟4.515 ns，仍保留min0.8 ns及原生clock skew。此项通过不等于DDR或整板全部时序通过。M最差setup是TF会话取消／背压至PCM RAM CEB（−4.013 ns）；effects还有expected-generation关键路径。DMA大数据寄存器CLEAR的功能recovery仍为−1.500 ns，不作false-path豁免。

W最差setup现为DDR recording read-pointer至`raw_store/completion_committed`（−3.028 ns，数据12.963 ns，10 ns周期）。其余三类最差STA均为正；仍须修复setup并完成物理CDC／PLL审计。

PLL初次调用缺少`GOWIN_SIMLIB`，已用安装版gw5a公共模型重新运行，DDR来源／配置审计成功执行。M仍被拒绝：视频／CPU PLL控制传播10.673／10.025 ns，超过10 ns预算；另有当前M本域grant释放结构和物理SDC与旧DEMO审计匹配问题，须按实际网表与封存选择补齐证明，不能忽略或伪造通过。W物理PLL审计运行中。

## 验证与下一步

v28编译输入与v27完全相同，严格复用七项综合产物；完整综合审计重跑。针对实际网表的7项floorplan/消费者/clock/reset破坏控制通过，一项需要另选routed W的可选测试未运行。footprint监督器经64 MiB分配子进程验证，统计本次进程树及压缩内存，12 GiB或1800秒停止；历史记录不修改。

下一轮依据上述真实路径修复：M有界PCM暂存、效果／事件路径、载荷hold和DMA复位分布；W录音返回与完成计数；PLL传播与当前preboard物理证明。缓存中的向量包络snapshot实验只有局部逐拍与独立综合证据，尚未选入候选，不算整板改善。

准备入口仍为`build.py --prepare-custom-board --workstation-profile custom138k-workstation-task3-{m,w}-preboard-v1`，依赖与物理运行输入见JSON。正确目标板、串行JTAG、连接、身份读回、回退与功能步骤见[简短SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。真实LCD吞吐、DAC延迟与整机演示留到另获授权的上板验收。
