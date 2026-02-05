from base_ctrl import BaseController
import os
import fcntl
import struct
import select
import time
import math
import signal
import sys

#!/usr/bin/env python3
# filepath: /home/jetson/ugv_jetson/tutorial_en/manual_drive.py
# joystick teleop for chassis using BaseController (reads /dev/input/js0)


SERIAL = '/dev/ttyTHS1'
BAUD = 115200

MAX_SPEED = 0.2     # m/s
MAX_TURN = 0.2      # differential term (m/s)
SEND_INTERVAL = 0.5 # seconds (keepalive)

# Right-stick / gimbal configuration
# Many controllers map: 2=right_x, 3=right_y but some report swapped axes.
# Swap defaults to the more common mapping for right stick: pan=3 (horizontal), tilt=2 (vertical).
RIGHT_AXIS_PAN = 3    # horizontal on right stick (pan)
RIGHT_AXIS_TILT = 4   # vertical on right stick (tilt)
GIMBAL_SEND_INTERVAL = 0.1  # seconds
# Pan/Tilt angle limits (degrees)
PAN_MIN = -180.0
PAN_MAX = 180.0
TILT_MIN = -45.0
TILT_MAX = 90.0
# Maximum speed (degrees/sec) at full stick deflection
PAN_SPEED_DEG = 90.0
TILT_SPEED_DEG = 90.0

# Button mapping for lights (common: LB=4, RB=5). Adjust to your device if needed.
BUTTON_LIGHT_LEFT = 4
BUTTON_LIGHT_RIGHT = 5

# Hat / D-pad axes (user-provided): left/right = axis 6, back/forward = axis 7
HAT_AXIS_X = 6
HAT_AXIS_Y = 7
HAT_FORWARD_SPEED = 0.05  # m/s when fully pressed on hat Y
HAT_TURN_SPEED = 0.05     # m/s when fully pressed on hat X

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
    buttons = {}
    last_buttons = {}
    io4_pwm = 0
    io5_pwm = 0
    last_gimbal_send = 0.0
    # persistent pan/tilt angles (degrees). Start at 0 (do not auto-return).
    pan_angle = 0.0
    tilt_angle = 0.0
    last_pan, last_tilt = None, None
    last_loop_time = time.time()
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
                    if etype & JS_EVENT_BUTTON:
                        # value is 1 when pressed, 0 when released
                        buttons[number] = value
            except BlockingIOError:
                pass

            # map axes to forward/turn
            raw_forward = -axis.get(AXIS_FORWARD, 0.0)  # invert so up is positive
            # invert horizontal axis so pushing left produces a left turn
            raw_turn = -axis.get(AXIS_TURN, 0.0)

            # apply radial deadzone and rescale so diagonal inputs produce smooth combined motion
            m = math.hypot(raw_forward, raw_turn)
            if m < DEADZONE or m == 0.0:
                forward = 0.0
                turn = 0.0
            else:
                # rescale magnitude to account for deadzone and preserve direction
                scale = (m - DEADZONE) / (1.0 - DEADZONE)
                nx = raw_forward / m
                ny = raw_turn / m
                forward = nx * scale
                turn = ny * scale

            # scale
            forward_m = forward * MAX_SPEED
            turn_m = turn * MAX_TURN

            # Hat (axes 6/7) fixed slow speeds: integrate as additive contribution
            raw_hat_x = -axis.get(HAT_AXIS_X, 0.0)
            raw_hat_y = -axis.get(HAT_AXIS_Y, 0.0)  # user said negative = forward
            if abs(raw_hat_x) >= DEADZONE:
                turn_m += raw_hat_x * HAT_TURN_SPEED
            if abs(raw_hat_y) >= DEADZONE:
                forward_m += raw_hat_y * HAT_FORWARD_SPEED

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

            # Right stick -> pan/tilt (integrated velocity control)
            # read raw axes: pan should be horizontal, tilt vertical (invert vertical so up is positive)
            raw_pan = axis.get(RIGHT_AXIS_PAN, 0.0)
            raw_tilt = -axis.get(RIGHT_AXIS_TILT, 0.0)  # invert so up is positive
            # radial deadzone/rescale for velocity magnitude
            m2 = math.hypot(raw_pan, raw_tilt)
            if m2 < DEADZONE or m2 == 0.0:
                pan_norm = 0.0
                tilt_norm = 0.0
            else:
                scale2 = (m2 - DEADZONE) / (1.0 - DEADZONE)
                nx2 = raw_pan / m2
                ny2 = raw_tilt / m2
                pan_norm = nx2 * scale2
                tilt_norm = ny2 * scale2

            # integrate velocity to degrees using loop dt
            now = time.time()
            dt = max(0.0, now - last_loop_time)
            last_loop_time = now

            pan_angle += pan_norm * PAN_SPEED_DEG * dt
            tilt_angle += tilt_norm * TILT_SPEED_DEG * dt
            # clamp
            pan_angle = clamp(pan_angle, PAN_MIN, PAN_MAX)
            tilt_angle = clamp(tilt_angle, TILT_MIN, TILT_MAX)

            # send gimbal commands when changed or periodically
            now = time.time()
            if last_pan is None:
                last_pan = pan_angle
            if last_tilt is None:
                last_tilt = tilt_angle
            if (abs(pan_angle - last_pan) > 0) or (abs(tilt_angle - last_tilt) > 0) or (now - last_gimbal_send > GIMBAL_SEND_INTERVAL):
                try:
                    base.gimbal_ctrl(int(pan_angle), int(tilt_angle), 0, 0)
                    last_gimbal_send = now
                    last_pan, last_tilt = pan_angle, tilt_angle
                except Exception:
                    pass

            # handle button presses for lights (toggle on rising edge)
            try:
                lb = buttons.get(BUTTON_LIGHT_LEFT, 0)
                rb = buttons.get(BUTTON_LIGHT_RIGHT, 0)
                if lb == 1 and last_buttons.get(BUTTON_LIGHT_LEFT, 0) == 0:
                    io4_pwm = 0 if io4_pwm else 255
                    base.lights_ctrl(io4_pwm, io5_pwm)
                    print(f"Toggled IO4 (chassis LED) -> {io4_pwm}")
                if rb == 1 and last_buttons.get(BUTTON_LIGHT_RIGHT, 0) == 0:
                    io5_pwm = 0 if io5_pwm else 255
                    base.lights_ctrl(io4_pwm, io5_pwm)
                    print(f"Toggled IO5 (pan-tilt LED) -> {io5_pwm}")
            except Exception:
                pass
            last_buttons.update(buttons)

            time.sleep(0.01)

    finally:
        cleanup()


if __name__ == '__main__':
    main()
