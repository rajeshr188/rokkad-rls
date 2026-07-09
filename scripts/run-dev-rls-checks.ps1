param(
    [switch]$IncludeStrictCheck
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe. Create/activate .venv first."
}

$envPath = Join-Path $repoRoot ".env"
if (-not (Test-Path $envPath)) {
    throw ".env not found at $envPath"
}

$envMap = @{}
foreach ($line in Get-Content $envPath) {
    if ($line.StartsWith("#") -or -not $line.Contains("=")) {
        continue
    }
    $parts = $line.Split("=", 2)
    $envMap[$parts[0].Trim()] = $parts[1].Trim().Trim('"')
}

# Force runtime DB connection values from .env so stale shell vars cannot skew checks.
foreach ($key in @("DB_ENGINE", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")) {
    if ($envMap.ContainsKey($key) -and $envMap[$key]) {
        Set-Item -Path ("Env:" + $key) -Value $envMap[$key]
    }
}

Push-Location $repoRoot
try {
    Write-Host "[1/4] Running Django system check..." -ForegroundColor Cyan
    & $pythonExe manage.py check
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py check failed with exit code $LASTEXITCODE"
    }

    Write-Host "[2/4] Verifying no missing policy migrations..." -ForegroundColor Cyan
    & $pythonExe manage.py makerlspolicies --check
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py makerlspolicies --check failed with exit code $LASTEXITCODE"
    }

    Write-Host "[3/4] Running local RLS safety check (allow owned tables)..." -ForegroundColor Cyan
    & $pythonExe manage.py check_rls --allow-owned-tables
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py check_rls --allow-owned-tables failed with exit code $LASTEXITCODE"
    }

    Write-Host "[4/4] Running tenant FK safety guard tests..." -ForegroundColor Cyan
    & $pythonExe manage.py test core.tests_rls_foundation --pattern="*tests_rls_foundation.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Tenant FK safety guard tests failed with exit code $LASTEXITCODE"
    }

    if ($IncludeStrictCheck) {
        Write-Host "[extra] Running strict RLS safety check..." -ForegroundColor Yellow
        & $pythonExe manage.py check_rls
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Strict check_rls failed. This indicates runtime role ownership/BYPASSRLS drift or policy regression." -ForegroundColor Red
            throw "manage.py check_rls failed with exit code $LASTEXITCODE"
        } else {
            Write-Host "Strict check_rls passed." -ForegroundColor Green
        }
    }

    Write-Host "All development RLS checks completed successfully." -ForegroundColor Green
}
finally {
    Pop-Location
}
