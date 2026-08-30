[CmdletBinding()]
param([switch]$RunTests)

$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Failures = 0

function Report-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    if ($Passed) {
        Write-Host "[OK]   $Name - $Detail" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red
        $script:Failures++
    }
}

Write-Host '== AUSM Smart RAG doctor ==' -ForegroundColor Cyan

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
Report-Check '.venv' (Test-Path -LiteralPath $Python) $Python
if (Test-Path -LiteralPath $Python) {
    & $Python -c 'import app.main; print(app.main.app.title)' *> $null
    Report-Check 'Python imports' ($LASTEXITCODE -eq 0) 'FastAPI application imports successfully'
    & $Python -c 'import streamlit; import frontend.api_client' *> $null
    Report-Check 'Streamlit UI' ($LASTEXITCODE -eq 0) 'frontend and Streamlit import successfully'
    & $Python -m pip check *> $null
    Report-Check 'Python packages' ($LASTEXITCODE -eq 0) 'No broken requirements'
}

$OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
$Ollama = if ($OllamaCommand) {
    $OllamaCommand.Source
} else {
    Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
}
$OllamaReady = $false
$Models = ''
if (Test-Path -LiteralPath $Ollama) {
    $Models = (& $Ollama list 2>$null | Out-String)
    $OllamaReady = $LASTEXITCODE -eq 0
}
Report-Check 'Ollama' $OllamaReady 'http://localhost:11434'
if ($OllamaReady) {
    Report-Check 'gemma4:e4b' ($Models -match '(?m)^gemma4:e4b\s') 'generation model'
    Report-Check 'embeddinggemma' ($Models -match '(?m)^embeddinggemma(?::latest)?\s') `
        'embedding model'
}

$DockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
$Docker = if ($DockerCommand) {
    $DockerCommand.Source
} else {
    Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
}
$DockerReady = $false
if (Test-Path -LiteralPath $Docker) {
    & $Docker info --format '{{.ServerVersion}}' *> $null
    $DockerReady = $LASTEXITCODE -eq 0
}
Report-Check 'Docker engine' $DockerReady 'Docker Desktop'

$QdrantReady = $false
try {
    $QdrantHealth = Invoke-RestMethod -Uri 'http://localhost:6333/healthz' -TimeoutSec 5
    $QdrantReady = $QdrantHealth -match 'passed'
} catch {
    $QdrantReady = $false
}
Report-Check 'Qdrant' $QdrantReady 'http://localhost:6333'

if ($RunTests -and (Test-Path -LiteralPath $Python)) {
    & $Python -m ruff check app frontend tests
    Report-Check 'Ruff' ($LASTEXITCODE -eq 0) 'source and tests'
    & $Python -m pytest -q
    Report-Check 'Pytest' ($LASTEXITCODE -eq 0) 'test suite'
}

if ($Failures -gt 0) {
    Write-Host "Doctor found $Failures problem(s)." -ForegroundColor Red
    exit 1
}
Write-Host 'All checks passed.' -ForegroundColor Green
