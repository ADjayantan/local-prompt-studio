$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$engineScript = Join-Path $projectDir 'start-local-engines.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'LocalPromptStudioEngines'
$runCommand = '"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -Watch' -f $powershellExe, $engineScript

New-ItemProperty -Path $runKey -Name $runName -Value $runCommand -PropertyType String -Force | Out-Null
Start-Process -FilePath $powershellExe -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', $engineScript, '-Watch') -WindowStyle Hidden

Write-Host ''
Write-Host 'Local Prompt Studio auto-start is installed.' -ForegroundColor Green
Write-Host 'Backend, ComfyUI, Ollama and the web portal all start automatically after Windows sign-in.' -ForegroundColor Cyan
Write-Host 'A hidden watchdog rechecks them every 20 seconds and restarts anything that stops.' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Waiting for the portal to answer...' -ForegroundColor Yellow

$ready = $false
$deadline = [DateTime]::Now.AddSeconds(150)
do {
  try {
    $ready = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2).StatusCode -eq 200
  } catch {
    $ready = $false
  }
  if ($ready) { break }
  Start-Sleep -Milliseconds 750
} while ([DateTime]::Now -lt $deadline)

Write-Host ''
if ($ready) {
  Write-Host 'Portal is live at http://localhost:3000' -ForegroundColor Green
  Write-Host 'Bookmark that address. You never need to double-click a file again.' -ForegroundColor Green
  Start-Process 'http://localhost:3000/'
} else {
  Write-Host 'The portal has not answered yet. It usually appears within a minute.' -ForegroundColor Yellow
  Write-Host 'If it stays down, check these logs:' -ForegroundColor Yellow
  Write-Host '  D:\CLI-Anything\PromptStudio\web-engine-error.log' -ForegroundColor Yellow
  Write-Host '  D:\CLI-Anything\PromptStudio\watchdog-error.log' -ForegroundColor Yellow
}
Write-Host ''
