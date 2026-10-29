param([ValidateSet('supervise','preflight','recover')][string]$Action='supervise',[switch]$Detached,
      [string]$LabCaFile='C:\dev\dpr-private\openbao\tls\ca.crt')
$ErrorActionPreference='Stop'
$cRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$cRaw=Join-Path $cRoot 'results\bench\api_bppb_100k'
New-Item -ItemType Directory -Path $cRaw -Force | Out-Null
# k6 uses the Windows trust store. Never open a hidden Windows Security Warning.
# Recovery uses Python CA files and must not depend on k6/user-store readiness.
if ($Action -eq 'supervise') {
    $cCertificate=[System.Security.Cryptography.X509Certificates.X509Certificate2]::new($LabCaFile)
    $cStore=[System.Security.Cryptography.X509Certificates.X509Store]::new('Root','CurrentUser')
    $cStore.Open('ReadOnly')
    try { $cTrusted=$cStore.Certificates.Find('FindByThumbprint',$cCertificate.Thumbprint,$false).Count -gt 0 }
    finally { $cStore.Close() }
    $cTrust=@{thumbprint=$cCertificate.Thumbprint;store='CurrentUser/Root';trusted_before_launch=$cTrusted;
        added_by_launcher=$false;removed=$false;at_wib=[datetimeoffset]::Now.ToString('o');
        status=if($cTrusted){'TRUSTED'}else{'OPERATOR_CA_TRUST_REQUIRED'}}
    $cTrust | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRaw 'ca_trust.json')
    if (-not $cTrusted) { throw 'Operator must trust the verified lab CA in CurrentUser/Root before detached API launch' }
    $cLifecycleFile=Join-Path $cRoot 'evidence\benchmark\api_bppb_100k\ca_lifecycle.json'
    if(-not (Test-Path -LiteralPath $cLifecycleFile)){
        @{thumbprint=$cCertificate.Thumbprint;store='CurrentUser/Root';status='IMPORTED_BY_OPERATOR_OBSERVED';
          operator_reported_import=$true;import_observed_at_wib=[datetimeoffset]::Now.ToString('o');
          trusted_before_run=$true;operator_authorized_removal=$true;removal_verified=$false} |
            ConvertTo-Json | Set-Content -LiteralPath $cLifecycleFile -Encoding UTF8
    }
}
if ($Detached) {
    if (Test-Path -LiteralPath (Join-Path $cRaw 'launcher.json')) { throw 'Existing launcher receipt; refusing duplicate' }
    $cProcess=Start-Process powershell.exe -WindowStyle Hidden -WorkingDirectory $cRoot `
        -ArgumentList @('-NoProfile','-NonInteractive','-File',('"'+$PSCommandPath+'"'),'-Action',$Action,'-LabCaFile',('"'+$LabCaFile+'"')) `
        -RedirectStandardOutput (Join-Path $cRaw 'worker.stdout.log') -RedirectStandardError (Join-Path $cRaw 'worker.stderr.log') -PassThru
    @{pid=$cProcess.Id;at_wib=[datetimeoffset]::Now.ToString('o');detached=$true;progress_interval_seconds=1800} |
        ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $cRaw 'launcher.json')
    Write-Output "Detached API supervisor launcher PID $($cProcess.Id)"
    exit 0
}
$cExit=1
try {
    $env:DPR_OPENBAO_HTTP_TRANSPORT='https_pool'
    $env:DPR_BENCH_DEK_CACHE_TTL='0'
    $cScanner=Import-Clixml -LiteralPath 'C:\dev\dpr-private\scanner_user.credential.xml'
    $env:SCANNER_DATABASE_URL='postgresql://scanner_user:'+ [uri]::EscapeDataString($cScanner.GetNetworkCredential().Password)+'@127.0.0.1:5433/baseline_100k?sslmode=disable'
    Remove-Variable cScanner
    & powershell.exe -NoProfile -NonInteractive -File 'C:\dev\dpr-private\benchmark\bppb-launch.ps1' -m benchmark.api $Action
    $cExit=$LASTEXITCODE
} finally {
    Remove-Item Env:SCANNER_DATABASE_URL -ErrorAction SilentlyContinue
    if($Action -eq 'supervise'){
        & powershell.exe -NoProfile -NonInteractive -File (Join-Path $PSScriptRoot 'ca_cleanup.ps1') -EvidenceFile $cLifecycleFile
        $cCleanupExit=$LASTEXITCODE
        $cLifecycle=Get-Content -LiteralPath $cLifecycleFile -Raw | ConvertFrom-Json
        $cNote="`n`n## API CA lifecycle (operator instruction29Oct)`n`nOperator imported lab CA $($cLifecycle.thumbprint); first observed $($cLifecycle.import_observed_at_wib). After supervisor/DB cleanup, Remove-Item targeted only that certificate in CurrentUser/Root. Status $($cLifecycle.status), absence verified $($cLifecycle.removal_verified), completed $($cLifecycle.cleanup_completed_at_wib). Evidence: evidence/benchmark/api_bppb_100k/ca_lifecycle.json. No root token, issuance or TLS downgrade.`n"
        Add-Content -LiteralPath (Join-Path $cRoot 'benchmark\NOTES.md') -Value $cNote -Encoding UTF8
        $cBranch=(& git -C $cRoot branch --show-current).Trim()
        if($cBranch -ne 'perf/keyservice-latency'){throw 'Refuse CA evidence publication on another branch'}
        & git -C $cRoot add -- benchmark/NOTES.md evidence/benchmark/api_bppb_100k evidence/benchmark/api_bppb_compare.json
        if($LASTEXITCODE -ne 0){throw 'CA evidence git add failed'}
        & git -C $cRoot commit --only -m ('evidence: API CA cleanup status '+$cLifecycle.status) -- benchmark/NOTES.md evidence/benchmark/api_bppb_100k evidence/benchmark/api_bppb_compare.json
        if($LASTEXITCODE -ne 0){throw 'CA evidence git commit failed'}
        & git -C $cRoot push origin HEAD:refs/heads/perf/keyservice-latency
        if($LASTEXITCODE -ne 0){throw 'CA evidence git push failed'}
        @{status='PUSHED';commit=(& git -C $cRoot rev-parse HEAD).Trim();at_wib=[datetimeoffset]::Now.ToString('o')} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cRaw 'ca_publication.json') -Encoding UTF8
        if($cCleanupExit -ne 0){throw 'CA removal not verified; see ca_lifecycle.json'}
    }
}
exit $cExit
