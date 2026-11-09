#!/usr/bin/env bash
# เริ่มเซิร์ฟเวอร์: bash start.sh
cd "$(dirname "$0")"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
python app.py
