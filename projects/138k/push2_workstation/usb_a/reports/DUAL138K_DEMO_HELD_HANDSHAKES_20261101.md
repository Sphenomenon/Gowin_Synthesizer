# DEMO PC／APB 既有握手的窄时序约束

显式 DEMO timing owner已升级为v2，向新M／W候选实际SDC添加10行约束：8-bit PC和49-bit APB请求held payload保持13.020ns有限setup，只豁免hold；三个toggle只切到首级D，首级Q到第二级D保持2.000ns。旧APB响应20.000ns和PC ACK规则保持，没有整域clock cut、后级setup cut或reset例外。v1候选继续使用原封存策略及SDC，不自动升级。

实际VG／VO的Boolean握手审查证明payload不会在ACK前覆盖、逐bit只到对应目的D、首级无旁路或额外功能消费者，capture等待原协议同步阶段。新门同时接入严格综合网表和实际物理PLL/startup入口；新元数据明确列出held总线约束，不能仍用“没有业务例外”描述。全实际netlist解析选择器，拒绝跨owner宽glob，以及额外max_delay覆盖原有限预算。

[机器验证记录](dual138k_demo_held_handshakes_20261101.json)绑定6维护文件身份。M16与W14真实VG／VO共16项针对性测试、100个反例拒绝；DEMO selection／v1兼容3项通过，真实旧stage＋原SDC兼容复验且原SHA不变。隔离旧HEAD原helper和test复现物理单测23项中的相同2失败／1跳过：无效M/W配置fixture被更早的integration metadata hash门拒绝。该失败明确保留，未放宽门或改错误顺序，不能写成全套单测通过。

先前模块行为证据还覆盖16种50MHz／76.8MHz相位、PC224／APB224事务、停钟、忙时丢弃、背压和复位释放，6实际源负控拒绝；旧cache seal v2 SHA256 `9b36aabd94b4084c625e76db0b758ce113af98fdceba1b37ba6f539805fce311`，root重验42产物及7外部输入。这里的reset仿真属于可复用模块。实际custom top的PC reset绑定常高，所有reset／CLEAR无效且有效INIT0，因此只证明power-up-only，不声称支持PC warm reset；APB仍为共同异步断言、各域三拍释放。

最终维护验证记录SHA256 `3606092ac1c27163c4068a554ae3de30c58c00832fbeb2add188a8268b3a7290`，源于缓存`held-maintained-validation-v1.json`。M17／W15已独立prepare且启动全量综合，分别在新身份下验证实际选择和routed时序。这里没有运行新P&R、SRAM或Flash；原M16／W14失败记录不改，同域负路径仍需处理，尚未获得完整声画或双板接受。
