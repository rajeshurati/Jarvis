$ErrorActionPreference = "Stop"
$logPath = Join-Path (Split-Path $PSScriptRoot -Parent) "data\windows_audio_repair.log"
Start-Transcript -Path $logPath -Force

try {
    $microphoneDevice = "INTELAUDIO\CTLR_DEV_7A50&LINKTYPE_02&DEVTYPE_00&VEN_8086&DEV_AE20&SUBSYS_170F1025&REV_10EC\5&130de547&0&0000"
    $microphoneEndpoint = "SWD\MMDEVAPI\{0.0.1.00000000}.{9fb30d50-197f-44b1-929b-3c8af38a4710}"

    Write-Host "Restarting Intel microphone device..."
    pnputil /restart-device $microphoneDevice
    if ($LASTEXITCODE -ne 0) {
        throw "Intel microphone device restart failed with exit code $LASTEXITCODE"
    }

    Write-Host "Restarting Windows microphone endpoint..."
    pnputil /restart-device $microphoneEndpoint
    if ($LASTEXITCODE -ne 0) {
        throw "Microphone endpoint restart failed with exit code $LASTEXITCODE"
    }

    Write-Host "Restarting Windows Audio..."
    Restart-Service -Name Audiosrv -Force
    Start-Sleep -Seconds 3

    Write-Host "Windows audio repair completed."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript
}
