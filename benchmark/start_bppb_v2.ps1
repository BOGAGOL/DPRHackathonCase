param([string]$PrivateLauncherPath = 'C:\dev\dpr-private\benchmark\bppb-launch.ps1')
$ErrorActionPreference = 'Stop'
$cRepoRoot = Split-Path -Parent $PSScriptRoot
$cRaw = Join-Path $cRepoRoot 'results\bench\bppb_v2'
if (!(Test-Path -LiteralPath $PrivateLauncherPath)) { throw 'Private credential launcher is missing' }
if (Test-Path -LiteralPath (Join-Path $cRaw 'worker.lock')) { throw 'Existing v2 worker/session; refusing duplicate' }
$cGate = Get-Content -Raw -LiteralPath (Join-Path $cRepoRoot 'evidence\benchmark\bppb_v2_preflight.json') | ConvertFrom-Json
if (!$cGate.passed) { throw 'Initial gate failed; no worker started' }
New-Item -ItemType Directory -Path $cRaw -Force | Out-Null
$env:DPR_OPENBAO_HTTP_TRANSPORT = 'https_pool'
$env:DPR_BENCH_DEK_CACHE_TTL = '0'
$env:DPR_BENCH_DEK_CACHE_ENTRIES = '0'
$cWorker = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -WorkingDirectory $cRepoRoot `
    -ArgumentList @('-NoProfile','-NonInteractive','-File',('"' + $PrivateLauncherPath + '"'),'-m','benchmark.paired_v2','run') `
    -RedirectStandardOutput (Join-Path $cRaw 'runner.stdout.log') `
    -RedirectStandardError (Join-Path $cRaw 'runner.stderr.log') -PassThru
[ordered]@{ launcher_pid=$cWorker.Id; started_at_wib=[datetimeoffset]::Now.ToOffset([timespan]::FromHours(7)).ToString('o');
    detached=$true; transport='https_pool'; dek_cache_ttl_seconds=0;
    stdout='results/bench/bppb_v2/runner.stdout.log'; stderr='results/bench/bppb_v2/runner.stderr.log';
    polling_interval_seconds=900; completion='Worker writes versions summary, verifies integrity, commits and pushes its own results' } |
    ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRepoRoot 'evidence\benchmark\bppb_v2_launch.json')
Write-Output "Detached v2 launcher PID $($cWorker.Id). Logs: results/bench/bppb_v2/"
