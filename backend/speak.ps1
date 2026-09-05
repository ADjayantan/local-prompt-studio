param(
  [Parameter(Mandatory = $true)][string]$TextFile,
  [Parameter(Mandatory = $true)][string]$OutputFile
)

$resolvedText = (Resolve-Path -LiteralPath $TextFile).Path
$outputParent = Split-Path -Parent $OutputFile
if (-not (Test-Path -LiteralPath $outputParent)) {
  New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
}

Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $speaker.SelectVoice('Microsoft Zira Desktop')
  $speaker.Rate = 0
  $speaker.Volume = 100
  $speaker.SetOutputToWaveFile($OutputFile)
  $speaker.Speak([System.IO.File]::ReadAllText($resolvedText))
} finally {
  $speaker.Dispose()
}
