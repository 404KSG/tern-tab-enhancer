#!/usr/bin/env python3
"""Offline status fixture: speaks the same OSC 7501 states as Pi 1.2."""
import sys

def report(state):
    suffix = ":kind=question" if state == "blocked" else ""
    sys.stdout.write(f"\033]7501;state={state}:app=pi{suffix}\033\\")
    sys.stdout.flush()

sys.stdout.write("\033]2;π - Offline status fixture\007")
report("idle")
print("Offline status fixture. No model calls. Commands: working, blocked, done, idle, error.", flush=True)
for line in sys.stdin:
    command = line.strip()
    if command in {"working", "blocked", "done", "idle", "error"}:
        report(command)
        print(command, flush=True)
    elif command == "quit":
        break
