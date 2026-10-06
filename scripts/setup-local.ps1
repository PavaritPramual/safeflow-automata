param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not (Test-Path -LiteralPath '.env')) {
    $randomBytes = [byte[]]::new(32)
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $randomGenerator.GetBytes($randomBytes)
    $randomGenerator.Dispose()
    $apiKey = [BitConverter]::ToString($randomBytes).Replace('-', '')
    "SAFEFLOW_API_KEY=$apiKey" | Set-Content -Encoding utf8 .env
}
$keyLine = Get-Content -LiteralPath .env | Where-Object { $_.StartsWith('SAFEFLOW_API_KEY=') } | Select-Object -First 1
$apiKey = $keyLine.Substring('SAFEFLOW_API_KEY='.Length)
if ($apiKey.Length -lt 24) { throw 'SAFEFLOW_API_KEY is too short' }
New-Item -ItemType Directory -Force docker/ha-data | Out-Null
"safeflow_api_key: '$apiKey'" | Set-Content -Encoding utf8 docker/ha-config/secrets.yaml
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
& ./.venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'package installation failed' }
Write-Output 'Local key and virtual environment ready. No credential was printed.'
