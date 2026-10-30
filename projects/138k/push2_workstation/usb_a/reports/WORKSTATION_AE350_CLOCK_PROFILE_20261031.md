# ILM/DLM 新配置的时钟审计来源修正

实际 C02 整机综合候选 `custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1-011fdc9c6697df42` 完成后，时钟审计器仍只按旧 no-panel 名字识别 LCD 关闭状态，错误要求新配置含 LCD 时钟。初次失败日志保留；本修正从命名 profile 注册表取得 panel 策略，严格核对 configuration、profile_source 和 SHA256 形状，未知或损坏的命名配置失败。缺少命名清单的历史准备保留原 panel-on 策略。

没有改变 SDC、时钟、PLL、硬件或固件。实际原 VG 重新通过五项时钟／来源测试、28 个网表和约束负控；新增注册表测试覆盖五种配置和各自损坏身份。ProfileSources 六项、accepted sources 十七项、带实际 prepare 的 runtime sources 十二项通过，五份 profile 来源锁全部加载成功。PCM CDC 的完整重新运行单独记录，不借本次时钟结果宣称其通过。

新的实际 prepare／verify 身份为 `custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1-4b356270438e20d8`；600 项 staged 输入与 C02 原准备逐字相同，266 编译单元／298 modules／2 packages。新身份没有重跑综合；上述 VG 检查明确绑定原 `011fdc9c6697df42`，不回填原来源记录。

原整机综合耗时 371.465 s，600 项输入、原复制清单 653 文件保持，无 AG 诊断；Logic 94,623／LUT 75,967／ALU 16,802／RAM16 309／Register 60,578，综合等效 BSRAM 245/340。它是后续 C03 迁移前对照，**不是物理 CLS／BSRAM 或 routed timing**。ROM 内容会被稀疏优化，不能把容量差预记为固定物理成本。VG SHA256 为 `fdc08cad2db2b540a4bf6d99e85a9ac6f3942868dc3db7292281a20ed9e80f3e`。

机器记录：[ae350_clock_profile_parent.json](workstation_task_20261030/ae350_clock_profile_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-clock-profile-parent-v1` 保存源码快照与外部输入清单，`verify.py` 可只读复核。未运行 P&R 或操作板卡；完整 CDC／reset／物理时序、CPU 周期与硬件 ILM/DLM/cache 仍待验证。回退本次工具改动可恢复 `904b2c6`，但旧审计器仍不能正确识别新配置，不能以回退作为通过证据。
