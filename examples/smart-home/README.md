# ตัวอย่างบ้านหนึ่งห้อง

ผู้ติดตั้งแก้สองไฟล์นี้:

- `policy.yaml`: สถานะ การกระทำ กฎเวลา transition และคุณสมบัติที่ต้องตรวจ
- `lab.yaml`: การจับคู่ตัวแปรกับอุปกรณ์จริงของ simulation และตัวเลือก AI

ตัวอย่างใช้แอร์ ฮีเตอร์ พัดลม และไฟ ค่า 180 วินาทีเป็นค่าทดลอง ไม่ใช่ข้อกำหนดผู้ผลิต
ชื่อ action เช่น ac_cool เป็นรหัสที่ตัวเชื่อมเข้าใจ แกนตัวกำกับไม่รู้จักชื่ออุปกรณ์โดยตรง
LLM ส่งรหัสผ่าน JSON ส่วน ML/RL สามารถแปลง class/action index เป็นรหัสเดียวกันได้
การควบคุมต่อเนื่องและหลายอุปกรณ์พร้อมกันยังไม่อยู่ในตัวเชื่อมบ้านรุ่นนี้

หากเปลี่ยนชื่ออุปกรณ์ให้แก้ variables/actions/expressions และ bindings ให้ตรงกัน
หากเปลี่ยนเวลาพักให้แก้ parameters.rest_s การเพิ่มกฎต้องมีคุณสมบัติที่ต้องการตรวจด้วย
ระบบช่วยตรวจสิ่งที่เขียน แต่ไม่ได้รู้เองว่ากฎของบ้านคุณควรเป็นอะไร

หลังแก้ ต้องสร้างชุดทวนสอบใหม่ก่อนเปิดใช้งาน:

```powershell
./.venv/Scripts/python.exe -m safeflow verify --definition examples/smart-home/policy.yaml --output logs/my-home-01 --verifyta /path/to/verifyta
./.venv/Scripts/python.exe -m safeflow serve --config examples/smart-home/lab.yaml --verification logs/my-home-01
```

ใช้โฟลเดอร์ผลลัพธ์ใหม่ทุกครั้ง หาก UPPAAL ตรวจไม่ได้หรือมีคุณสมบัติไม่ผ่าน ระบบยังไม่พร้อมควบคุม
อ่าน [ไวยากรณ์และสมมติฐาน](../../docs/guides/automata.md) และ [ตัวอย่าง API](../../docs/guides/api.md)
