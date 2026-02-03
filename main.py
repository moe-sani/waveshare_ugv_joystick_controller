from base_ctrl import BaseController
import os
import fcntl
import struct
import select
import time
import signal
import sys

#!/usr/bin/env python3
# filepath: /home/jetson/ugv_jetson/tutorial_en/manual_drive.py
# joystick teleop for chassis using BaseController (reads /dev/input/js0)


SERIAL = '/dev/ttyTHS1'
BAUD = 115200

MAX_SPEED = 0.4     # m/s
MAX_TURN = 0.3      # differential term (m/s)
SEND_INTERVAL = 0.5 # seconds (keepalive)

# Joystick device and axis mapping (adjust if your gamepad differs)
JS_DEV = '/dev/input/js0'
AXIS_FORWARD = 1  # typically left stick vertical
AXIS_TURN = 0     # typically left stick horizontal
DEADZONE = 0.15   # joystick deadzone (0..1)

_JS_EVENT_STRUCT = struct.Struct('<IhBB')  # time(unsigned int), value(short), type(ubyte), number(ubyte)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

base = BaseController(SERIAL, BAUD)

js_fd = None

def cleanup(signum=None, frame=None):
    try:
        base.send_command({"T":1, "L":0.0, "R":0.0})
    except Exception:
        pass
    try:
        if js_fd is not None:
            os.close(js_fd)
    except Exception:
        pass
    print("\nStopped. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def clamp(v, a, b):
    return max(a, min(b, v))

def compute_lr(forward, turn):
    l = forward - turn
    r = forward + turn
    l = clamp(l, -MAX_SPEED, MAX_SPEED)
    r = clamp(r, -MAX_SPEED, MAX_SPEED)
    return l, r

def normalize_axis(raw):
    # raw is int in -32767..32767
    if raw == 0:
        return 0.0
    return max(-1.0, min(1.0, float(raw) / 32767.0))

def open_joystick(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return fd

def main():
    global js_fd
    # ensure robot stopped at start
    base.send_command({"T":1, "L":0.0, "R":0.0})

    try:
        js_fd = open_joystick(JS_DEV)
    except Exception as e:
        print(f"Could not open joystick {JS_DEV}: {e}")
        print("Run 'jstest /dev/input/js0' to confirm device. Exiting.")
        return

    print(f"Using joystick {JS_DEV}. AXIS_FORWARD={AXIS_FORWARD}, AXIS_TURN={AXIS_TURN}, DEADZONE={DEADZONE}")

    axis = {}
    last_send = 0.0
    last_l, last_r = 0.0, 0.0

    try:
        while True:
            # read all available events
            try:
                while True:
                    buf = os.read(js_fd, _JS_EVENT_STRUCT.size)
                    if not buf or len(buf) < _JS_EVENT_STRUCT.size:
                        break
                    tv, value, etype, number = _JS_EVENT_STRUCT.unpack(buf)
                    if etype & JS_EVENT_INIT:
                        # ignore initialization events
                        continue
                    if etype & JS_EVENT_AXIS:
                        axis[number] = normalize_axis(value)
                    # buttons ignored for now
            except BlockingIOError:
                pass

            # map axes to forward/turn
            raw_forward = -axis.get(AXIS_FORWARD, 0.0)  # invert so up is positive
            raw_turn = axis.get(AXIS_TURN, 0.0)

            # apply deadzone
            forward = raw_forward if abs(raw_forward) >= DEADZONE else 0.0
            turn = raw_turn if abs(raw_turn) >= DEADZONE else 0.0

            # scale
            forward_m = forward * MAX_SPEED
            turn_m = turn * MAX_TURN

            l, r = compute_lr(forward_m, turn_m)

            # send only when changed meaningfully or periodic keepalive
            if (abs(l - last_l) > 1e-3) or (abs(r - last_r) > 1e-3):
                base.send_command({"T":1, "L":round(l,3), "R":round(r,3)})
                last_send = time.time()
                last_l, last_r = l, r
                print(f"F={forward_m:.2f}  Turn={turn_m:.2f}  L={l:.2f} R={r:.2f}")

            if time.time() - last_send > SEND_INTERVAL:
                # keepalive with current values
                base.send_command({"T":1, "L":round(l,3), "R":round(r,3)})
                last_send = time.time()

            time.sleep(0.01)

    finally:
        cleanup()


if __name__ == '__main__':
    main()
