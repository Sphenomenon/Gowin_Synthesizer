# W11 默认与 far 完整物理结果

2026-11-01。候选 `custom138k-workstation-w-demo-v1-bafd43c180d52b1c` 的645封存／284启用输入、综合网表和两份完整物理输出均重新核验。profile artifact SHA256 为 `156837d00ea51374c0e0a1708fc583af10cadb8f35594edf528be0492dc5b4b0`；封存配置SHA256为 `dd1548d062a71244dc4590481bec8599e6cbc741b1c0c06d8c52b2a609fab35b`。实际消费前阶段的新PCM、录音事务许可及HCI身份源码，未消费后来M13的共享音频修改。

| 完整物理候选 | 默认 `D2110101` | far `D2110102` |
|---|---:|---:|
| setup违反端点／最差ns | 6,423／−5.018 | 6,394／−4.648 |
| hold违反端点／最差ns | 2／−3.675 | 11／−0.585 |
| 原DDR3.500ns路径hold余量 | −3.675 | +0.673 |

默认实测Logic71,157、LUT54,725、ALU14,644、FF45,091、CLS52,251、物理BSRAM293／340、SSRAM298、DSP67.5；这些是实际物理数，不与综合BSRAM equivalent257混用。两次P&R均退出0并生成位流，但完整时序均失败，禁止作为已通过镜像或硬件接受。far资源详情及全部STA字段见机器报告，未以默认数字代填。

默认位流SHA256 `2cd14d6de414d864fbe497348ff2b2a92546626fc440b49f6222412fe0ac8342`；far位流SHA256 `61ed0b30ea61214dad99dcb06004ccf3898333feeea1cac48e6ef21b0a95ad88`。far严格由本次默认测量派生，仅追加既有审核的DDR launch／capture区域约束，VG及完整SDC逐字节不变，原3.500ns不降低。

默认与far各自实际VO的native CLI／完整SDC、54项测试（41通过、13不适用跳过，36变异拒绝）、完整DEMO边界7项／61负控、官方GW5A simlib PLL及self-test的7负控通过。所有工具、输入及输出前后hash稳定。这些局部门不代替全局时序。外部完整汇总SHA256为 `fc09d53cdc514e9db4bd16e485075c714f98f9bf3fc4ca226a93e61ae7c7ff0f`；[机器报告](dual138k_w11_physical_20261101.json)固定来源、各次资源／时序及完整证据引用。

下一项实际阻塞分别为：PCM的32位physical epoch串行比较到位图宽清理；录音返回tag／timeout反馈到START宽初始化；HCI的12位handle与32位generation串行比较到pending／token。新源码修复单独验证后进入W12，W11输入不再改写。far剩余11个hold均为参考时钟监视器的同域binary／Gray路径；最差skew1.008ns、数据0.448ns，不能作为异步CDC豁免。两类全局时钟资源均已实用8／8，不能假定增加全局缓冲有余量；下一布局须继续实测。

只读硬件核对发现一个有效138K：JTAG接口8257读得ID `0001081B`、UserCode `C11028E5`、Status `00022020`；同一FTDI的8258接口全FFFFFFFF，不计第二块板。未下载、复位、打开UART或写Flash。当前无外部HDMI采集或线路音频输入；手机仅有模拟器，真实A2DP／BLE验收按用户安排稍后进行。本轮物理位流没有上板，回退仍是原板内镜像；同板分时与双板并发验收均未发生。
