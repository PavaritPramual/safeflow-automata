param([int]$Seconds = 30, [string]$Output = 'logs/resource-samples.json')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$samples = @()
$deadline = (Get-Date).AddSeconds($Seconds)
do {
    $ollamaSnapshot = Invoke-RestMethod http://127.0.0.1:11434/api/ps
    $haSnapshot = docker stats --no-stream --format '{{json .}}' safeflow-homeassistant | ConvertFrom-Json
    $ownedModelProcesses = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -match '\\Ollama\\' }
    $modelMemory = @($ownedModelProcesses | ForEach-Object {
        $process = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        if ($process) { [ordered]@{name=$process.ProcessName; pid=$process.Id; working_set_bytes=$process.WorkingSet64} }
    })
    $backendMemory = @(Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id,WorkingSet64)
    $vmMemory = @(Get-Process -Name vmmemWSL -ErrorAction SilentlyContinue | Select-Object Id,WorkingSet64)
    $samples += [ordered]@{timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); ollama=$ollamaSnapshot;
        model_processes=$modelMemory; python_processes=$backendMemory; docker=$haSnapshot; wsl=$vmMemory}
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
$report = [ordered]@{host_ram_bytes=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;
    target_ram_bytes=8589934592; samples=$samples;
    note='Sampled process/container memory, not a hard limit or proof of 8 GB compatibility. WSL includes shared overhead; do not add container RAM to WSL RAM as independent allocations.'}
$report | ConvertTo-Json -Depth 15 | Set-Content -Encoding utf8 $Output
Write-Output "Resource samples saved: $Output ($($samples.Count) samples)"
