$ErrorActionPreference = 'Stop'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
Remove-ItemProperty -Path $runKey -Name 'LocalPromptStudioEngines' -ErrorAction SilentlyContinue
Write-Host 'Local Prompt Studio auto-start entry was removed.' -ForegroundColor Green
