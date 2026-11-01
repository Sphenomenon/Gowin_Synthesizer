# W14 far 完整物理对照

W14 `D211010F` 已完成全量 P&R 和六组物理子审计。原 DDR 3.500 ns hold 路径余量 +0.667 ns，全局 hold 0 个违例／+0.106 ns；setup 仍有 6909 个违例端点、最差 −5.058 ns，recovery +2.469、removal +0.278 ns。整机时序未闭合，尚非合格演示镜像，未上板。

候选 `custom138k-workstation-w-demo-v1-df8c9ba4d32507f1` 保持默认完整 VG／SDC，只追加两条 DDR 远区 CST，无 monitor 区域或时钟／例外放宽。physical manifest SHA256 `b310b83e8bdd73b697042f964e8637d7eb6b92878ef06540a05b7d7442108139`；FS `d965d0082102f8de6f5d93816d747714729543dad403b0dae057602ed2712daf`。Gowin V1.9.12、place2／route0、关闭资源复制，P&R 493.868 秒、退出 0。[机器报告](dual138k_w14_far_physical_20261101.json)绑定实际来源、配置和命令。

物理 FF 45,092、LUT 57,144、ALU 14,380、CLS 53,291、BSRAM 293、DSP 66.5、SSRAM 298。DDR launch R104C175→capture R2C2，arrival 6.081、required 5.414、skew 0.470 ns，原要求保持。四条 clk50 专项／全来源 setup、hold 分别 −4.734／+0.140／−4.734／+0.140 ns，各限 100 条，不冒充完整端点统计。最差全局路径为 DDR command_full→raw memory_generation CE；仍须修复实际同步控制锥，不能以 hold 转正宣称整机接受。

实际 VO native 54 项（40 通过／14 跳过）及 35 负控、boundary 7 项及 69 负控、官方六 PLL／三 shared tuple／7 负控全部通过。原 prepare v1 及其失败保持；v3 外部审计只替换已审 helper 与 test，未混入维护 TF。主线程逐 hash 重验 32 物理文件及 3248 项证据，含 1374 冻结审计输入、645 staged、951 prepare 来源及 915 PLL 依赖。完整 seal `w14-audits-v3/far-complete-seal-v1.json` SHA256 `032485b9e719797d47939944089c4717c315ffebefa5ef0ed6a99025adbfd777`。

本轮无 SRAM／Flash 或板卡操作。真实完整 HDMI／DAC／25K、手机 A2DP／BLE／D 实时处理与下载、长录音和双板联合验收仍未完成；模拟器验证与稍后真机验收分别记录。现有录音容量仍为 16,384 帧，并非长录音。
