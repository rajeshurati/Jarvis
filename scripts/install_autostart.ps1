param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "Local Jarvis Supervisor"
$desktopTaskName = "Local Jarvis Desktop"
$legacyTaskName = "Local Jarvis Startup"
$projectRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$pythonExecutable = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonWindowlessExecutable = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"

if ($Uninstall) {
    foreach ($installedTaskName in @($taskName, $desktopTaskName, $legacyTaskName)) {
        $existing = Get-ScheduledTask -TaskName $installedTaskName -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            Unregister-ScheduledTask -TaskName $installedTaskName -Confirm:$false
        }
    }
    Write-Output "Removed the Local Jarvis startup tasks."
    exit 0
}

# Remove the pre-supervisor startup task so it cannot launch duplicate processes.
$legacyTask = Get-ScheduledTask -TaskName $legacyTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacyTask) {
    Unregister-ScheduledTask -TaskName $legacyTaskName -Confirm:$false
}

if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "Jarvis virtual environment is missing: $pythonExecutable"
}
if (-not (Test-Path -LiteralPath $pythonWindowlessExecutable -PathType Leaf)) {
    throw "Jarvis windowless Python launcher is missing: $pythonWindowlessExecutable"
}

$arguments = '-m jarvis.supervisor'
$action = New-ScheduledTaskAction `
    -Execute $pythonWindowlessExecutable `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Keeps the localhost-only Jarvis and Ollama services available after sign-in." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName

$desktopAction = New-ScheduledTaskAction `
    -Execute $pythonWindowlessExecutable `
    -Argument '-m jarvis.desktop' `
    -WorkingDirectory $projectRoot
Register-ScheduledTask `
    -TaskName $desktopTaskName `
    -Action $desktopAction `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts the Local Jarvis tray and native control panel after sign-in." `
    -Force | Out-Null
Start-ScheduledTask -TaskName $desktopTaskName
Write-Output "Installed and started the Local Jarvis service and desktop startup tasks."
