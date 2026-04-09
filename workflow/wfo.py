from .finetune import train_hpo
from .run_ray import dipatch
from .run_sim import run_backtest


def run_wfo_pipeline(output):
    trade_years = range(2011, 2022)
    
    last_valid_state = {
        "config": None,
        "motif": None,
        "fsm_prior": None
    }
    
    for trade_year in trade_years:
        train_start = (trade_year - 2) * 10000 + 101 
        train_end   = (trade_year - 1) * 10000 + 1231 
        trade_start = trade_year * 10000 + 101       
        trade_end   = trade_year * 10000 + 1231      
        
        print(f"🔄 WFO 训练期 [{train_start}-{train_end}] -> 交易期[{trade_year}]")
        
        # ---------------------------------------------------------
        # stage A: Ray Tune seek opt 
        # ---------------------------------------------------------
        best_trial = train_hpo(start_date=train_start, end_date=train_end)
        
        if best_trial is not None and best_trial.metrics["status"] == "success":
            print(f"✅ 成功挖出显著 Alpha 更新大脑库")
            current_config = best_trial.config
            current_motif = best_trial.metrics["learned_motif"]
            current_fsm = best_trial.metrics["fsm_prior_matrix"]
            
            # refresh cache
            last_valid_state["config"] = current_config
            last_valid_state["motif"] = current_motif
            last_valid_state["fsm_prior"] = current_fsm
            
        else:
            print(f"Alpha not found")
            if last_valid_state["motif"] is not None:
                print(f"Fallback and inhert previous fsm")
                current_config = last_valid_state["config"]
                current_motif = last_valid_state["motif"]
                current_fsm = last_valid_state["fsm_prior"] 
            else:
                print(f"not history fsm avaiable and force cash strategy")
                continue 

        # ---------------------------------------------------------
        # stage B: Ray Worker generate OOS Score Parquet
        # ---------------------------------------------------------
        # return update FSM
        updated_fsm = dipatch(
            start_date=trade_start,
            end_date=trade_end,
            config=current_config,
            learned_motif=current_motif,
            fsm_prior_matrix=current_fsm,
            output=output
        )
        
        last_valid_state["fsm_prior"] = updated_fsm


if __name__ == "__main__":

    print("🚀 初始化 Ray 分布式集群...")

    env_vars = {
      "OMP_NUM_THREADS": "1",
      "MKL_NUM_THREADS": "1",
      "OPENBLAS_NUM_THREADS": "1",
      "VECLIB_MAXIMUM_THREADS": "1",
      "NUMEXPR_NUM_THREADS": "1"
    }

    ray.init(address="auto", 
             namespace="backtest", 
             runtime_env={"env_vars": env_vars},  
            ignore_reinit_error=True
    )
    
    from .ray_agent import start_agents
    agent_num = 10
    start_agents(pool_size=agent_num)
    
    try:
        # os.makedirs(output, exist_ok=True)
        # s3 nfs used in cluster
        run_wfo_pipeline(output)
    except KeyboardInterrupt:
        print("\n⏹️ 任务被手动终止")
    finally:
        print("清理集群资源...")
        ray.shutdown()

    # run backtest
