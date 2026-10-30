# 运行时 tag RAM：源码与离线回归（2026-10-30）

共享 `workstation_runtime_div147` 的宽 tag 已改为同步读环形 RAM，维护 helper、扩宽测试台及地址负控已进入主工作区，并通过便携算术／消费者、1028-frame 生产启动和完整 I2S 回归。本阶段完成源码与对应离线验证；没有新的整机综合／P&R、硬件接受或部署。逐文件源码、全部测试输入、工具与证据哈希见[机器记录](workstation_task_20261030/runtime_tag_ram_source.json)。

`TAG_WIDTH>=32` 使用自由运行游标，RAM 深度严格大于商级数，读地址为当前写地址减商级数；小 tag 保留寄存器路径。游标每拍前进，使空泡不改变固定延迟；42-bit 除法仍在 edge18、32-bit 仍在 edge13 返回，不加末级 tag 寄存器。除法算术、valid 与 quiescent 规则保持。reset 清 valid 与游标，flush 清 valid；RAM 旧内容不复位，但只有对应 valid 成立时可消费，invalid payload 不承诺保持。当前 helper SHA256 为 `359350552b6aa00a512068bd68a35cda7a15fad52faf5b23a0f91a893eca1d63`。

| 本阶段维护文件 | SHA256 |
|---|---|
| `rtl/audio/workstation_runtime_div147.sv` | `359350552b6aa00a512068bd68a35cda7a15fad52faf5b23a0f91a893eca1d63` |
| `rtl/audio/RUNTIME_ARITHMETIC_PIPELINE_CONTRACT.md` | `ab751dd7f8b3c65e0c1b33839a04751867b1908093e0de7382a2bc6a1f269e74` |
| `sim/audio/run_runtime_arithmetic_pipeline.py` | `792044e9e782c8f0779ed7caedca1862d982cbba143c96f1f291868aaa5be2fc` |
| `sim/audio/tb_runtime_div147_independent.sv` | `c0caa0bd46cfea4d762d3703210716cc5da739b1f15d82ed9a8c9893bcadc940` |

便携回归从版本化 `resource_rework_route0` 重建锁定依赖，仅逆向经过哈希检查的 arithmetic provenance 尾部取得旧算法 oracle，不依赖私有冻结工程。8 组 helper 配置覆盖 8～80-bit 输入及 16～161-bit tag、完整高位随机输入、环绕、空泡、reset／flush。5 个 helper 负控和 4 个消费者负控均编译成功并被相应 oracle 检出，新增 ring-address+1 错误命中 tag 不一致。oscillator 672 帧／606 非零、688,128 slot 检查、34 次 PANIC，48／44.1 kHz 的 A/B/C 最大延迟仍为 69／165／1061 clocks；vector 664 帧／524 非零、6,368 voice／19,104 coefficient 检查、40 次 PANIC，最大 284 clocks。oscillator 编译有 4 项既有 UNSIGNED 告警，vector 无告警；不是“全部工具零告警”。

独立封存原型另通过不用 valid 移位或 RAM 地址方程的 due-cycle FIFO oracle：8 组配置、每设计 38,794 个输出、56 次边沿间 flush、40 次边沿间 reset，并覆盖所有 tag 位 walking-one／zero、完整 80 位随机输入及 latency=32 的深度边界。4 个独立负控均检出。原型 SHA256 为 `e1a87ccf4de3b89594e18a33ca71ba898c3949c432dbb017de6ca494e9904837`；已精确核对，它与维护 helper 仅有一行说明注释差异，没有 RTL 行为差异。封存 `REVIEW_SEAL.json` SHA256 为 `4d646cce86bcd45cb9a0828a0573ebd996155c9597d20282d1ddfdeb7d1b5f7e`。

