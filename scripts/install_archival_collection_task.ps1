$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$entry = Join-Path $root "scripts\run_archival_collection.py"
$taskName = "cs-archival-collection"
# Input e fornecido por export esportivo oficial; este job nunca consulta mercado/apostas.
$input = Join-Path $root "data\collection_only\upstream_events.json"
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $entry + '" --input "' + $input + '" --status') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "CS2 COLLECTION_ONLY archival collector; no market or betting access" -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
