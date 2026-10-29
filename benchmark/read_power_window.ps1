param(
    [Parameter(Mandatory=$true)][datetimeoffset]$StartUtc,
    [Parameter(Mandatory=$true)][datetimeoffset]$EndUtc
)
$ErrorActionPreference = 'Stop'
$cFilter = @{ LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=105 }
$cPreviousFilter = $cFilter.Clone()
$cPreviousFilter.EndTime = $StartUtc.LocalDateTime
$cPrevious = Get-WinEvent -FilterHashtable $cPreviousFilter -MaxEvents 1 -ErrorAction Stop
$cWindowFilter = $cFilter.Clone()
$cWindowFilter.StartTime = $StartUtc.LocalDateTime
$cWindowFilter.EndTime = $EndUtc.LocalDateTime
try {
    $cWindow = @(Get-WinEvent -FilterHashtable $cWindowFilter -ErrorAction Stop)
} catch {
    if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }
    $cWindow = @()
}
$cRows = @(foreach ($cEvent in @($cPrevious) + $cWindow) {
    $cXml = [xml]$cEvent.ToXml()
    $cAc = @($cXml.Event.EventData.Data | Where-Object { $_.Name -eq 'AcOnline' })
    if ($cAc.Count -ne 1) { throw 'Power source event missing AC state' }
    [ordered]@{
        record_id = $cEvent.RecordId
        event_id = $cEvent.Id
        time_utc = ([datetimeoffset]$cEvent.TimeCreated).ToUniversalTime().ToString('o')
        time_wib = ([datetimeoffset]$cEvent.TimeCreated).ToOffset([timespan]::FromHours(7)).ToString('o')
        ac_online = ([string]$cAc[0].'#text').ToLowerInvariant() -eq 'true'
    }
})
[ordered]@{
    provider='Microsoft-Windows-Kernel-Power'
    log_name='System'
    query_start_utc=$StartUtc.ToUniversalTime().ToString('o')
    query_end_utc=$EndUtc.ToUniversalTime().ToString('o')
    latest_event_at_or_before_start=$cRows[0]
    events_in_window=@($cRows | Select-Object -Skip 1)
} | ConvertTo-Json -Depth 6 -Compress
