param([switch]$Watch)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = 'D:\CLI-Anything\Python312\python.exe'
$comfyRoot = 'D:\CLI-Anything\ComfyUI_windows_portable'
$comfyPython = Join-Path $comfyRoot 'python_embeded\python.exe'
$nodeExe = 'C:\Program Files\nodejs\node.exe'
$logRoot = 'D:\CLI-Anything\PromptStudio'
$ollamaModels = 'D:\CLI-Anything\Ollama\models'
$env:WRANGLER_SEND_METRICS = 'false'
$env:OLLAMA_MODELS = $ollamaModels

function Resolve-Ollama {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
    (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  $command = Get-Command ollama -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  return $null
}

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
  if (-not (Test-Path -LiteralPath $ollamaModels)) {
    New-Item -ItemType Directory -Path $ollamaModels -Force | Out-Null
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

  # Local LLM (Ollama) for real PowerPoint and Markdown content. Optional:
  # if Ollama is not installed this block is skipped and those modes fall back
  # to offline templates.
  $ollamaExe = Resolve-Ollama
  if ($ollamaExe -and -not (Test-LocalUrl 'http://127.0.0.1:11434/api/tags')) {
    Start-Process -FilePath $ollamaExe `
      -ArgumentList @('serve') `
      -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logRoot 'ollama-start.log') `
      -RedirectStandardError (Join-Path $logRoot 'ollama-error.log')
  }

  # Web portal on http://localhost:3000. Keeping it here means the sign-in
  # watchdog brings the whole studio up on its own — no file to double-click.
  $portalRunning = Test-LocalProcess -ExecutablePath $nodeExe -CommandPattern '*wrangler*dev*--port*3000*'
  if ((Test-Path -LiteralPath $nodeExe) -and -not (Test-LocalUrl 'http://127.0.0.1:3000/') -and -not $portalRunning) {
    Start-Process -FilePath $nodeExe `
      -ArgumentList @('node_modules\wrangler\bin\wrangler.js', 'dev', '--config', 'dist/server/wrangler.json', '--port', '3000') `
      -WorkingDirectory $projectDir `
      -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logRoot 'web-engine-start.log') `
      -RedirectStandardError (Join-Path $logRoot 'web-engine-error.log')
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
    # One transient failure (a locked log file, a slow disk) must never kill the
    # watchdog — otherwise the studio silently stops coming up after sign-in.
    try {
      Start-LocalEngines
    } catch {
      $stamp = (Get-Date).ToString('s')
      "[$stamp] $($_ | Out-String)" | Add-Content -Path (Join-Path $logRoot 'watchdog-error.log') -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 20
  }
} finally {
  $watchdogMutex.ReleaseMutex()
  $watchdogMutex.Dispose()
}
