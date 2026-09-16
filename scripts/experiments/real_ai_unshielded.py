import os
import json
import logging
import gymnasium as gym
import sinergym
from stable_baselines3 import PPO

# 1. ปิด Log ภายนอก
logging.getLogger('sinergym').setLevel(logging.CRITICAL)
logging.getLogger('gymnasium').setLevel(logging.CRITICAL)
os.environ['ENERGYPLUS_LOG_LEVEL'] = 'FATAL'

# 2. เชื่อมต่อ Environment และ AI Model
env = gym.make('Eplus-5zone-hot-discrete-v1')
ai_model = PPO(policy="MlpPolicy", env=env, verbose=0)

obs, info = env.reset()

TOTAL_STEPS = 10
logs_data = []  # ตัวแปรสำหรับรวม Log ทุกสเต็ป

for step in range(TOTAL_STEPS):
    action, _states = ai_model.predict(obs, deterministic=False)
    action = int(action)

    next_obs, reward, terminated, truncated, next_info = env.step(action)

    log_entry = {
        "step": step + 1,
        "input_observation": {
            "indoor_temp_c": round(float(obs[0]), 2),
            "raw_obs_sample": [round(float(x), 2) for x in obs[:4]]
        },
        "ai_proposed_action": action,
        "simulator_response": {
            "reward": round(float(reward), 4),
            "next_indoor_temp_c": round(float(next_obs[0]), 2),
            "terminated": bool(terminated),
            "truncated": bool(truncated)
        }
    }

    logs_data.append(log_entry)
    obs = next_obs
    if terminated or truncated:
        obs, info = env.reset()

env.close()

# 3. Export บันทึกเป็นไฟล์ execution_logs.json ลงในโฟลเดอร์ logs
with open("/workspace/logs/execution_logs.json", "w", encoding="utf-8") as f:
    json.dump(logs_data, f, indent=2, ensure_ascii=False)

print("\n[SUCCESS] Exported logs to logs/execution_logs.json successfully!")
