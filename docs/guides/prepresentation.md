# ซ้อมใช้งาน SafeFlow ก่อนพรีเซนต์

เป้าหมายคือแสดงว่าผู้ดูแลเปลี่ยนนิยามแล้วใช้ตัวกำกับเดิมได้ การเปลี่ยนเป็น 90 วินาที
เป็นตัวอย่างการปรับใช้ ไม่ได้แทนข้อกำหนดหลัก 180 วินาทีในรายงานลงนาม

## ชุดที่มีให้ลอง

| ชุด | ไฟล์ตั้งค่า | สิ่งที่เปลี่ยน |
|---|---|---|
| A | examples/smart-home/lab.yaml | บ้านเดิม พัก 180 วินาที |
| B | examples/smart-home/variants/cooldown-90/lab.yaml | พัก 90 วินาที |
| C | examples/smart-home/variants/renamed-90/lab.yaml | พัก 90 และเปลี่ยนรหัสแอร์/คำสั่ง |

C ใช้ cooling_unit, cooling_on และ cooling_off ในแบบจำลอง ส่วนอุปกรณ์ native
ยังชื่อ air_conditioner เหมือนเดิม bindings เป็นผู้เชื่อมสองชื่อเข้าหากัน
จึงไม่อ้างว่าได้เพิ่มอุปกรณ์กายภาพชนิดใหม่ การทดสอบก่อนพรีเซนต์มี
[หลักฐานและตารางเปรียบเทียบ](../../experiments/prepresentation-2026-10-27/README.md)

## 1. ลองแก้ไฟล์โดยไม่แตะโค้ด

สำเนาโฟลเดอร์ cooldown-90 เป็นโฟลเดอร์ my-home ที่อยู่ข้างกัน แล้วแก้ policy.yaml
เช่น parameters.rest_s หรือรหัสตัวแปร/คำสั่ง หากเปลี่ยนรหัสต้องแก้การอ้างอิงใน
transition, property, clock reset และ bindings ให้ตรงกัน

ไฟล์ requirements.json เป็นเฉลยทดสอบอิสระ ระบุเวลาพักและชื่อแฝงที่ต้องการจริง
ไม่ใช่ไฟล์กฎ runtime อย่าแก้เฉลยเพียงเพื่อให้ผลที่ผิดผ่านการตรวจ
ตัวอย่าง C ใช้ชื่อแฝงสำหรับบทบาท ac และคำสั่ง ac_cool/ac_off ส่วนบทบาทอื่นคงเดิม

## 2. ทวนสอบนิยามรุ่นใหม่

จากราก repository ใช้โฟลเดอร์ผลลัพธ์ใหม่ทุกครั้ง:

```powershell
./.venv/Scripts/python.exe -m safeflow verify --definition examples/smart-home/variants/my-home/policy.yaml --output logs/my-home-proof-01 --verifyta ../../tools/uppaal/uppaal-5.0.0-win64/bin/verifyta.exe
```

ดู verification.json และผลแต่ละคุณสมบัติ ต้องผ่านครบจึงเปิดควบคุมได้ หากเปลี่ยน
นิยามหลังตรวจ หรือใช้ bundle ของอีกชุด ระบบจะไม่พร้อมและไม่รับการควบคุม
UPPAAL ตรวจแบบจำลองก่อนเริ่ม ส่วนระหว่างรัน SafeFlow ตรวจทุกเหตุการณ์และผลจริง

## 3. เปิดหน้า Home Assistant และลองหนึ่งรอบ

เปิด backend แบบกดทีละรอบ เพื่อเห็นลำดับชัดและปิด trace ได้ง่าย:

```powershell
./.venv/Scripts/python.exe -m safeflow serve --config examples/smart-home/variants/my-home/lab.yaml --verification logs/my-home-proof-01 --logs logs/my-home-run-01
```

