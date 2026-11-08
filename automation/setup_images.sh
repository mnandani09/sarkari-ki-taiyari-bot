#!/usr/bin/env bash
# Fonts + headless Chromium for the carousel / post / Story images (GitHub runner)
set -e
mkdir -p ~/.fonts
for w in Regular Medium SemiBold Bold; do wget -q -O ~/.fonts/Poppins-$w.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-$w.ttf; done
sudo apt-get install -y -q fonts-noto-color-emoji > /dev/null 2>&1 || true
fc-cache -f > /dev/null
pip install -q playwright==1.48.0
python -m playwright install --with-deps chromium > /dev/null 2>&1
