param(
    [switch]$SilentTest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "logs"
$logPath = Join-Path $logDirectory "wake-alarm.log"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Write-AlarmLog {
    param([string]$Message)
    "$(Get-Date -Format o) $Message" | Add-Content -LiteralPath $logPath -Encoding UTF8
}

Write-AlarmLog "Wake alarm started. SilentTest=$SilentTest"
$alarmAudio = Join-Path $projectRoot "data\wake-alarm.wav"
if (-not (Test-Path -LiteralPath $alarmAudio)) {
    throw "Wake alarm audio is missing: $alarmAudio"
}
if ($SilentTest) {
    $probe = [System.Media.SoundPlayer]::new($alarmAudio)
    $probe.Load()
    $probe.Dispose()
    Write-AlarmLog "Silent validation completed."
    exit 0
}

try {
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        Write-AlarmLog "Speaking wake call attempt $attempt."
        [Console]::Beep(880, 500)
        [Console]::Beep(1047, 500)
        $player = [System.Media.SoundPlayer]::new($alarmAudio)
        $player.PlaySync()
        $player.Dispose()
        if ($attempt -lt 6) {
            Start-Sleep -Seconds 20
        }
    }
    $popup = New-Object -ComObject WScript.Shell
    [void]$popup.Popup(
        "Good morning Rajesh. Jarvis is ready.",
        300,
        "Jarvis wake-up call",
        64
    )
    Write-AlarmLog "Wake alarm completed."
}
catch {
    Write-AlarmLog "Wake alarm failed: $($_.Exception.Message)"
    throw
}
