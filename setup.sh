#!/usr/bin/env bash
# ติดตั้งครั้งเดียวบน Termux: bash setup.sh
set -e
cd "$(dirname "$0")"
pkg update -y
pkg install -y python ffmpeg
pip install -U -r requirements.txt
[ -d "$HOME/storage" ] || termux-setup-storage || true
echo
echo "ติดตั้งเสร็จแล้ว เริ่มใช้งานด้วย: bash start.sh"
