# W-DEMO：CPU／BLE 唯一录音对象源码与离线验证

日期：2026-10-31。范围为 `task2.md` 第5.4节的录音owner与固件接口；本记录不是整机、位流或硬件验收。

W显式选择 `SINGLE_BLE_RECORDING=1`，经维护 HCI wrapper→native core→GATT→command endpoint 逐层传递；默认值仍为0，不依赖顶层宏越过独立编译边界。唯一真实后端是既有 BLE raw DDR store。CPU/UI调用 `a138_ble_record_firmware_submit/poll/facts`，同样使用 `ble_business_owner` 的对象ID、任务ID、物理descriptor序号和CRC。独立R00后端及其DDR lane的退出由W整机装配另行验证，不能凭该API提前宣称网表已退出。

内部START/STOP/CLEAR descriptor可在GATT未连接时执行。其private flag不进入外部线规，READ原有Rice flags、真实链路、CRC、ACK／恢复／任务语义保留。START成功需要实际完整首帧；STOP成功需要真实DDR提交前缀进入READY；CLEAR成功需要raw实际完成。终态receipt保持对象身份、帧数和CRC；已封存对象不会因下一次REC而静默覆盖。CPU observer reset仍使用原sticky fence。

W固件选择 `A138_SINGLE_BLE_RECORDING`，退出启动note／本地96-bit REC／cue自检和cue上传，原REC token转请求上述同一owner。旧录音对象64 API不再被W UI调用；被退出的硬件寄存器须在完整候选明确拒绝。默认宏关闭时，BLE owner源码删除opt-in块后逐字节还原原审核SHA `71661e3f0f11a668966e5b9cdabd8a4599e6990d1e299c91cd1310cb4273792a`。维护first-party provenance记录当前owner，冻结输入、原始import映射和历史ROM均保持。

[验证摘要](worker_single_recording_20261031/verification.json)：实际C链接真实APB CDC、协议parser、物理CRC engine、raw DDR及native commit，控制时钟20ns／内存时钟14ns。1765项行为检查，其中64项覆盖CPU无GATT START→首帧→STOP／native READY→BLE GET／真实READ同一对象和CRC→CPU无GATT CLEAR→替换ID。包括无首帧时保持PENDING、不可覆盖queued请求、真实提交数、下载PCM CRC与CLEAR终态身份。原136条外部wire／DATA消息与历史golden逐字相等，15项既有行为变异负控全部拒绝；输入在测试期间未变化。旧 `sim/test_recording_service_api.py` 同时通过。

真实ROM构建另增加显式worker选择和callback审核：原分支仍保留原owner／有序机器站点检查；worker分支绑定维护源码和独立审核站点，实际未知JALR、缺少目标、源码漂移和栈溢出拒绝。NoBonding/session-only Classic来源由相应独立实现记录说明；最终完整候选须重新构建并绑定其实际UI／ROM／ELF来源、资源与时序，不能使用本阶段的中间ROM数字代替。

当前录音仍是既有format1：48kHz stereo PCM16，16384帧／65536字节，约0.341秒。未完成长录音、44.1kHz格式扩展、真实蓝牙音频录制、Android手机WAV、实板声画共存或完整W综合／P&R。测试PCM为确定性的仿真fixture，仅用于核对真实存储与CRC，不是DEMO音源或真实闭环的替代。
