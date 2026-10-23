$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install apps/api/requirements.txt first. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) { throw 'Run python scripts/configure.py first.' }
foreach ($localPort in @(8000, 3000)) {
    $portProbe = [System.Net.Sockets.TcpClient]::new()
    try {
        $connectionAttempt = $portProbe.ConnectAsync('127.0.0.1', $localPort)
        try { $null = $connectionAttempt.Wait(500) } catch { }
        if ($portProbe.Connected) { throw "Port $localPort is already in use. Stop the existing app first." }
    } finally { $portProbe.Dispose() }
}
& $pythonExe scripts/local_database.py start
if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL startup failed.' }
$localDirectory = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Path $localDirectory -Force | Out-Null
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList 'scripts/serve.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDirectory 'api.stdout.log') -RedirectStandardError (Join-Path $localDirectory 'api.stderr.log')
$webRoot = Join-Path $projectRoot 'apps/web'
$webProcess = Start-Process -FilePath (Get-Command node).Source -ArgumentList 'node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3000' -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDirectory 'web.stdout.log') -RedirectStandardError (Join-Path $localDirectory 'web.stderr.log')
@{ api = @{ id = $apiProcess.Id; started_ticks = $apiProcess.StartTime.ToUniversalTime().Ticks }; web = @{ id = $webProcess.Id; started_ticks = $webProcess.StartTime.ToUniversalTime().Ticks } } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $localDirectory 'processes.json')
$ready = $false
for ($attemptIndex = 0; $attemptIndex -lt 30; $attemptIndex++) {
    try {
        $healthResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/api/health/ready' -UseBasicParsing -TimeoutSec 2
        if ($healthResponse.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Startup health check failed; inspect .local logs and use stop-local.ps1 to clean up owned processes.' }
Write-Host 'Local web: http://localhost:3000/login'
Write-Host 'Credentials: .local/demo-accounts.json (keep private). Stop using scripts/stop-local.ps1.'
