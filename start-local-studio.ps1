$ErrorActionPreference = 'Stop'

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$nodeExe = 'C:\Program Files\nodejs\node.exe'
$logRoot = 'D:\CLI-Anything\PromptStudio'
$env:WRANGLER_SEND_METRICS = 'false'

foreach ($requiredFile in @($nodeExe, (Join-Path $projectDir 'start-local-engines.ps1'))) {
  if (-not (Test-Path -LiteralPath $requiredFile)) {
    throw "Required local program was not found: $requiredFile"
  }
}

if (-not (Test-Path -LiteralPath $logRoot)) {
  New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
}

function Test-LocalUrl {
  param([Parameter(Mandatory = $true)][string]$Url)

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

& (Join-Path $projectDir 'start-local-engines.ps1')

if (-not (Test-LocalUrl 'http://127.0.0.1:3000/')) {
  Start-Process -FilePath $nodeExe `
    -ArgumentList @('node_modules\wrangler\bin\wrangler.js', 'dev', '--config', 'dist/server/wrangler.json', '--port', '3000') `
    -WorkingDirectory $projectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'web-start.log') `
    -RedirectStandardError (Join-Path $logRoot 'web-error.log')
}

$readyDeadline = [DateTime]::Now.AddSeconds(120)
do {
  $portalReady = Test-LocalUrl 'http://127.0.0.1:3000/'
  $apiReady = Test-LocalUrl 'http://127.0.0.1:8765/api/health'
  if ($portalReady -and $apiReady) { break }
  Start-Sleep -Milliseconds 750
} while ([DateTime]::Now -lt $readyDeadline)

if (-not ($portalReady -and $apiReady)) {
  throw "Local Prompt Studio could not start. Check logs in $logRoot"
}

Write-Host ''
Write-Host 'Local Prompt Studio is ready.' -ForegroundColor Green
Write-Host 'Portal:  http://localhost:3000' -ForegroundColor Cyan
Write-Host 'Outputs: D:\CLI-Anything\PromptStudio' -ForegroundColor Cyan
Write-Host 'Image and video become available automatically when ComfyUI finishes loading.' -ForegroundColor Yellow
Write-Host ''

Start-Process 'http://localhost:3000/'
