# W12 完整输入、综合与严格门

2026-11-01。W12 `custom138k-workstation-w-demo-v1-13266a0d74cad8e8` 已完成 prepare、全量综合及完整 strict 门。FF 45,092、LUT 55,357、ALU 14,093、BSRAM equivalent 257、SSRAM 298；相较 W11 的 FF/LUT/ALU 为 +1/+521/−3，不预记物理资源或时序收益。实际 kept group 映射和后续 P&R 另行验证，当前不能部署。

两份 DEMO 的 822 项来源锁各更新六个已验证输入身份：PCM owner、两份 HCI owner、raw store、唯一 raw-store 生产 pin 工具、显式物理派生 helper。没有更改配置角色或默认采用 monitor 区域试验。W12 完整输入 SHA256 `13266a0d74cad8e8b5d6d31519282133847cc419494ef62f3b921ebbe74c0442`，配置 SHA256 `b829315fb364af6bf8f2617db63690445e3be5ccff3223b1a54c8f7b41547153`；951 项来源快照、645 项 staged／284 项启用输入已逐项核验。六项重点 RTL 均在实际启用清单中；已审 raw-store `214c0a5d…09da1d`、PCM `3342a94c…cff837`、HCI `271e3d70…9785ea`／`02dc6825…00787` 真实进入本次编译，广播／chorus 复用 M13 来源。

来源回归 17 项、DEMO 网表审计器回归 15 项、角色策略 7 项通过；prepare 当时 M/W 两个指定 profile 的完整 load 均通过。额外运行的通用历史 profile 测试因非 DEMO 锁中的既有 firmware.c 漂移失败，日志保留，未刷新历史锁。一次误拼不存在的可选测试文件名在执行测试前退出；随后运行实际策略与审计器测试并通过，不将该次命令列为通过。

使用显式 xPack RV32 编译器及安装版 Gowin，综合 207.14 s、exit 0，全部 647 个声明输入（含 manifest／profile）前后哈希稳定。VG SHA256 `e2bc658c7bb33953d2982e863f59d6500cc00f4fd478b60a4ecb6fb7f2977894`；完整来源、功能保全／角色退出、资源、时钟、CDC 结构和 SDC selector／retirement strict 门通过，SHA256 `1b61dae4bb5a1f5702595c707a6357fbcee4923c0eaead0e755ae7180d59768a`。它是综合阶段门，routed STA／CDC／PLL 和真实业务接受仍待完成。

[机器记录](dual138k_w12_prepare_synthesis_20261101.json)绑定配置、六项消费来源、固件来源清单、综合运行、独立审计工具快照及原失败日志。后续音频维护源即使继续开发，本候选只消费这份封存输入。默认新物理身份为 `D2110106`，完整 P&R 单独记录；D105 的失败区域不自动继承。唯一录音仍为 16,384 帧，真实手机 A2DP／BLE、25K 触摸、完整 HDMI／DAC、长录音和双板共存均未验收。未操作 SRAM／Flash，现板及受保护主区不变。
