# ClipGrab

เว็บแอปโหลดคลิปจากลิงก์ (YouTube, TikTok, Facebook, Instagram, X และอีกหลายเว็บที่ yt-dlp รองรับ)
รันเซิร์ฟเวอร์บนมือถือ Android ด้วย Termux แล้วเปิดใช้จากมือถือหรือ iPad ผ่านเบราว์เซอร์

ฟีเจอร์: พรีวิวคลิปก่อนโหลด · MP4 (เลือกคุณภาพได้) / MP3 / ภาพปก · วางหลายลิงก์พร้อมกัน · แถบความคืบหน้า · ยกเลิกได้

## ติดตั้ง (ครั้งเดียว) บน Termux

แก้ `USER/REPO` เป็นของคุณแล้ววางทีเดียวจบ:

```bash
pkg update -y && pkg install -y git && git clone https://github.com/USER/REPO.git clipgrab && cd clipgrab && bash setup.sh
```

ถ้าขึ้นหน้าต่างขอสิทธิ์เก็บไฟล์ ให้กดอนุญาต

## ใช้งาน

```bash
cd clipgrab && bash start.sh
```

เทอร์มินัลจะแสดงที่อยู่ เช่น `http://192.168.1.50:8080`

- เปิดบนมือถือเครื่องเดียวกัน: `http://localhost:8080`
- เปิดจาก iPad: ต้องอยู่ Wi-Fi เดียวกัน แล้วเปิดที่อยู่ที่แสดง จากนั้นกด "บันทึกไฟล์" ไฟล์จะลงในแอป Files ของ iPad
- ไฟล์ที่โหลดจะถูกเก็บในมือถือที่โฟลเดอร์ `Download/ClipGrab` ด้วย (ถ้าอนุญาตสิทธิ์เก็บไฟล์แล้ว)

ไม่ควรเปิดพอร์ตนี้ออกอินเทอร์เน็ต เพราะไม่มีระบบล็อกอิน ใช้ใน Wi-Fi บ้านเท่านั้น

## อัปเดต

เมื่อโหลดไม่ได้ ส่วนใหญ่เพราะเว็บต้นทางเปลี่ยนระบบ ให้รัน `bash update.sh` แล้วเริ่มใหม่

## ปรับแต่ง (ตัวแปรสภาพแวดล้อม)

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `PORT` | 8080 | พอร์ตเซิร์ฟเวอร์ |
| `MAX_PARALLEL` | 2 | จำนวนคลิปที่โหลดพร้อมกัน |
| `DOWNLOAD_DIR` | `~/storage/downloads/ClipGrab` หรือ `./downloads` | ที่เก็บไฟล์ |

ตัวอย่าง: `PORT=9000 MAX_PARALLEL=3 bash start.sh`

## อัปขึ้น GitHub

GitHub Pages รันเซิร์ฟเวอร์ไม่ได้ จึงใช้ GitHub เก็บโค้ดอย่างเดียว แล้วโคลนไปรันบน Termux

```bash
git init && git add . && git commit -m "ClipGrab"
git branch -M main
git remote add origin https://github.com/USER/REPO.git
git push -u origin main
```

## หมายเหตุ

ใช้ดาวน์โหลดเฉพาะเนื้อหาที่คุณมีสิทธิ์ และให้เคารพข้อกำหนดของแต่ละแพลตฟอร์ม