อีก terminal ใช้ `docker compose -f docker/compose.yaml up -d homeassistant`
แล้วเปิด [Home Assistant](http://localhost:8123) ด้วยบัญชี lab เดิม

1. เลือก SafeFlow Lab และตรวจ Readiness = ready
2. ตั้งเป้าหมายอุณหภูมิหรือไฟ แล้วดูค่าที่อ่านกลับ
3. เปิดสวิตช์แอร์ คำขอจะเข้าคิว ยังไม่เปลี่ยนบ้านทันที
4. กด Run one round เพื่อใช้คำสั่งคนหนึ่งรอบ
5. กดอีกครั้งเพื่อรับข้อเสนอจาก AI แล้วดูผลตัดสินและสถานะล่าสุด
6. หยุด backend ด้วย Ctrl+C หลังรอบเสร็จและคิวว่าง เพื่อปิด trace

ถ้าจะลองชุด B/C ที่เก็บผลตรวจไว้แล้ว ใช้ --config ของชุดนั้นได้ตรง ๆ บนเครื่องนี้
เครื่องอื่นต้องสร้าง bundle ของตัวเองให้ตรงกับ source และ verifier ที่มีสิทธิ์ใช้งาน
อย่าเปิด backend สองตัวชนพอร์ต 8765 หรือใช้ผลตรวจชุด A กับ B/C

## 4. สลับโมเดลจริง

หยุด backend เดิมแล้วเริ่ม session ใหม่ด้วย config และ bundle เดิม เพิ่มเพียง
`--model qwen3:0.6b` หรือ `--model qwen3:1.7b` ไม่ต้องแก้นิยามหรือแกนตัวกำกับ
ถ้าต้องการรันอัตโนมัติให้เพิ่ม --interval 5 ซึ่งเป็นเวลาพักจริงระหว่างรอบ
เวลาจำลองยังเดินครั้งละ 30 วินาที ไม่ใช่เวลาที่โมเดลใช้คิด

สำหรับตรวจอัตโนมัติผ่านบัญชี lab ที่มี refresh token อยู่แล้ว ใช้เครื่องมือดังนี้
โดย backend ต้องใช้ --logs ให้ตรงกับ --trace-dir:

```powershell
./.venv/Scripts/python.exe scripts/check-live-loop.py --rounds 5 --min-ai-responses 4 --human-device air_conditioner --trace-dir logs/my-home-run-01 --output logs/my-home-live-01.json
```

เครื่องมือนับคำตอบ native ของโมเดลที่ดำเนินรอบจบแล้ว ไม่เอา timeout มานับเป็น
คำตอบ และต้องมี AI ทำงานต่อหลังคำสั่งคน report.json เป็นผลช่วงที่ระบบยังรันอยู่
ต้องตรวจ trace หลังหยุดด้วย หากหยุดระหว่างเรียกโมเดลอาจจบด้วย shutdown_requested
ซึ่งไม่ถือเป็น run ที่ปิดครบ ให้เก็บไว้และรันใหม่ ไม่แก้ log เพื่อให้ผ่าน

## 5. อ่านข้อมูลและอธิบายเส้นทาง

```powershell
./.venv/Scripts/python.exe -m safeflow check logs/my-home-run-01/session-ID.jsonl
./.venv/Scripts/python.exe scripts/check-home-trace.py logs/my-home-run-01/session-ID.jsonl --contract examples/smart-home/variants/my-home/requirements.json --output logs/my-home-oracle-01.json
```

อ่านตามลำดับ: session_start ระบุนิยาม/ผลทวนสอบ → received เก็บคำตอบดิบและข้อมูลที่
ส่งให้โมเดล → decision ระบุเหตุการณ์ รหัส action และ transition → observation
เก็บสถานะดิบจาก simulation และ facts ที่แปลงแล้ว → session_end ปิดการรัน

ที่ 120 วินาที ชุด A ต้องบล็อกการเปิดแอร์ใหม่ ส่วน B/C อนุญาต การยืนยันจุดนี้ใช้
ชุดทดสอบ API ที่ควบคุมเวลาและติดป้ายชัด ไม่อ้างว่าโมเดลจริงเสนอคำสั่งนั้นเอง
การทดสอบขอบ 89/90/91 วินาทีทำใน API/engine ส่วนหน้าบ้านปกติเดินครั้งละ 30 วินาที

ไม่จำเป็นต้องให้ AI เลือกคำสั่งเก่งจึงผ่านการตรวจตัวกำกับ และการรันจริงที่ไม่มี
คำสั่งถูกบล็อกก็ไม่ใช่หลักฐานว่า AI ไม่มีวันฝ่ากฎ ข้อสรุปจำกัดตามข้อมูลที่เก็บ

เมื่อซ้อมเสร็จ หยุดเฉพาะ container lab ด้วย
`docker compose -f docker/compose.yaml stop homeassistant` เพื่อเก็บบัญชี ข้อมูล และหลักฐานไว้
