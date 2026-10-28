param([ValidateSet('supervise','preflight','recover')][string]$Action='supervise',[switch]$Detached)
$ErrorActionPreference='Stop'
$cRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$cRaw=Join-Path $cRoot 'results\bench\api_bppb_100k'
New-Item -ItemType Directory -Path $cRaw -Force | Out-Null
if ($Detached) {
    if (Test-Path -LiteralPath (Join-Path $cRaw 'launcher.json')) { throw 'Existing launcher receipt; refusing duplicate' }
    $cProcess=Start-Process powershell.exe -WindowStyle Hidden -WorkingDirectory $cRoot `
        -ArgumentList @('-NoProfile','-NonInteractive','-File',('"'+$PSCommandPath+'"'),'-Action',$Action) `
        -RedirectStandardOutput (Join-Path $cRaw 'worker.stdout.log') -RedirectStandardError (Join-Path $cRaw 'worker.stderr.log') -PassThru
    @{pid=$cProcess.Id;at_wib=[datetimeoffset]::Now.ToString('o');detached=$true;progress_interval_seconds=1200} |
        ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRaw 'launcher.json')
    Write-Output "Detached API supervisor launcher PID $($cProcess.Id)"
    exit 0
}
$env:DPR_OPENBAO_HTTP_TRANSPORT='https_pool'
$env:DPR_BENCH_DEK_CACHE_TTL='0'
$cScanner=Import-Clixml -LiteralPath 'C:\dev\dpr-private\scanner_user.credential.xml'
$env:SCANNER_DATABASE_URL='postgresql://scanner_user:'+ [uri]::EscapeDataString($cScanner.GetNetworkCredential().Password)+'@127.0.0.1:5433/baseline_100k?sslmode=disable'
Remove-Variable cScanner
# Go/k6 on Windows uses the Windows certificate store. Trust this lab CA only
# for the lifetime of this launcher; never disable TLS verification.
$cCertificate=[System.Security.Cryptography.X509Certificates.X509Certificate2]::new('C:\dev\dpr-private\openbao\tls\ca.crt')
$cStore=[System.Security.Cryptography.X509Certificates.X509Store]::new('Root','CurrentUser')
$cStore.Open('ReadWrite')
$cAdded=$cStore.Certificates.Find('FindByThumbprint',$cCertificate.Thumbprint,$false).Count -eq 0
$cTrust=@{thumbprint=$cCertificate.Thumbprint;store='CurrentUser/Root';added_by_launcher=$cAdded;removed=$false;at_wib=[datetimeoffset]::Now.ToString('o')}
try {
    if ($cAdded) { $cStore.Add($cCertificate) }
    $cTrust | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRaw 'ca_trust.json')
    & powershell.exe -NoProfile -NonInteractive -File 'C:\dev\dpr-private\benchmark\bppb-launch.ps1' -m benchmark.api $Action
    $cExit=$LASTEXITCODE
} finally {
    if ($cAdded) { $cStore.Remove($cCertificate); $cTrust.removed=$true }
    $cStore.Close()
    $cTrust | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRaw 'ca_trust.json')
    Remove-Item Env:SCANNER_DATABASE_URL -ErrorAction SilentlyContinue
}
exit $cExit
