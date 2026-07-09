param(
    [string]$MigrationRole,
    [string]$MigrationPassword,
    [string]$RuntimeRole,
    [string]$RuntimePassword,
    [switch]$UseDirectMigrationLogin,
    [string[]]$MigrateArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe. Create/activate .venv first."
}

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

$dbEngine = $envMap["DB_ENGINE"]
$dbName = $envMap["DB_NAME"]
$dbHost = $envMap["DB_HOST"]
$dbPort = $envMap["DB_PORT"]

if (-not $dbEngine -or $dbEngine.ToLower() -ne "postgres") {
    throw "DB_ENGINE in .env must be 'postgres' for owner-role migrations."
}
if (-not $dbName -or -not $dbHost -or -not $dbPort) {
    throw "Missing DB_NAME/DB_HOST/DB_PORT in .env"
}

$runtimeRoleFromEnv = $envMap["DB_USER"]
$runtimePasswordFromEnv = $envMap["DB_PASSWORD"]

if (-not $runtimeRoleFromEnv -or -not $runtimePasswordFromEnv) {
    throw "Missing DB_USER/DB_PASSWORD in .env"
}

if (-not $RuntimeRole) {
    $RuntimeRole = $runtimeRoleFromEnv
}
if (-not $RuntimePassword) {
    $RuntimePassword = $runtimePasswordFromEnv
}

if (-not $MigrationRole) {
    if ($runtimeRoleFromEnv.EndsWith("_user")) {
        $MigrationRole = $runtimeRoleFromEnv.Substring(0, $runtimeRoleFromEnv.Length - 5) + "_migration_owner"
    } else {
        throw "Could not infer migration role from DB_USER. Pass -MigrationRole explicitly."
    }
}
if (-not $MigrationPassword) {
    $MigrationPassword = $RuntimePassword
}

if (-not $MigrateArgs) {
    $MigrateArgs = @("--noinput")
}

$oldValues = @{}
foreach ($key in @("DB_ENGINE", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")) {
    $oldValues[$key] = (Get-Item -Path ("Env:" + $key) -ErrorAction SilentlyContinue).Value
}

Push-Location $repoRoot
try {
    Write-Host "Preparing owner-role migration on database '$dbName'..." -ForegroundColor Cyan

    Set-Item -Path Env:DB_ENGINE -Value "postgres"
    Set-Item -Path Env:DB_NAME -Value $dbName
    Set-Item -Path Env:DB_HOST -Value $dbHost
    Set-Item -Path Env:DB_PORT -Value $dbPort

    if ($UseDirectMigrationLogin) {
        Write-Host "Using direct migration-role login '$MigrationRole'." -ForegroundColor Yellow
        Set-Item -Path Env:DB_USER -Value $MigrationRole
        Set-Item -Path Env:DB_PASSWORD -Value $MigrationPassword
        Remove-Item -Path Env:PGOPTIONS -ErrorAction SilentlyContinue
    } else {
        Write-Host "Using runtime login '$RuntimeRole' with SET ROLE '$MigrationRole'." -ForegroundColor Yellow
        Set-Item -Path Env:DB_USER -Value $RuntimeRole
        Set-Item -Path Env:DB_PASSWORD -Value $RuntimePassword
        Remove-Item -Path Env:PGOPTIONS -ErrorAction SilentlyContinue

        $env:PGPASSWORD = $RuntimePassword
        psql -h $dbHost -p $dbPort -U $RuntimeRole -d $dbName -v ON_ERROR_STOP=1 -c "SELECT current_user, current_role;" -c "SET ROLE $MigrationRole;" -c "SELECT current_user, current_role;" -c "RESET ROLE;" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime role '$RuntimeRole' cannot SET ROLE '$MigrationRole'. Run role hardening first or use -UseDirectMigrationLogin."
        }

        # In mixed-owner local setups, ensure migration role can access Django
        # metadata tables that post_migrate touches (content types, permissions, etc.).
        psql -h $dbHost -p $dbPort -U $RuntimeRole -d $dbName -v ON_ERROR_STOP=1 `
            -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $MigrationRole;" `
            -c "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $MigrationRole;" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to grant schema table/sequence access to '$MigrationRole'."
        }

        Set-Item -Path Env:PGOPTIONS -Value "-c role=$MigrationRole"
    }

    Write-Host "Running migrations..." -ForegroundColor Cyan

    & $pythonExe manage.py migrate @MigrateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py migrate failed with exit code $LASTEXITCODE"
    }

    Write-Host "Migration completed successfully." -ForegroundColor Green
}
finally {
    foreach ($key in $oldValues.Keys) {
        if ($null -eq $oldValues[$key]) {
            Remove-Item -Path ("Env:" + $key) -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path ("Env:" + $key) -Value $oldValues[$key]
        }
    }

    Pop-Location
}

Write-Host "Runtime role in .env remains '$RuntimeRole'." -ForegroundColor Yellow
