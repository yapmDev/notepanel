#!/usr/bin/env bash
PID=$(pgrep -f "python3.*notepanel/main.py")
if [ -n "$PID" ]; then
    kill -SIGUSR1 "$PID"
fi
