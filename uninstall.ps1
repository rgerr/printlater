# Removes PrintLater for the current user. Your config and token are kept unless -All is given.
param([switch]$All)
$root = Join-Path $env:LOCALAPPDATA 'PrintLater'
$app  = Join-Path $root 'app'
if (Test-Path (Join-Path $app 'run.py')) { & py -3 (Join-Path $app 'run.py') uninstall-menu }
Remove-Item -Recurse -Force $app -ErrorAction SilentlyContinue
if ($All) { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
Write-Host "PrintLater removed$(if ($All) {' including settings'} else {'; settings kept in ' + $root})."
