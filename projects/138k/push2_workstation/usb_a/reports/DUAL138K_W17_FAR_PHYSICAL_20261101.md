# W17 far 完整物理结果

2026-11-01。`custom138k-workstation-w-demo-v1-518b142532fd5352`的独立far布局`D2110123`完成全量P&R及actual审计，**完整STA失败，未上板**。同源default见[W17默认物理结果](DUAL138K_W17_DEFAULT_PHYSICAL_20261101.md)。

| 实测项目 | 结果 |
|---|---|
| P&R耗时／退出码 | 359.658秒／0 |
| 物理Logic／FF／CLS | 73463／45220／53431 |
| 物理BSRAM／DSP | 293／340；66.5／298 |
| LUT／ALU／SSRAM | 57282／14405／296 |
| setup负端点／最差 | 5696／-5.123 ns |
| hold负端点／最差 | 1／-0.232 ns |
| recovery／removal最差 | +1.803／+0.278 ns |
| pulse width最差／负路径 | +0.580 ns／0 |
| 四张clk50表最差 | -3.708／+0.192／-3.708／+0.192 ns |

VG／SDC和原3.500ns DDR要求保持。CST仅追加两个定向区域，actual launch R104C175→capture R2C2均命中；DDR hold +0.844ns（arrival6.192、required5.348ns）。这个单项通过不转授完整时序。最差setup为arbiter tags[19][3]→raw memory_failure −5.123ns；audio active_generation→written bitmap −5.088ns；clk50 host_rx generation→transport reliable −3.708ns。剩余hold为48k reference monitor reset pipe，−0.232ns，继续按实际端点修复。

原生VO58项47通过、11具名不适用／63负控；边界7／69、官方六PLL／7负控／held-v3和额外返回邮箱4／19均通过。actual VO再次确认9928对真实源／资格消费者10ns与hold-only覆盖，完整native-response映射归纳及physical CDC仍未接受。六标准进程与两项补充审计通过不覆盖STA失败。

主线程重验32个完整物理文件及3277份标准证据，并另对default／far扩展交付各3307／3322份证据重算hash，含完整STA／pulse width和返回邮箱负控。far dispatcher最初schema锚点错误在准备时拒绝、default外围文件数量断言错误的失败均保留；后续只修封存包装器，不改冻结审计、RTL或验收阈值。机器记录见[DUAL138K_W17_FAR_PHYSICAL_20261101.json](DUAL138K_W17_FAR_PHYSICAL_20261101.json)。

位流SHA256：`ba0e1a0f1edb3faf7e039101d4253e595f946811e7c50cb84fe864db3f81713c`。标准root复核SHA256：`d0fe3a5dbcf686cb624608828829fead60cebe3bb41920381a09f5e8f09d1ce2`，扩展root复核`159c05556301d5b0b93e009479df5d601f376ee078066c24443e00f41a074f02`；原始cache为`w17-far-physical-audits-v2/`及`w17-far-delivery-v1/`。

未验收真实HDMI／DAC／25K、手机A2DP／D处理／BLE下载或双板并发。W对象仍16384帧／64KiB，M基础尚无CNN。未执行SRAM或Flash，原板及Flash回退保留；T2-D1／D2仍未完成。
