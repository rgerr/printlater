# PrintLater

Start a Bambu Lab print at a time you choose, for example tomorrow at 07:30, while keeping
Bambu Handy and cloud printing. No Developer Mode, no LAN-only mode, no firmware changes and
no extra hardware.

*Unofficial tool. Not affiliated with or endorsed by Bambu Lab.*

## How it works

You send the job right away. A short block at the very top of the G-code makes the printer
wait, cold, until the chosen time:

- bed and hotend heaters off, controllable fans off, toolhead and calibration LEDs off
- stepper motors released
- a series of short dwell commands (`M400 S90`; the firmware caps a single dwell at about 90 s)
- motors re-enabled, then the printer's normal start sequence runs (homing, heating, levelling)

The plate's checksum inside the `.gcode.3mf` is updated, so the printer accepts the file.

Field test on a P2S with AMS (PETG, auto levelling): an 11-hour wait started within one second
of the calculated time; the first layer began about 8 minutes later.

## Requirements

- Windows 10/11
- Bambu Studio
- A sliced plate exported with **Export plate sliced file** (a `.gcode.3mf`)
- Optional: Home Assistant with the Bambu Lab integration (ha-bambulab)

## Install

Download `PrintLater-Setup-<version>.exe` from the
[latest release](https://github.com/rgerr/printlater/releases/latest) and run it. It installs for
your Windows user only (no administrator rights) and adds **Print later...** to the right-click
menu of `.3mf` files. Uninstall via Settings → Apps; your settings are kept.

The installer is not code-signed, so Windows SmartScreen may show "Windows protected your PC".
Choose *More info* → *Run anyway*. The installer is built from this repository by the
[Windows installer workflow](.github/workflows/windows-installer.yml), which also runs a
silent install and uninstall test.

### From source

With Python 3.11 or newer installed:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Use

1. In Bambu Studio: slice, then use the arrow next to *Print plate* → **Export plate sliced file**.
2. Right-click the `.gcode.3mf` → **Print later...** (Windows 11: *Show more options* first).
3. Pick the date and time and what the time means:
   - *the printer starts* (default): heating and homing begin at that time
   - *the first layer starts*: the preparation time (default 8 min) is subtracted
4. Bambu Studio opens the delayed copy (`<name>_startHHMM.gcode.3mf`). Press **Print plate → Send**
   within about a minute. The printer accepts the job at once and shows it as printing while it waits.

Your computer can be switched off after sending; the printer does the waiting.

To cancel, stop the job in Bambu Handy, Bambu Studio or on the printer.

## Timing

The wait is counted from the moment the printer starts the file, which is 15 to 25 seconds after
you press Send. The dialog assumes you send within `send_lead_seconds` (60 s). Sending later moves
the start by the same amount. With Home Assistant enabled, PrintLater watches for the job and shows
the exact expected start time once the printer has accepted it.

## Things to know

- **The build plate must be empty** at the start time. The printer cannot check this.
- The printer stays powered while it waits. Heaters, controllable fans and motors are off, but the
  power supply and mainboard (and one fan that G-code cannot control on some models) stay on.
  The standby draw has not been measured yet.
- The **chamber light** cannot be switched by G-code. The cloud turns it on when a job is sent.
  Switch it off in Handy, or use the Home Assistant blueprint below to do it automatically.
- A power cut during the wait cancels the job; nothing starts.
- Handy and Home Assistant show the job as *running* with no remaining time while it waits.
- The printer is busy while it waits: you cannot send another job in the meantime.

## Home Assistant (optional)

With `homeassistant.enabled = true` in `config.toml` PrintLater can do more. Store the token
with Start menu → PrintLater → *Set Home Assistant token* (or `run.py set-token` from source);
it is encrypted for your Windows user. The Start menu also has *Edit settings file* and
*Check settings*. With Home Assistant PrintLater can:

- switch the printer's smart plug on before you send
- refuse when the printer is still busy
- set an `input_datetime` to the expected start and an `input_boolean` while a start is planned
- report the exact expected start once the job is accepted

The blueprint `homeassistant/printlater_delayed_start.yaml` detects a waiting job (running,
stage idle, both target temperatures 0 for 45 s), keeps the chamber light off and can notify
you when waiting begins and when the print really starts.

## Command line

`PrintLater.exe` (installed) and `run.py` (source) take the same commands. The exe has no
console: its output goes to `printlater.log` in `%LOCALAPPDATA%\PrintLater`.

```text
run.py plan <file.gcode.3mf>                          dialog (same as the right-click entry)
run.py make <file.gcode.3mf> --at "YYYY-MM-DD HH:MM"  write the delayed file only
run.py check | set-token | install-menu | uninstall-menu
```

## Tested with

Bambu Lab P2S with AMS, Bambu Studio 2.8, Bambu cloud mode. Other models use the same
G-code dialect and should work, but test with a short delay (a few minutes) first.

## License

MIT
