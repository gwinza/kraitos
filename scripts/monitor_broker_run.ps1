# Monitor partial broker validation; regenerate expectancy report when ready.
param(
    [int]$ClosedTarget = 50,
    [int]$PollSeconds = 120
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Journal = Join-Path $Root "logs\broker_partial_journal.csv"
$Log = Get-ChildItem (Join-Path $Root "logs\broker_partial_*.log") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

function Get-ClosedCount {
    if (-not (Test-Path $Journal)) { return 0 }
    $rows = Import-Csv $Journal
    return @($rows | Where-Object { $_.result -in @("win", "loss", "breakeven") }).Count
}

Write-Output "broker_monitor: watching journal=$Journal target_closed=$ClosedTarget poll=${PollSeconds}s"

while ($true) {
    $closed = Get-ClosedCount
    $proc = Get-Process python -ErrorAction SilentlyContinue
    $running = $null -ne $proc
    $logSize = if ($Log) { $Log.Length } else { 0 }

    Write-Output "broker_monitor: closed=$closed running=$running log_bytes=$logSize"

    if ($closed -ge $ClosedTarget -or (-not $running -and $closed -gt 0)) {
        Set-Location $Root
        python scripts/generate_broker_expectancy_report.py
        Write-Output "AGENT_LOOP_WAKE_broker_monitor report_ready closed=$closed"
        break
    }

    if (-not $running -and $closed -eq 0) {
        Write-Output "AGENT_LOOP_WAKE_broker_monitor broker_stopped_no_trades"
        break
    }

    Start-Sleep -Seconds $PollSeconds
}
