$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "logs"
$startupLog = Join-Path $logDirectory "startup.log"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Write-StartupLog {
    param([string]$Message)
    "$(Get-Date -Format o) $Message" | Add-Content -LiteralPath $startupLog -Encoding UTF8
}

function Test-LocalEndpoint {
    param([string]$Url)
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

Set-Location -LiteralPath $projectRoot
if (-not (Test-LocalEndpoint "http://127.0.0.1:11434/api/tags")) {
    $ollama = Join-Path $projectRoot "tools\ollama\jarvis-ollama.exe"
    $env:OLLAMA_NO_CLOUD = "true"
    Start-Process -FilePath $ollama -ArgumentList "serve" -WorkingDirectory (Split-Path $ollama) -WindowStyle Hidden
    Write-StartupLog "Started Ollama."
    Start-Sleep -Seconds 4
}

if (-not (Test-LocalEndpoint "http://127.0.0.1:8765/health")) {
    $jarvis = Join-Path $projectRoot ".venv\Scripts\jarvis.exe"
    Start-Process -FilePath $jarvis -WorkingDirectory $projectRoot -WindowStyle Hidden
    Write-StartupLog "Started Jarvis."
    Start-Sleep -Seconds 4
}

if (-not (Test-LocalEndpoint "http://127.0.0.1:11434/api/tags")) {
    throw "Ollama did not become ready"
}
if (-not (Test-LocalEndpoint "http://127.0.0.1:8765/health")) {
    throw "Jarvis did not become ready"
}
Write-StartupLog "Jarvis and Ollama are healthy."
