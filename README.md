# waveshare_ugv_joystick_controller
Waveshare Robots Joystick Controller
# UGV Jetson — Joystick Teleop (tutorial_en)

This directory contains a simple joystick teleoperation script for the UGV chassis.

## Files

- `manual_drive.py` — reads `/dev/input/js0` and maps joystick axes to differential drive commands sent over serial to the base controller.

## Quick start

1. Make sure your joystick is recognized and working:

```bash
sudo jstest /dev/input/js0
```

2. Run the teleop script (may require `sudo` to access the joystick device):

```bash
sudo python3 tutorial_en/manual_drive.py
```

3. Move the left analog stick to drive the robot. Release the stick to stop — the script sends zero speed when the axis returns to center.

## Configuration

Edit the top of `manual_drive.py` to change behavior:

- `JS_DEV` — joystick device path (default `/dev/input/js0`).
- `AXIS_FORWARD` — axis number used for forward/back (default `1`, typically left stick vertical).
- `AXIS_TURN` — axis number used for turning (default `0`, typically left stick horizontal).
- `DEADZONE` — small threshold to ignore stick jitter (default `0.15`).
- `MAX_SPEED` / `MAX_TURN` — scale linear and turning speeds.

If controls feel inverted, swap sign or swap axis indices as needed.

## Safety

- The script sends a stop command on exit or on SIGINT/SIGTERM.
- Verify the robot is secured before first run and keep a clear emergency stop method available.

## Troubleshooting

- If the joystick device is not found, confirm device node with `ls /dev/input/` and use the correct `JS_DEV`.
- Use `jstest-gtk` or `jstest` to find axis numbers reported by your gamepad and adjust `AXIS_FORWARD` / `AXIS_TURN`.

## License
APACHE
