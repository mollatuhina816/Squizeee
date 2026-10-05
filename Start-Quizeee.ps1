$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop, start it, then run this script again. See RUNNING.md.'
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not ready. Start Docker Desktop and wait until its engine is running.' }
docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is required. Use a current Docker Desktop installation.' }

$environmentFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $environmentFile)) {
    function New-QuizeeeSecret {
        $bytes = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($bytes) } finally { $random.Dispose() }
        return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    }
    $dbSecret = New-QuizeeeSecret
    $jwtSecret = New-QuizeeeSecret
    @(
        "POSTGRES_PASSWORD=$dbSecret"
        "JWT_SECRET=$jwtSecret"
        'APP_ORIGIN=http://localhost:3000'
        'OPENAI_API_KEY='
        'AI_PROVIDER=gemini'
        'GEMINI_API_KEY='
        'GEMINI_QUESTION_MODEL=gemini-2.5-flash-lite'
        'ENVIRONMENT=development'
        'API_PORT=8010'
        'NEXT_PUBLIC_WS_ORIGIN=ws://localhost:8010'
    ) | Set-Content -LiteralPath $environmentFile -Encoding ascii
    Write-Host 'Created .env with unique local secrets. Keep this file private.'
}

$aiProviderLine = Get-Content -LiteralPath $environmentFile | Where-Object { $_ -match '^\s*AI_PROVIDER\s*=' } | Select-Object -Last 1
$aiProvider = if ($aiProviderLine) { ($aiProviderLine -split '=', 2)[1].Trim().Trim('"').Trim("'") } else { 'gemini' }
$aiKeyName = if ($aiProvider -eq 'openai') { 'OPENAI_API_KEY' } else { 'GEMINI_API_KEY' }
$aiKeyLines = @(Get-Content -LiteralPath $environmentFile | Where-Object { $_ -match "^\s*$aiKeyName\s*=" })
$aiKeyConfigured = $aiKeyLines.Count -gt 0 -and [bool](($aiKeyLines[-1] -split '=', 2)[1].Trim().Trim('"').Trim("'"))
if (-not $aiKeyConfigured) {
    Write-Warning "AI question generation needs $aiKeyName in .env. Add your key, then run this script again."
}

docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Read the error above, or run: docker compose logs --tail 100' }
Write-Host 'Waiting for the website to become ready...'
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if ($ready) {
    Write-Host 'Quizeee is ready: http://localhost:3000'
    Write-Host 'Choose Create a workspace to create your organization owner account.'
} else {
    Write-Warning 'Containers started, but the website has not passed the readiness check. Run: docker compose logs --tail 100'
}
