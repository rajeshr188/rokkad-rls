param(
    [string]$AdminUser,
    [string]$AdminPassword,
    [string]$MigrationRole = "rls_rokkad_migration_owner",
    [string]$RuntimeRole = "rls_rokkad_user"
)

$ErrorActionPreference = "Stop"

if (-not $AdminUser -or -not $AdminPassword) {
    throw "Provide -AdminUser and -AdminPassword for a PostgreSQL superuser/schema-owner account."
}

$envMap = @{}
foreach ($line in Get-Content ".env") {
    if ($line.StartsWith("#") -or -not $line.Contains("=")) {
        continue
    }
    $parts = $line.Split("=", 2)
    $envMap[$parts[0].Trim()] = $parts[1].Trim().Trim('"')
}

$dbName = $envMap["DB_NAME"]
$dbHost = $envMap["DB_HOST"]
$dbPort = $envMap["DB_PORT"]

if (-not $dbName -or -not $dbHost -or -not $dbPort) {
    throw "Missing DB_NAME/DB_HOST/DB_PORT in .env"
}

$env:PGPASSWORD = $AdminPassword

Write-Host "Applying local role hardening SQL as admin user '$AdminUser'..." -ForegroundColor Cyan
psql -h $dbHost -p $dbPort -U $AdminUser -d $dbName -v migration_role=$MigrationRole -v runtime_role=$RuntimeRole -f ".\scripts\dev-role-hardening.sql"
if ($LASTEXITCODE -ne 0) {
    throw "Role-hardening SQL execution failed with exit code $LASTEXITCODE"
}

Write-Host "Running strict RLS check (expected to pass after ownership fix)..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe manage.py check_rls
if ($LASTEXITCODE -ne 0) {
    throw "Strict check_rls still failing after role-hardening SQL."
}

Write-Host "Running development RLS check bundle..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1
if ($LASTEXITCODE -ne 0) {
    throw "Development RLS checks failed after role hardening."
}

Write-Host "Local role hardening and verification completed." -ForegroundColor Green
