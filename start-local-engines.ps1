param([switch]$Watch)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = 'D:\CLI-Anything\Python312\python.exe'
$comfyRoot = 'D:\CLI-Anything\ComfyUI_windows_portable'
$comfyPython = Join-Path $comfyRoot 'python_embeded\python.exe'
$logRoot = 'D:\CLI-Anything\PromptStudio'

function Test-LocalUrl {
  param([Parameter(Mandatory = $true)][string]$Url)
  try {
    return (Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode -eq 200
  } catch {
    return $false
  }
}

function Test-LocalProcess {
  param(
    [Parameter(Mandatory = $true)][string]$ExecutablePath,
    [Parameter(Mandatory = $true)][string]$CommandPattern
  )
  return @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.ExecutablePath -eq $ExecutablePath -and $_.CommandLine -like $CommandPattern }
  ).Count -gt 0
}

function Start-LocalEngines {
  if (-not (Test-Path -LiteralPath $logRoot)) {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
  }

  $apiRunning = Test-LocalProcess -ExecutablePath $pythonExe -CommandPattern '*backend\server.py*--port*8765*'
  if (-not (Test-LocalUrl 'http://127.0.0.1:8765/api/health') -and -not $apiRunning) {
    Start-Process -FilePath $pythonExe `
      -ArgumentList @('backend\server.py', '--port', '8765') `
      -WorkingDirectory $projectDir `
      -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logRoot 'api-start.log') `
      -RedirectStandardError (Join-Path $logRoot 'api-error.log')
  }

  $comfyRunning = Test-LocalProcess -ExecutablePath $comfyPython -CommandPattern '*ComfyUI\main.py*--port*8188*'
  if (-not (Test-LocalUrl 'http://127.0.0.1:8188/system_stats') -and -not $comfyRunning) {
    Start-Process -FilePath $comfyPython `
      -ArgumentList @('-s', 'ComfyUI\main.py', '--windows-standalone-build', '--listen', '127.0.0.1', '--port', '8188') `
      -WorkingDirectory $comfyRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logRoot 'comfy-start.log') `
      -RedirectStandardError (Join-Path $logRoot 'comfy-error.log')
  }
}

if (-not $Watch) {
  Start-LocalEngines
  exit 0
}

$createdNew = $false
$watchdogMutex = New-Object System.Threading.Mutex($true, 'Local\PromptStudioEngineWatchdog', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

try {
  while ($true) {
    Start-LocalEngines
    Start-Sleep -Seconds 20
  }
} finally {
  $watchdogMutex.ReleaseMutex()
  $watchdogMutex.Dispose()
}
