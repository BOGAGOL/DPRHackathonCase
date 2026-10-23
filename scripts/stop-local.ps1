$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot '.local/processes.json'
if (Test-Path -LiteralPath $processFile) {
    $ownedProcesses = Get-Content -LiteralPath $processFile | ConvertFrom-Json
    foreach ($processEntry in @($ownedProcesses.api, $ownedProcesses.web)) {
        $ownedProcess = Get-Process -Id $processEntry.id -ErrorAction SilentlyContinue
        if ($ownedProcess) {
            if ($ownedProcess.StartTime.ToUniversalTime().Ticks -ne [long]$processEntry.started_ticks -or $ownedProcess.ProcessName -notin @('python','node')) {
                throw "Refusing to stop PID $($processEntry.id): process identity changed. Launcher metadata retained for inspection."
            }
            & taskkill.exe /PID $processEntry.id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Failed to stop owned PID $($processEntry.id)." }
        }
    }
    Remove-Item -LiteralPath $processFile
}
Set-Location -LiteralPath $projectRoot
& '.venv/Scripts/python.exe' scripts/local_database.py stop
