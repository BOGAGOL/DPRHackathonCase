param(
    [datetimeoffset]$StartWib = [datetimeoffset]'2026-10-27T00:00:00+07:00',
    [datetimeoffset]$EndWib = [datetimeoffset]'2026-10-27T20:50:00+07:00'
)
$ErrorActionPreference = 'Stop'
$cRepoRoot = Split-Path -Parent $PSScriptRoot
$cOutput = Join-Path $cRepoRoot 'evidence\benchmark\baseline_1m\power_events.json'
$cEvents = @(Get-WinEvent -FilterHashtable @{
    LogName = 'System'
    ProviderName = 'Microsoft-Windows-Kernel-Power'
    Id = @(105, 506, 507, 566)
    StartTime = $StartWib.LocalDateTime
    EndTime = $EndWib.LocalDateTime
} -ErrorAction Stop)
$cSupportStart = [datetimeoffset]'2026-10-27T18:25:00+07:00'
$cSupportEnd = [datetimeoffset]'2026-10-27T19:35:00+07:00'
$cRows = @(foreach ($cEvent in ($cEvents | Sort-Object TimeCreated, RecordId)) {
    $cAt = [datetimeoffset]$cEvent.TimeCreated
    if ($cEvent.Id -ne 105 -and ($cAt -lt $cSupportStart -or $cAt -gt $cSupportEnd)) { continue }
    $cXml = [xml]$cEvent.ToXml()
    $cData = [ordered]@{}
    foreach ($cItem in $cXml.Event.EventData.Data) {
        $cData[[string]$cItem.Name] = [string]$cItem.'#text'
    }
    [ordered]@{
        event_id = $cEvent.Id
        record_id = $cEvent.RecordId
        time_utc = $cAt.ToUniversalTime().ToString('o')
        time_wib = $cAt.ToOffset([timespan]::FromHours(7)).ToString('o')
        data = $cData
        message = $cEvent.Message
    }
})
$cReport = [ordered]@{
    status = 'READ_SUCCESS'
    collected_at_utc = [datetimeoffset]::UtcNow.ToString('o')
    provider = 'Microsoft-Windows-Kernel-Power'
    log_name = 'System'
    windows_timezone = [TimeZoneInfo]::Local.Id
    query_start_wib = $StartWib.ToString('o')
    query_end_wib = $EndWib.ToString('o')
    scope = 'All event 105 source changes in day window; supporting 506/507/566 only 18:25-19:35 WIB. Computer/user identifiers omitted.'
    events = $cRows
}
$cJson = $cReport | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText($cOutput, $cJson + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
[pscustomobject]@{ status = 'READ_SUCCESS'; events = $cRows.Count; file = 'evidence/benchmark/baseline_1m/power_events.json' } | ConvertTo-Json -Compress
