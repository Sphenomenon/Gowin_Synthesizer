## 最终资源核对

比较基准：`timing_p27_uart_cdc_route1_20261018_142516_456857`。新候选：`resource_rework_final_route0_20261020_041042`。两者均使用完整工作站顶层。

| 同口径资源 | 旧 | 新 | 变化 |
|---|---:|---:|---:|
| SYN BSRAM | 217 | 197 | -20 |
| PNR 物理 BSRAM / 340 | 262 | 234 | -28 |
| 剩余物理 BSRAM | 78 | 106 | +28 |
| PNR Logic | 77097 | 80167 | +3070 |
| PNR Register | 43450 | 45499 | +2049 |
| PNR CLS | 54862 | 56275 | +1413 |
| PNR DSP | 157.5 | 155.5 | -2 |

物理 BSRAM 净减少 **28 块（10.69%）**。下面按互不重叠的叶节点核对，既不重复累加父子层级，也不以综合网表数代替物理数。

| 物理 BSRAM 子系统 | 旧 | 新 | 变化 |
|---|---:|---:|---:|
| CNN feature cache | 32 | 5 | -27 |
| Viterbi | 9 | 8 | -1 |
| Recorder packets | 6 | 6 | +0 |
| LED score cues | 4 | 4 | +0 |
| Video scanout | 16 | 4 | -12 |
| Reverb | 8 | 20 | +12 |
| Chorus | 4 | 4 | +0 |
| Other retained RAM | 183 | 183 | +0 |

完整工具报告、物理网表和文件哈希见 [资源对照 JSON](resource_comparison.json)。所有本轮构建均未烧录；资源节省不等于时序闭合或板上验收。
