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

1. In Bambu Studio: slice, then use the arrow next to *Print plate* → **Export plate sliced file**
   (or skip this and use a saved project, see below).
2. Right-click the `.gcode.3mf` → **Print later...** (Windows 11: *Show more options* first).
3. Pick the date and time and what the time means:
   - *the printer starts* (default): heating and homing begin at that time
   - *the first layer starts*: the preparation time (default 8 min) is subtracted
   - *the print is finished*: Bambu's estimated print time and a 10 min margin are subtracted;
     the estimate can be off on long prints, so the margin errs on finishing early
4. Bambu Studio opens the delayed copy (`<name>_startHHMM.gcode.3mf`). Press **Print plate → Send**
   within about a minute. The printer accepts the job at once and shows it as printing while it waits.

Your computer can be switched off after sending; the printer does the waiting.

### From a saved project

You can also right-click a saved Bambu Studio project (`.3mf`) instead of an exported
`.gcode.3mf`. PrintLater then slices the chosen plate with Bambu Studio's command line
(`--slice N --export-3mf`) and continues as above.

- Only what is saved is sliced. Unsaved changes in the Studio window are not included.
- A project made for another printer (a download from MakerWorld often is) is refused when
  `printer_model` is set in `config.toml`: open it in Studio, pick your printer and save it.
- In tests on a P2S the command line gave the same layers, weight and time as a GUI export; tool paths
  can differ in small details such as seam start points.

### Automatic send (experimental)

Tick **Send automatically** to let PrintLater press *Print plate* and *Send* in the Bambu Studio
window that holds the delayed file. Bambu Studio does the sending, exactly as when you click
yourself. Before sending, PrintLater shows the file and its filaments; Studio chooses the AMS slot
for each filament itself, so check what is loaded or choose *Send myself*.

PrintLater finds the buttons by their label, not by screen position, and stops when Studio does not
offer *Send* (for example because the printer is busy). The Studio window is then left open for you
and, with Home Assistant, a message goes to the `notify` service you set. A Bambu Studio update that
renames or rebuilds these windows can break this; sending yourself always works. The box is
remembered between plans.

To cancel, stop the job in Bambu Handy, Bambu Studio or on the printer.

## Timing

Large files take longer to reach the printer: Bambu Studio uploads them and the printer downloads
and unpacks them before it reports *running*. PrintLater adds `transfer_seconds_per_mb` (1.6 s) for
every MB above 10 MB; a 74 MB file took about 125 s on a P2S, a 6 MB file about 20 s.

The wait is counted from the moment the printer starts the file, which is 15 to 25 seconds after
you press Send. The dialog assumes you send within `send_lead_seconds` (60 s). Sending later moves
the start by the same amount. With Home Assistant enabled, PrintLater watches for the job and shows
the exact expected start time once the printer has accepted it.

## Things to know

- **Send from the right window.** PrintLater opens the delayed file in Bambu Studio and brings that
  window to the front; its title ends in `_startHHMM`. If Studio was already open, a second Studio
  window appears. Enabling *Keep only one Bambu Studio instance* in Studio's preferences avoids
  that, but Studio then replaces the project that is open.
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

- switch the printer's smart plug on before you send, and stop if it does not come online
- refuse when the printer is still busy, naming the running job and any planned start
- set an `input_datetime` to the expected start and an `input_boolean` while a start is planned
- report the exact expected start once the job is accepted
- show what is planned: job name in an `input_text` (`plan_name`) and a status in another
  `input_text` (`plan_status`): `none`, `planned` (file made, not yet on the printer),
  `waiting` (accepted, waiting cold), `started` or `failed` (no confirmation within 15 minutes)
- keep a print queue in a to-do list (`queue_todo`, for example a *Local To-do* list).
  The dialog gets an *Add to queue* button; Start menu → PrintLater → *Plan next job from
  the queue* opens the dialog for the first item and ticks it off once the job is accepted.
  Sending still happens in Bambu Studio: the printer holds one job at a time.

When Home Assistant is enabled but cannot be reached, or a configured entity does not exist,
PrintLater does not plan: without it, it cannot check whether the printer is free. Set
`continue_without_ha = true` to plan anyway.

`homeassistant/printlater_status_queue_example.yaml` is an example package that keeps the
status up to date after planning (waiting, started, failed when the plug goes off) and
notifies you when a print finishes while the queue is not empty.

The blueprint `homeassistant/printlater_delayed_start.yaml` detects a waiting job (running,
stage idle, both target temperatures 0 for 45 s), keeps the chamber light off and can notify
you when waiting begins and when the print really starts.

## Command line

`PrintLater.exe` (installed) and `run.py` (source) take the same commands. The exe has no
console: its output goes to `printlater.log` in `%LOCALAPPDATA%\PrintLater`.

```text
run.py plan <file.gcode.3mf>                          dialog (same as the right-click entry)
run.py make <file.gcode.3mf> --at "YYYY-MM-DD HH:MM"  write the delayed file only
             [--printing | --finish] [--plate N]      (--plate: slice that plate of a project .3mf)
run.py queue                                          show the print queue
run.py next                                           dialog for the next job in the queue
run.py check | set-token | install-menu | uninstall-menu
```

## Tested with

Bambu Lab P2S with AMS, Bambu Studio 2.8, Bambu cloud mode. Other models use the same
G-code dialect and should work, but test with a short delay (a few minutes) first.

## License

MIT
