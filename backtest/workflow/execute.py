class HierarchicalBayesianFSM:
    def __init__(self, pure_chains, idi_prices, m, num_macro_states=3, fsm_dist_thresh=1.2, max_wait=40):
        self.m = m
        self.fsm_dist_thresh = fsm_dist_thresh
        self.max_wait = max_wait
        self.num_macro = num_macro_states
        
        # 1. 宏观大脑：P(S_{t+1} | S_t)
        # 矩阵形状[今日宏观状态, 明日宏观状态]，拉普拉斯平滑初始化为 1.0
        self.macro_transition_alpha = np.ones((num_macro_states, num_macro_states))
        
        # 2. 微观大脑与状态机
        self.chains_db = {}
        for cid, chain_indices in enumerate(pure_chains):
            # 提取标准化的形态轨迹
            trajectory =[]
            for idx in chain_indices:
                subseq = idi_prices[idx : idx + m].copy()
                # Z-Score 标准化，保证计算距离时不受绝对振幅影响
                subseq_z = (subseq - np.mean(subseq)) / (np.std(subseq) + 1e-8)
                trajectory.append(subseq_z)
                
            self.chains_db[cid] = {
                "trajectory": trajectory,
                "current_step": 0,
                "bars_waited": 0,
                # 微观先验矩阵：P(R_{t+1} | Chain=True, S_{t+1})
                # 矩阵形状[明日宏观状态, 明日个股收益状态(0跌, 1平, 2涨)]
                "conditional_alpha": np.ones((num_macro_states, 3)) 
            }
            
    def update_posterior(self, macro_t_minus_1, macro_t, stock_ret_t, triggered_chains_t_minus_1):
        """
        在 T 日收盘时调用：使用已发生的事实，更新贝叶斯先验矩阵。
        """
        if macro_t_minus_1 is None:
            return # 第一天，没有历史转移记录可更新

        # 1. 更新宏观转移大脑: 记录 S_{t-1} 到 S_t 的跃迁
        self.macro_transition_alpha[macro_t_minus_1, macro_t] += 1.0
        
        # 2. 将今日连续收益率离散化为状态 (0:跌, 1:平, 2:涨)
        ret_thresh = 0.01 # 可根据实际波动率动态调整
        if stock_ret_t < -ret_thresh:
            stock_state_t = 0
        elif stock_ret_t > ret_thresh:
            stock_state_t = 2
        else:
            stock_state_t = 1
            
        # 3. 更新微观个股链条大脑: 只有昨天触发的链条，今天才能验证其预测结果
        for cid in triggered_chains_t_minus_1:
            # 更新逻辑：在今天真实发生的宏观状态(macro_t)下，这只股票最终走出了 stock_state_t
            self.chains_db[cid]["conditional_alpha"][macro_t, stock_state_t] += 1.0

    def step_fsm(self, live_residual_window):
        """
        在 T 日收盘时调用：推进状态机，返回今天刚通关（触发）的链条 ID 列表。
        """
        # 对最新窗口进行标准化
        live_z = (live_residual_window - np.mean(live_residual_window)) / (np.std(live_residual_window) + 1e-8)
        triggered_chains_today =[]

        for cid, chain in self.chains_db.items():
            step = chain["current_step"]
            if step < len(chain["trajectory"]):
                target_pat = chain["trajectory"][step]
                dist = np.linalg.norm(live_z - target_pat) # simd
                
                # 形态匹配成功，FSM 向前推进一步
                if dist < self.fsm_dist_thresh:
                    chain["current_step"] += 1
                    chain["bars_waited"] = 0
                    
                    # 链条走完（通关）！
                    if chain["current_step"] == len(chain["trajectory"]):
                        triggered_chains_today.append(cid)
                        chain["current_step"] = 0 # 重置，等待下一次触发
                else:
                    # 匹配失败，增加等待计数
                    if step > 0:
                        chain["bars_waited"] += 1
                        if chain["bars_waited"] > self.max_wait:
                            # 等待超时，状态机归零
                            chain["current_step"] = 0
                            chain["bars_waited"] = 0
                            
        return triggered_chains_today

    def predict_prob_up(self, chain_id, macro_t):
        """
        全概率公式推断：计算明天 (T+1) 上涨的联合概率 P(R_{t+1}=涨 | C_t, S_t)
        """
        chain = self.chains_db[chain_id]
        
        # 1. 大盘转移概率: P(S_{t+1} | S_t)
        macro_alphas = self.macro_transition_alpha[macro_t, :]
        p_macro_next = macro_alphas / np.sum(macro_alphas) # 长度为 num_macro 的数组
        
        total_prob_up = 0.0
        
        # 2. 全概率展开：遍历明天所有可能的宏观状态 j
        for next_macro_j in range(self.num_macro):
            
            # P(R_{t+1}=涨 | C_t, S_{t+1}=j)
            micro_alphas = chain["conditional_alpha"][next_macro_j, :]
            p_micro_up_given_j = micro_alphas[2] / np.sum(micro_alphas)
            
            # 累加：P(S_{t+1}=j) * P(R=涨 | S_{t+1}=j)
            total_prob_up += p_macro_next[next_macro_j] * p_micro_up_given_j
            
        return total_prob_up