1028-frame 生产启动回归检查 211 帧，全部正确、127 非零、无错误帧或故障，跨一次帧中采样率切换；最大 render／slot 为 1168／1197 clocks。完整 I2S 回归检查 20,192 帧，其中 20,186 正常帧、20,061 非零，8 次帧中切换，最大 render／slot 为 1204／1229 clocks；有 6 次 loader 重叠、768 个压力事件和 26 次 Note Off，两率三效果及 FDN 覆盖保持。6 个错误零帧来自主动 TF 采样率不匹配，5 次 fault 来自主动丢钟／媒体及 owner6 fence 超时；测试核对标签、静音、隔离与恢复。analysis／record 的丢帧计数来自主动背压消费者，通知均被核对。serializer request drop、render deadline、pitch／MIDI overflow 和 note drop 均有持续零值断言，不能把这些异常计数抹去后称“零错误”。

两项 composition 回归均使用真实 DSP、时钟事务与官方 DCS、owner6 DMA、最终 PCM、跨域 bridge、串行 I2S 及 taps；DDR 为有序功能模型，TF 为一致包 fixture，切换授权由外部测试策略给出。没有 CPU 命令或完整顶层／profile 选择接受。两项共有 70 个输入，source-set 为 `1404aafd7312401d80487e2867675f3ef2c783e2e972ae6950ade828df8593a0`，composition 身份为 `native-runtime-audio-offline-v1-nonzero-1404aafd7312401d`；prepare 参考 `custom138k-workstation-r00-v1-2030fdf7a01ba140` 仅供锁定依赖，不能改称本轮新整机候选。composition／fixture 自身告警为零、无 UNOPTFLAT；依赖层的已记录告警保留在机器记录中。报告写入前重算便携 24 项、启动和完整 I2S 各 70 项输入，均无漂移。

独立 helper 映射使用全 payload 引脚保持活动的同一 `WIDTH=42, TAG_WIDTH=161` wrapper，旧寄存器版与 RAM 版均综合退出 0：

| helper-only 综合资源 | 寄存器版 | RAM 版 | RAM 减寄存器版 |
|---|---:|---:|---:|
| Logic | 925 | 858 | −67 |
| LUT / ALU | 925 / 0 | 854 / 4 | −71 / +4 |
| Register | 3,886 | 832 | −3,054 |
| BSRAM | 0 | 5 | +5 |

RAM 版真实网表保留 5 个 `SDPX9B`，36-bit 读写端口、`READ_MODE=0`。这些是独立 pitch helper 的综合映射结果，attack helper 未在该实验单独映射；不能外推为整机净 FF／CLS 收益或物理 BSRAM 数，更不能保证 FD 的 2,754 条未布通网络因此消失。该实验未做 P&R、RAM 数据弧／CLK-to-DO 或 STA。原 FD 失败证据保持独立身份。

| 本机 cache 验证记录 | SHA256 |
|---|---|
| `div147-tag-ring-root-regression-v1/verification.json` | `74007becf199a32e362c481860cfceb06b4cf3ce5dc24b6e4609271d14d79f2c` |
| `div147-tag-ring-startup1028-v1/verification.json` | `c1bd6abfb5262a82c08c2d1cffddf7cda458942032642dd2d71783f7990c44c5` |
| `div147-tag-ring-full-i2s-v1/verification.json` | `794271c5278ed3630ef7dc27d4579de206cdc1c72cd30317bb398c6b5d85b912` |
| `div147-tag-ring-mapping-v2/verification.json` | `6ce458c7b24771c10c09f1bc32aa2a6fc6ae3710e03802381a5bc1bad007b4ae` |

上述目录均在 `/Users/sphenicidition/.cache/gw138k-task-20261030/`。下一步须为实际整机重新绑定输入锁与候选，核验宽 tag 实际选入后的完整资源、P&R／所有 STA、RAM 数据弧、clock／reset／CDC／PLL 和功能保持，再单独记录硬件检查。no-local-panel 属于另一阶段，不计入本报告收益。当前无位流，`physical_gates_passed`、`hardware_tested`、SRAM／Flash 写入、`deployment_allowed`、`release_ready` 均为 false；不改既有部署身份。回退源码可定位封存旧寄存器 helper SHA256 `cd45ffd4eb301966956d0acbe233703693ec25e95368679ef0d9ffeb36d17bdc`，仍须刷新锁和重验，不能直接等同于板上回退。
