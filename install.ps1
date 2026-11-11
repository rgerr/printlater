# PrintLater installer for the current Windows user (no administrator rights needed).
# Copies the program to %LOCALAPPDATA%\PrintLater\app, creates config.toml if missing
# and adds "Print later..." to the right-click menu of .3mf files.
$ErrorActionPreference = 'Stop'
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Join-Path $env:LOCALAPPDATA 'PrintLater'
$app  = Join-Path $root 'app'

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { throw "Python launcher 'py' not found. Install Python 3.11 or newer first (winget install Python.Python.3.12)." }
if ((& py -3 -c "import sys; print(sys.version_info >= (3, 11))") -ne 'True') { throw "Python 3.11 or newer is required." }
$pyexe = (& py -3 -c "import sys; print(sys.executable)").Trim()

New-Item -ItemType Directory -Force -Path $app | Out-Null
Copy-Item -Recurse -Force (Join-Path $src 'printlater') $app
Copy-Item -Force (Join-Path $src 'run.py'), (Join-Path $src 'config.example.toml') $app
$cfg = Join-Path $root 'config.toml'
if (-not (Test-Path $cfg)) { Copy-Item (Join-Path $src 'config.example.toml') $cfg; Write-Host "Created $cfg" }
else { Write-Host "Kept existing $cfg" }

& $pyexe (Join-Path $app 'run.py') install-menu

# Start menu: print queue and "plan next job from the queue"
$nl = (Get-Culture).TwoLetterISOLanguageName -eq 'nl'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PrintLater'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
$pyw = Join-Path (Split-Path $pyexe) 'pythonw.exe'
$sh = New-Object -ComObject WScript.Shell
foreach ($e in @(@('queue', $(if ($nl) { 'Printwachtrij' } else { 'Print queue' })),
                 @('next',  $(if ($nl) { 'Volgende uit de wachtrij inplannen' } else { 'Plan next job from the queue' })))) {
    $lnk = $sh.CreateShortcut((Join-Path $menu ($e[1] + '.lnk')))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $app 'run.py') + '" ' + $e[0]
    $lnk.WorkingDirectory = $app
    $lnk.Save()
}
& $pyexe (Join-Path $app 'run.py') check
Write-Host "`nDone. Right-click a .gcode.3mf file and choose 'Print later...'."
Write-Host "Windows 11: the entry is under 'Show more options'."
