[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipDocker
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Find-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string[]]$Fallbacks = @()
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    foreach ($candidate in $Fallbacks) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    return $null
}

Write-Host '== AUSM Smart RAG setup ==' -ForegroundColor Cyan

$PyLauncher = Find-Executable -Name 'py.exe'
if (-not $PyLauncher) {
    throw 'Python launcher not found. Install 64-bit Python 3.12, reopen PowerShell, and rerun.'
}
& $PyLauncher -3.12 --version
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.12 is required. Install it with the Windows py launcher enabled.'
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host 'Creating .venv...'
    & $PyLauncher -3.12 -m venv .venv
}

Write-Host 'Installing Python dependencies...'
& $VenvPython -m pip install --upgrade pip
Write-Host 'The first install downloads local document, AI support, and UI wheels; later runs use pip cache.'
& $VenvPython -m pip install --prefer-binary -r requirements-dev.txt
& $VenvPython -m pip check

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env from .env.example.'
} else {
    Write-Host 'Keeping existing .env.'
}

if (-not $SkipModels) {
    $Ollama = Find-Executable -Name 'ollama.exe' -Fallbacks @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
    )
    if (-not $Ollama) {
        throw 'Ollama was not found. Install/start Ollama, reopen PowerShell, and rerun setup.'
    }
    & $Ollama list | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Ollama is installed but not responding. Start Ollama, then rerun setup.'
    }
    Write-Host 'Ensuring Ollama models are available (downloads occur only when missing)...'
    $InstalledModels = (& $Ollama list | Out-String)
    if ($InstalledModels -notmatch '(?m)^gemma4:e4b\s') {
        & $Ollama pull 'gemma4:e4b'
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not pull gemma4:e4b. Check the model name and Ollama connectivity.'
        }
    }
    if ($InstalledModels -notmatch '(?m)^embeddinggemma(?::latest)?\s') {
        & $Ollama pull 'embeddinggemma'
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not pull embeddinggemma. Check Ollama connectivity.'
        }
    }
}

if (-not $SkipDocker) {
    $Docker = Find-Executable -Name 'docker.exe' -Fallbacks @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
    )
    if (-not $Docker) {
        throw 'Docker CLI not found. Install Docker Desktop, reopen PowerShell, and rerun setup.'
    }
    & $Docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop is installed but its engine is not running. Start it and rerun setup.'
    }
    Write-Host 'Starting Qdrant...'
    & $Docker compose up -d

    $Deadline = (Get-Date).AddSeconds(60)
    $QdrantReady = $false
    do {
        try {
            $HealthResponse = Invoke-RestMethod -Uri 'http://localhost:6333/healthz' `
                -TimeoutSec 3
            $QdrantReady = $HealthResponse -match 'passed'
            if ($QdrantReady) {
                break
            }
        } catch {
            $QdrantReady = $false
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $Deadline)

    if (-not $QdrantReady) {
        & $Docker compose ps
        throw 'Qdrant did not become healthy within 60 seconds. Run docker compose logs qdrant.'
    }
    Write-Host 'Qdrant is healthy.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host 'Start the API with:'
Write-Host '  .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload'
Write-Host 'Start the Streamlit UI in another terminal with:'
Write-Host '  .\.venv\Scripts\python.exe -m streamlit run frontend/app.py'
Write-Host 'Then open http://127.0.0.1:8501'
Write-Host 'API documentation remains available at http://127.0.0.1:8000/docs'
Write-Host 'Run .\scripts\doctor.ps1 at any time to verify the installation.'
