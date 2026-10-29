param(
    [ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$Thumbprint='FC95F6CA26E050CAB0C16B17B3F4A20441FA8440',
    [string]$EvidenceFile=(Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'evidence\benchmark\api_bppb_100k\ca_lifecycle.json')
)
$ErrorActionPreference='Stop'
$cCertificatePath='Cert:\CurrentUser\Root\'+$Thumbprint.ToUpperInvariant()
$cPrevious=if(Test-Path -LiteralPath $EvidenceFile){Get-Content -LiteralPath $EvidenceFile -Raw | ConvertFrom-Json}else{$null}
$cRecord=[ordered]@{
    thumbprint=$Thumbprint.ToUpperInvariant();store='CurrentUser/Root';
    operator_reported_import=$true;import_observed_at_wib=$cPrevious.import_observed_at_wib;
    trusted_before_run=$cPrevious.trusted_before_run;operator_authorized_removal=$true;
    cleanup_started_at_wib=[datetimeoffset]::Now.ToString('o');
    removal_command=('Remove-Item '+$cCertificatePath);status='REMOVAL_FAILED';removal_verified=$false
}
$cExit=2
try {
    $cRecord.present_before_removal=Test-Path -LiteralPath $cCertificatePath
    if($cRecord.present_before_removal){Remove-Item -LiteralPath $cCertificatePath -ErrorAction Stop}
    $cRecord.removal_verified= -not (Test-Path -LiteralPath $cCertificatePath)
    if(-not $cRecord.removal_verified){throw 'Lab CA still present after removal'}
    $cRecord.status='REMOVED_VERIFIED';$cExit=0
} catch {
    $cRecord.error_type=$_.Exception.GetType().Name
} finally {
    $cRecord.cleanup_completed_at_wib=[datetimeoffset]::Now.ToString('o')
    $cRecord | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidenceFile -Encoding UTF8
}
exit $cExit
