$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$engineScript = Join-Path $projectDir 'start-local-engines.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'LocalPromptStudioEngines'
$runCommand = '"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -Watch' -f $powershellExe, $engineScript

New-ItemProperty -Path $runKey -Name $runName -Value $runCommand -PropertyType String -Force | Out-Null
Start-Process -FilePath $powershellExe -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', $engineScript, '-Watch') -WindowStyle Hidden

Write-Host 'Local Prompt Studio auto-start is installed.' -ForegroundColor Green
Write-Host 'Backend and ComfyUI will start automatically after Windows sign-in.' -ForegroundColor Cyan
