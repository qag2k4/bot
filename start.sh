#!/usr/bin/env bash
set -x
python -u web.py &
python -u bot.py
