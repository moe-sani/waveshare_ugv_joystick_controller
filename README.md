# waveshare_ugv_joystick_controller
Waveshare Robots Joystick Controller
# UGV Jetson — Joystick Teleop (tutorial_en)

This directory contains a simple joystick teleoperation script for the UGV chassis.

## Files

- `manual_drive.py` — reads `/dev/input/js0` and maps joystick axes to differential drive commands sent over serial to the base controller.
 - `main.py` — reads `/dev/input/js0` and maps joystick axes to differential drive commands sent over serial to the base controller.

## Quick start

1. Make sure your joystick is recognized and working:

```bash
sudo jstest /dev/input/js0
```

2. Run the teleop script (may require `sudo` to access the joystick device):

```bash
sudo python3 main.py
```

3. Move the left analog stick to drive the robot. Release the stick to stop — the script sends zero speed when the axis returns to center.

## Configuration

Edit the top of `main.py` to change behavior:

- `JS_DEV` — joystick device path (default `/dev/input/js0`).
- `AXIS_FORWARD` — axis number used for forward/back (default `1`, typically left stick vertical).
- `AXIS_TURN` — axis number used for turning (default `0`, typically left stick horizontal).
- `DEADZONE` — small threshold to ignore stick jitter (default `0.15`).
- `MAX_SPEED` / `MAX_TURN` — scale linear and turning speeds.

Additional controls in this version:

- Right stick (`RIGHT_AXIS_PAN`, `RIGHT_AXIS_TILT`): controls the pan/tilt gimbal. Pan maps roughly to ±180°; tilt maps approximately from -45° (down) to +90° (up). Adjust `RIGHT_AXIS_PAN` / `RIGHT_AXIS_TILT` at the top of `main.py` if your gamepad uses different axis indices.
- Shoulder buttons (`BUTTON_LIGHT_LEFT`, `BUTTON_LIGHT_RIGHT`): toggle IO4 (chassis LED) and IO5 (pan-tilt LED) respectively. Defaults are LB=4 and RB=5; change these constants if your device reports different button numbers.

Behavior notes:

- Pan/Tilt now use hold-to-move velocity control: pushing the right stick in a direction will move the gimbal continuously while held. The deflection magnitude controls speed (more deflection → faster). Releasing the stick stops movement — the camera does not auto-return to center.
- Default axis mapping is `RIGHT_AXIS_PAN=3` (horizontal) and `RIGHT_AXIS_TILT=2` (vertical). If your controller reports different indices, run `jstest /dev/input/js0` and update those constants at the top of `main.py`.

Fixes in this version:

- Left/right turning inversion corrected: pushing the stick left now turns the robot left.
- Diagonal (combined forward+turn) control improved: joystick uses a radial deadzone and rescales diagonal inputs so you can smoothly move and turn when pushing the stick at an angle.

If controls feel inverted, swap sign or swap axis indices as needed.

## Safety

- The script sends a stop command on exit or on SIGINT/SIGTERM.
- Verify the robot is secured before first run and keep a clear emergency stop method available.

## Troubleshooting

- If the joystick device is not found, confirm device node with `ls /dev/input/` and use the correct `JS_DEV`.
- Use `jstest-gtk` or `jstest` to find axis numbers reported by your gamepad and adjust `AXIS_FORWARD` / `AXIS_TURN`.

## License
APACHE
