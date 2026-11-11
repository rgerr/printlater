# Changelog

## 1.2.0 (2026-11-11)

- Planning status in Home Assistant: job name (`plan_name`) and status (`plan_status`:
  none, planned, waiting, started, failed).
- Print queue in a Home Assistant to-do list (`queue_todo`): *Add to queue* in the dialog,
  `run.py queue` and `run.py next`, Start menu entries for both.
- No silent planning without Home Assistant: when it is enabled but unreachable, or a configured
  entity is missing, PrintLater stops (`continue_without_ha = true` restores the old behaviour).
- The busy message names the running job and any planned start.
- Stops when the printer does not come online after switching the plug on.
- No confirmation within 15 minutes: the plan is marked failed and the planned flag is cleared.
- Example package `homeassistant/printlater_status_queue_example.yaml`.

## 1.1.0 (2026-11-01)

- Windows installer (`PrintLater-Setup-1.1.0.exe`): no Python needed, per-user install, uninstall
  via Settings → Apps, settings and token kept on update and uninstall.
- Start menu entries: set Home Assistant token, check settings, edit settings file.
- Packaged exe logs command output to `printlater.log` in the settings folder.
- Installer replaces the program files of an earlier `install.ps1` install.
- Installer built and smoke-tested on Windows by a GitHub Actions workflow.

## 1.0.0 (2026-11-01)

- Low-power delayed start inserted into sliced `.gcode.3mf` files, checksum updated.
- Right-click dialog (English/Dutch) with "printer starts" or "first layer starts" timing.
- Optional Home Assistant link: plug on, busy check, planned-start helpers, start confirmation.
- Home Assistant blueprint: chamber light off while waiting, notifications.
- Timing calibrated on a P2S: dwell accurate to about 1 s over 11 h; Send to file start 15-25 s;
  preparation before the first layer about 8 min.
