$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8000"

function Get-RunState($runId) {
    return Invoke-RestMethod -Uri "$BaseUrl/api/runs/$runId" -Method GET
}

function Wait-ForTimelineType($runId, $type, $timeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    do {
        $state = Get-RunState $runId
        if ($state.timeline | Where-Object { $_.type -eq $type }) {
            return $state
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for timeline type '$type'"
}

function Wait-ForTerminalRun($runId, $timeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    do {
        $state = Get-RunState $runId
        if ($state.status -in @("completed", "terminated", "failed")) {
            return $state
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for terminal run"
}

Write-Host "`n=== Phase 2 happy-path test ===" -ForegroundColor Cyan

Write-Host "`n1) Health"
Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET | ConvertTo-Json -Depth 10

Write-Host "`n2) Create supervisor"
$supervisorBody = @{
    name = "Phase 2 Demo Supervisor"
    base_instruction = "Supervise the order. If shipment is delayed or payment fails, escalate immediately. When delivered, close the workflow."
    tools_enabled = @(
        "send_customer_message",
        "create_internal_note",
        "escalate_issue",
        "mark_order_for_review",
        "schedule_next_wake_up",
        "close_workflow"
    )
    wake_aggressiveness = "high"
    model_config = @{
        model = "gemini-3.6-flash"
        temperature = 0.2
    }
} | ConvertTo-Json -Depth 10

$supervisor = Invoke-RestMethod `
    -Uri "$BaseUrl/api/supervisors" `
    -Method POST `
    -ContentType "application/json" `
    -Body $supervisorBody
$supervisor | ConvertTo-Json -Depth 10
$SUPERVISOR_ID = $supervisor.id
Write-Host "SUPERVISOR_ID=$SUPERVISOR_ID" -ForegroundColor Green

Write-Host "`n3) Start run"
$orderId = "ORDER-P2-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$runBody = @{
    order_id = $orderId
    supervisor_id = $SUPERVISOR_ID
    default_wake_seconds = 60
} | ConvertTo-Json

$run = Invoke-RestMethod `
    -Uri "$BaseUrl/api/runs" `
    -Method POST `
    -ContentType "application/json" `
    -Body $runBody
$run | ConvertTo-Json -Depth 10
$RUN_ID = $run.run_id
Write-Host "RUN_ID=$RUN_ID" -ForegroundColor Green

Write-Host "`nWaiting for workflow_start Gemini decision..."
$state = Wait-ForTimelineType $RUN_ID "agent_decision" 60
$state | ConvertTo-Json -Depth 20

Write-Host "`n4) Add run-specific instruction"
$instructionBody = @{
    text = "If shipment is delayed, escalate immediately using escalate_issue."
} | ConvertTo-Json
Invoke-RestMethod `
    -Uri "$BaseUrl/api/runs/$RUN_ID/instructions" `
    -Method POST `
    -ContentType "application/json" `
    -Body $instructionBody | ConvertTo-Json -Depth 10
Start-Sleep -Seconds 3

Write-Host "`n5) Send shipment_delayed event"
$delayBody = @{
    type = "shipment_delayed"
    payload = @{
        delay_hours = 4
        carrier = "Demo Carrier"
    }
} | ConvertTo-Json -Depth 10
Invoke-RestMethod `
    -Uri "$BaseUrl/api/runs/$RUN_ID/events" `
    -Method POST `
    -ContentType "application/json" `
    -Body $delayBody | ConvertTo-Json -Depth 10

Write-Host "Waiting for classifier + Gemini + tool processing..."
Start-Sleep -Seconds 8
$state = Get-RunState $RUN_ID
$state | ConvertTo-Json -Depth 20

Write-Host "`n6) Send delivered terminal event"
$deliveredBody = @{
    type = "delivered"
    payload = @{
        delivered_at = [DateTime]::UtcNow.ToString("o")
    }
} | ConvertTo-Json -Depth 10
Invoke-RestMethod `
    -Uri "$BaseUrl/api/runs/$RUN_ID/events" `
    -Method POST `
    -ContentType "application/json" `
    -Body $deliveredBody | ConvertTo-Json -Depth 10

Write-Host "Waiting for final Gemini summary + Supabase fallback..."
$completed = Wait-ForTerminalRun $RUN_ID 90
$completed | ConvertTo-Json -Depth 20

Write-Host "`n7) Fetch final summary"
$final = Invoke-RestMethod -Uri "$BaseUrl/api/runs/$RUN_ID/final-summary" -Method GET
$final | ConvertTo-Json -Depth 20

Write-Host "`n8) Verify completed run rejects new signals (409 expected)"
try {
    Invoke-RestMethod `
        -Uri "$BaseUrl/api/runs/$RUN_ID/events" `
        -Method POST `
        -ContentType "application/json" `
        -Body $delayBody
    Write-Host "ERROR: signal was unexpectedly accepted" -ForegroundColor Red
} catch {
    Write-Host "Expected rejection received:" -ForegroundColor Green
    Write-Host $_.Exception.Message
}

Write-Host "`n=== Phase 2 happy-path test complete ===" -ForegroundColor Cyan
Write-Host "SUPERVISOR_ID=$SUPERVISOR_ID"
Write-Host "RUN_ID=$RUN_ID"
Write-Host "Use scripts\phase2_db_checks.sql in Supabase SQL Editor with this RUN_ID."
