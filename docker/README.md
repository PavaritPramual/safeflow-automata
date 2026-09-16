# Docker workflow

SafeFlow ใช้ Sinergym และ EnergyPlus ผ่าน external Docker image โดยไม่ vendor
source code ของ Sinergym เข้ามาใน repository นี้

## Image ที่ต้องใช้

สคริปต์ `real_ai_unshielded.py` ใช้ Stable-Baselines3 PPO ดังนั้น image ต้อง build
พร้อม optional dependency กลุ่ม `drl`

ชุดที่ทดสอบผ่าน:

- Sinergym `v3.12.2`
- Commit `4bb1b3f856af491f9b55f8a0d1b0baeaff44a6a0`
- Target `runtime`
- Build argument `SINERGYM_EXTRAS="drl"`

จาก parent workspace ที่มี Sinergym อยู่ใน `external/sinergym`:

```powershell
docker build --target runtime -t sinergym:latest --build-arg SINERGYM_EXTRAS="drl" .\external\sinergym
```

ตรวจว่า Sinergym และ Stable-Baselines3 import ได้:

```powershell
docker run --rm sinergym:latest python -c "import sinergym, stable_baselines3; print('Dependencies OK')"
```

## Run experiment

รันจาก root ของ `safeflow-ai`:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace sinergym:latest python scripts/experiments/real_ai_unshielded.py
```

การ mount ทำให้ตำแหน่งภายใน container เชื่อมกับ host ดังนี้:

| Container | Host |
|---|---|
| `/workspace/scripts/experiments/real_ai_unshielded.py` | `scripts/experiments/real_ai_unshielded.py` |
| `/workspace/logs/execution_logs.json` | `logs/execution_logs.json` |
| `/workspace/Eplus-*-res*/` | `Eplus-*-res*/` |

`--rm` ลบ container หลังจบงาน แต่ไม่ลบไฟล์ที่เขียนผ่าน bind mount

## Minimal image กับ DRL image

Sinergym runtime image ที่ build โดยไม่กำหนด `SINERGYM_EXTRAS` สามารถรัน simulator
พื้นฐานได้ แต่ไม่สามารถรัน experiment นี้เพราะไม่มี `stable_baselines3`

```text
runtime minimal              Sinergym + EnergyPlus
runtime with extras="drl"    Sinergym + EnergyPlus + PPO dependencies
```

การเพิ่ม `drl` เป็นการเตรียม dependency ของ environment ไม่ใช่การเพิ่ม algorithm
ใหม่ใน SafeFlow
