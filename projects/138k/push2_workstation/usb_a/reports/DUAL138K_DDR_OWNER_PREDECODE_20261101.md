# DDR 返回 owner 预译码维护阶段

实际arbiter仅将每个权威tags entry的invalid谓词先组合译码，再按原read_pointer选择一位veto。没有新状态或周期，原四位owner读取、返回数据、优先级／fairness和所有NBA保持；tag corruption及X/Z仍可在同边沿触发原empty／invalid-owner即时故障。

W16far真实15级路径为read_pointer→RAM16SDP4／多位tags mux→response_fault_now→bridge／raw fault，总数据14.996ns（C2Q.306、cell4.113、route10.577），最差−5.168ns。本次只处理该前缀，不宣称已消除完整违例。新RTL SHA256 `e4cd6d5e3e485659041015adcfbcdf34259e3e33240a4027bdf90e11467f655d`，严格逆向恢复原`4320716d…7deb`全部字节。

实际candidate通过620,880四态／NBA边沿检查，原bits2模块另21,552次，3新负控；原native27场景＋6fault＋11负控、authority10相位每相位17场景／666检查及6负控均通过。主线程独立重验248证据及2owned。逐文件hash／命令／检查范围见[机器报告](DUAL138K_DDR_OWNER_PREDECODE_20261101.json)，seal `e24caaaca663a2ad5dd23b2b0ae508eb1d9e1fcb7013ddf2a367ca157dda92ed`。

预译码可能改变推断存储和路由成本；必须用新来源锁、候选及完整综合/P&R实际测量。冻结W16不改，不预记资源／时序收益；未运行EDA、未上板或写SRAM／Flash。
