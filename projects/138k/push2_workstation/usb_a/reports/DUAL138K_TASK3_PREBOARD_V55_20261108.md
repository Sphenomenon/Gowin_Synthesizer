# v55：W routed 消费者证明修复与实际时序结果

M **29/29**、W **26/26** 完整综合审计通过；本轮仍未完成物理门禁，**不得加载 SRAM**。没有访问板卡或写 Flash。分工保持 M 交互、唯一参数、普通32／矢量8声部、本地混响与最终输出；W 实际 CNN、手机接收解码及唯一录音对象。

| 板 | 完整候选身份尾号 | 配置 SHA-256 | 综合 BSRAM 等效 |
|---|---|---|---|
| M | `6ae12e44a093b56a` | `8599cb847780a6f003e7d436f4bbd5f31e400ef3d9f5897cbaa91bdba2be697d` | 212 |
| W | `c031a4198f2ae893` | `1d68cb8dc608edb6cb59842af0554b3491f2066912b8866f77b0131144377321` | 253 |

两板各在两个独立目录 prepare，M 730、W 718 个全部暂存输入逐字相同，源码快照及 USB／AE350 固件 ROM、二进制、ELF 身份一致。v54→v55 只变更已锁定的证明工具，编译输入完全相同，严格复用综合后重新通过完整审计；没有重复运行输入未变的完整综合。此处证明源码和编译闭包复现，不宣称位流逐字复现。

W flat routed VO 没有层次 frame，旧审计错误地在层次 scope 查 `read_fire`。现在仅在全扁平网表解析精确转义根路径，部分扁平或歧义连接仍拒绝；保留唯一驱动、非恒定及完整有效 next-Q 证明。实际 routed FIFO 的 binary D、Gray D、首级捕获 D 破坏及部分层次负控制全部拒绝，3项定向测试通过。实际 paired-held、raw-command、raw-completion 和修正后的 receiving-synchronizer 子门通过；这些是选定边界检查，**不是完整 physical CDC 验收**。

W v16（`D21108C3`）完整 P&R exit0，1248.05秒；原始 v51 来源与 v55 编译字节由严格复用收据关联。物理 BSRAM **287/340**、CLS **56980/69120**、Logic **81013**、FF **46764**。位流 SHA-256 为 `ca7e0d06822d6aea62fbe675b390a2a644827c1d616af04b712f954e3aca7be9`；PLL 检查通过，但以下 STA 失败，位流仅作失败证据保留。

| setup | hold | recovery | removal |
|---|---|---|---|
| −3.029 ns | −0.040 ns | +2.573 ns | +0.284 ns |

DDR 中部功能复位修正令 recovery 从上一版 −0.527 ns 转为 +2.573 ns；保留初始化 min0.8 ns、实际 hold 及功能 CLEAR 检查。仍有三类实际 setup 长路径：录音仲裁 read-pointer→故障→raw-store pack/fetch 控制；delay FIFO→DMA watchdog；config session→录音 ingress→result payload。hold 为 raw status payload→fetch_fault；未添加宽泛例外。

M v17（`D21108C2`）仍有2416条网络未布通，BSRAM253/340、CLS60473/69120，无有效位流及最终 STA；v18 增量放置对照失败后退役。不会用失败 P&R 的资源统计代替时序验收，也不继续无诊断的路由参数轮换。

针对 W pack/fetch 的缓存内同拍故障选择实验已通过六组双时钟顺序对照和8192个任意二态／四态边沿；尚未选择为生产输入，隔离综合结果另行记录。下一步先核对实际组合链改善，再决定接入与重建。

[结构化证据](DUAL138K_TASK3_PREBOARD_V55_20261108.json)绑定全部新身份、审计、复现比较、routed 结果及日志哈希。334项历史配置／基线再次逐字核对不变，额外 task2 清单继续引用 v54 证据；task2、单板和历史回退保留。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)继续未放行。真实 LCD 吞吐、DAC 延迟和整机演示留到正确目标板的上板阶段。
