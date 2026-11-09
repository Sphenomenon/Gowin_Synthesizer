# v118：两板完整布线，时序仍未放行

本阶段完成两板可复现的源码准备和完整布线，**上板前目标仍未完成，禁止加载当前位流**。配置、完整身份、位流 SHA-256、资源和原始证据哈希见 [JSON](DUAL138K_TASK3_PREBOARD_V118_20261109.json)。没有连接或操作板卡，没有 SRAM/Flash 写入。

| 项目 | M | W |
| --- | --- | --- |
| 完整源码候选后缀 | `d901b4429953ecb6` | `7f0b1ee68e9a102b` |
| 完整综合审计 | 32/32 | 30/30 |
| 独立 prepare 暂存字节复现 | 753 文件通过 | 741 文件通过 |
| 综合 FF / LUT / ALU | 54327 / 67168 / 17959 | 46949 / 58166 / 15925 |
| 综合 BSRAM 等效 / SSRAM | 217 / 235 | 253 / 779 |
| 物理结果 / UserCode | v39 / `D21109E7`，完整布通 | v38 / `D21109E6`，完整布通 |
| 物理 Logic / Register / CLS | 87266 / 54327 / 59706 | 79344 / 46949 / 55913 |
| 物理 BSRAM / DSP | 263/340 / 148.5/298 | 287/340 / 122/298 |
| 全局 setup / hold / recovery / removal，ns | **−4.690 / −0.223 / +1.722 / −0.146** | **−2.144 / +0.135 / +1.151 / +0.287** |
| 显式 setup / hold 最差，ns | **−1.965 / −0.223** | +0.354 / +0.285 |

M 五路 `/147` 显式选择完整的版本化倒数乘法实现，原 restoring 源码和其他配置保留。32/42 位的全输入整数证明、8 种宽度/tag 组合、flush/复位、真实普通32和矢量8引擎周期对照通过；最终 Gowin 网表结合厂商 primitive 模型验证商值、tag和固定延迟。真实普通32覆盖6612帧和34次PANIC，矢量8覆盖708帧和40次PANIC。相对 v106 完整综合减少2994 FF、2043 LUT，增加5块综合BSRAM等效及14个MULT27X36。M v39用516.89秒完整布通，输入未变；旧v36的2309条未布通结果保留。

M 新综合的150个变化逻辑状态通过reset-inclusive next-Q对照，另核对23个归纳条件和28个SDPB地址位；新的v17消费者清单保留v15/v16。此为明确条件下的named-state/memory-output对应证明，不宣称整机归纳。CANCEL的11个实际复制FF经D/CE/CLEAR/CLK/INIT及破坏反例核对。前阶段M cache raster和W CANCEL/admission改动见[v106](DUAL138K_TASK3_PREBOARD_V106_20261109.md)。

W 新原生CNN retirement边界保留native acceptance边沿，下一拍才退休请求FIFO，busy禁止重复head，完成数据保持到completion FIFO接收。完整映射审计证明260个next-Q方程，不使用内部控制cuts；原先DDR tag→CNN请求FIFO退队的失败路径已切断。v118仅更新审计来源，完整编译输入及顺序与v113一致，复用原综合。重新独立生成物理输入，VG/CST/SDC逐字节相同，UserCode及归一化P&R脚本也相同，故复用v38物理结果，没有重跑相同输入。v38原冻结父身份`1aa062c5dfdbec7a`保留，未刷新旧锁。

两板独立prepare的候选身份及全部暂存字节一致。M元数据也逐字节一致；W保留目录相关固件诊断元数据差异，不声称全部元数据相同。17项当前来源检查通过，复用输入未变的真实音频/显示/取消/CNN回归。W实际physical-reconstruction测试复现2211个逻辑单元和8个排除RAM，拒绝11个破坏反例。

剩余故障直接取自新STA：

- M：PCM描述符位图校验→overflow CE为−4.690ns；PANIC分发→参数/普通声部、TF尾帧控制、效果故障门控和手机batch回复也有负setup。两组保持邮箱有hold违规，显示复位有removal违规。DDR `read_rclksel_conf`→DQS及部分release链的显式max也失败，不能仅看全局recovery为正。物理PLL/held审计另外停在改变的memory-reset消费者清单，尚未通过，未放宽检查。
- W：DDR tag→即时transport fault→延迟DMA状态为−2.144ns；录音ingress身份检查→真实录音结果为−2.138ns；raw-store completion、fetch地址及endpoint TX也有负setup。全局及显式hold为正不代表setup闭合。

当前位流仅保存失败证据：M SHA-256为`6b83b883e39f5c1796b9f026b5817dc8779987009b47d564e65fbb1d79525761`；W为`65314574b41ccba2a1171900376dce07ae7b36cd7a6056e3d542afbc9a9f0971`。完整路径在JSON中，生成数据库和位流留在外部缓存，不纳入源码。

复现使用现有`build.py --prepare-custom-board --workstation-profile custom138k-workstation-task3-{m,w}-preboard-v1 --custom-board-output <新目录> --netlist-dir <三份锁定PCB网表目录> --riscv-prefix <GNU工具前缀>`；保留描述符的原配置，不追加速度或时钟选项。随后运行`tools.workstation_custom_board_audit`。完整物理配方、旧参考CST和所有输入哈希绑定在JSON所列`physical_inputs.json`中。task2、单板、冻结基线、v92/v106及其他历史候选均保留。后续须用修复后的新身份完成全部资源、时序、CDC/PLL和复现门禁，[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仍为待放行步骤。
