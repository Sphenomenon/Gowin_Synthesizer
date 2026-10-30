# USB2 owner 音频复位：父级接入与回归（2026-10-30）

FC 的 recovery 最差路径从50MHz启动状态直达音频域 `feedback_divider/CLEAR`。本阶段为实际 `workstation_usb2_input` 增加末尾参数 `AUDIO_OWNER_RESET_SYNC=0`，仅 runtime 顶层显式设为1。启用时平台请求异步断言，在三个真实音频上升沿后由末级释放，统一交给输入 owner 和音频反馈域；wrapper 是独立编译单元，不依赖 provider 宏传播。父级在现有 R00 top 手移这一行参数，没有用隔离旧top替换主线。

父级实际 wrapper／MMIO adapter／owner／锁定CDC／生成FIFO／session 回归通过，三个相位分别同时验证默认和启用配置。每配置4次异步断言、5次释放，覆盖停高／停低、短请求、两个排队事件顺序、断开重连、PANIC和接入默认值；六个破坏reset链的负控均由真实仿真拒绝。计算PLL隔离回归也通过，当前连接0次虚假attach，旧连接负控2次；反馈fence2项、默认hotplug准备6项、accepted来源17项全通过，无跳过。

父级刷新345项来源锁并fresh prepare：R00 `ea7e74fca1b64f6d`、保留识别 `2de322ccbd747a19`、no-CNN `7c771ad35c675979`。各12项实际来源检查通过，staged分别583／570／571项；相对各自前序仅wrapper、维护top及其兼容副本三项字节变化，SDC保持。旧 `4b1436d83219e765` 综合及FC物理证据不转移到这些新身份。

已追查owner全部16个异步敏感块，详见[复位边界契约](../rtl/workstation/USB2_INPUT_RESET.md)。当前仍未接受原始请求到同步器CLEAR的flight／脉宽、级间及末级到功能CLEAR的物理recovery／removal，以及生成FIFO写侧的音频到USB复位撤销边界。新源码不添加SDC例外，不能据此声称FC恢复失败已关闭。本阶段没有EDA或板卡操作，完整reset及部署门禁保持未完成。[机器记录](workstation_task_20261030/usb2_owner_reset_parent_integration.json)绑定父级命令、哈希及具体负控。
