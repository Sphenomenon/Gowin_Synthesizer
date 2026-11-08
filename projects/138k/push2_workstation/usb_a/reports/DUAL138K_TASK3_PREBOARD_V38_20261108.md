# 双138K task3 v38 物理检查点

本阶段两板均完成完整 P&R 并产生位流，但**仍未通过上板前门禁**。源码／完整综合沿用不可变 [v37](DUAL138K_TASK3_PREBOARD_V37_20261108.md)：M `33632cd650f42875`、W `f4d596b8e1744006`，综合审计29/29、26/26通过。逐项配置、输入与网表见该报告；本次完整物理结果、证据路径和SHA-256见[JSON](DUAL138K_TASK3_PREBOARD_V38_20261108.json)。未连接、识别或操作板卡，SRAM／Flash未写入。

| 项目 | M A14 | W B13 |
|---|---|---|
| 物理身份 | `custom138k-resource-physical-D21108AE` | `custom138k-resource-physical-D21108BD` |
| UserCode | `0xD21108AE` | `0xD21108BD` |
| LUT／ALU／寄存器 | 70509／19193／58680 | 58522／16470／46758 |
| 物理BSRAM | 253/340 | 287/340 |
| CLS | 61209/69120 | 56308/69120 |
| PLL | 6 | 4 |
| setup | **−4.526 ns** | **−2.670 ns** |
| hold | **−0.282 ns** | +0.143 ns |
| recovery | +0.642 ns | +0.682 ns |
| removal | +0.278 ns | +0.372 ns |
| PLL／启动专项门禁 | **失败**：ICPSEL[0] 10.092 ns > 10 ns | 通过 |

位流均在缓存 `/Users/sphenicidition/.cache/gw138k-task3-20261108/` 下，文件为对应目录中的 `impl/pnr/custom_138k_integration.fs`：

- M：`m-preboard-physical-v14`，SHA-256 `b4f91f783af94ce29f1d2babd9659e2edfe246a7c1f98edd3c9be309598d97cf`。
- W：`w-preboard-physical-v13`，SHA-256 `2756d6b552a89ab08ec84dc072ae786520808ec2b35dfff63a65c1e333b4c213`。

## 本轮修复及复用范围

M A12把功能复位误标为CLK，被CT1014拒绝；A13同时约束正相LOCAL与反相SR，因工具把两者视为同一对象被CT1000拒绝。A14仅将实际反相复位 `u_managed/runtime/n184_6` 分配LW11/SR，逐网表确认891个CLEAR、2个PRESET和4个RAM RESET，保留真实时钟LW8/9/10。目标测试覆盖断开时钟输入、复位反相器和实际负载的拒绝，RTL及SDC未改。A12/A13失败证据保留。

A14成功解析CST并完成P&R。功能memory reset recovery已转正；指定DDR初始化hold在原min0.8ns下为 **+2.486 ns**。全设计hold仍由其他载荷路径失败，不能宣称hold整体关闭。严格5ns注册Q到PLL控制约束保留，完整10ns传播门禁仍拒绝10.092ns路径。

两板编译输入仍为v37完整综合。M复用了29/29完整审计，并以 `m-A14-synthesis-evidence-reuse-review.json` 核对仅物理测试方法变化、所有综合门禁可执行代码／编译输入不变；原审计未改，不宣称新增完整综合。物理输入在各运行期间未变。v37源码锁保持不可变，本次物理适配由本报告同一提交中的helper/test字节、准备收据与物理清单绑定；最终交付仍须重新封存源码配置并验证复现。

## 最新实际故障及下一步

1. M最差setup从 `input_owner/audio_online` 经生命周期、PANIC、统一参数及事件队列room反馈到 `settle_wait/CE`，13级逻辑，数据17.318ns；另有peer identity经录音仲裁到TX载荷的21级路径−4.435ns。下一步须在所属事件／端点模块切断长就绪反馈，保持同一取消边界和参数owner。
2. M PCM response载荷hold−0.282ns、PANIC载荷hold−0.203ns；有限1.8ns最小延迟与现有时钟检查保留。PLL ICPSEL[0]传播仍超限，须定位真实路由。
3. W原完成计数终点不再最差，但setup仍失败。最差为delay FIFO标记到看门狗CE，8级逻辑、数据12.478ns；第二为录音tag队头校验经原生故障反馈到completion_code，−2.655ns。已在缓存对照验证延后一拍计数、保持原故障周期的看门狗原型：6种超时、429输出位和计数对应关系通过，含X/Z输入；**尚未改生产源码、尚无物理通过结论**。
4. W保持PLL／启动专项通过；两板完整外设／TF FIFO尾部等必要routed CDC仍须完成，不能用专项代替完整验收。

继续根据上述实际路径修复、针对性验证，再统一完整构建。CAP3持续手机接纳保持关闭；真实LCD吞吐、DAC延迟和整机演示留到上板阶段。回退为源码`56da7e70`与历史v28物理证据，task2、单板和冻结候选保留。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仅准备步骤；这些失败候选不得加载。
