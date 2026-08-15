$BaseUrl = "http://localhost:8000"

Write-Host "Starting demo run..."
$run = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs" `
  -ContentType "application/json" `
  -Body '{"order_id":"ORDER-DEMO-001","default_wake_seconds":30}'

$runId = $run.run_id
Write-Host "RUN_ID=$runId"

Write-Host "Initial state:"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/runs/$runId" | ConvertTo-Json -Depth 10

Write-Host "Sending shipment_delayed event..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/events" `
  -ContentType "application/json" `
  -Body '{"type":"shipment_delayed","payload":{"carrier":"DemoShip","delay_hours":4}}'

Start-Sleep -Seconds 2
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/runs/$runId" | ConvertTo-Json -Depth 10

Write-Host "Adding instruction..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/instructions" `
  -ContentType "application/json" `
  -Body '{"text":"If delayed, prioritize speed over cost."}'

Write-Host "Pausing..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/pause"
Start-Sleep -Seconds 1

Write-Host "Sending event while paused..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/events" `
  -ContentType "application/json" `
  -Body '{"type":"payment_failed","payload":{"reason":"demo"}}'

Write-Host "State while paused (event is queued; no new agent_decision yet):"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/runs/$runId" | ConvertTo-Json -Depth 10

Write-Host "Resuming..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/resume"
Start-Sleep -Seconds 2
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/runs/$runId" | ConvertTo-Json -Depth 10

Write-Host "Terminating..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runs/$runId/terminate" | ConvertTo-Json -Depth 10
