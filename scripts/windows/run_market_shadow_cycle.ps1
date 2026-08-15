<#
.SYNOPSIS
    Ciclo diario de coleta/liquidacao shadow do Beyond Market (SHADOW_ONLY_NO_CAPITAL).

.DESCRIPTION
    Encadeia, nesta ordem: ingest HLTV recente (janela curta, so pra manter
    data/cs.db em dia sem rescraping pesado) -> coleta Polymarket -> importa
    cotacoes pro banco shadow -> liquida em papel os eventos que ja passaram ->
    imprime o status agregado. Cada passo e' independente e tolerante a falha
    (um passo falhar nao derruba os seguintes).

    Isto NUNCA toca capital real. Cada script chamado aqui passa pelo portao
    de reabertura shadow-only (`assert_market_shadow_collection_open`), gate
    separado e incondicional do portao de capital (`assert_beyond_market_open`,
    que este ciclo nunca chama). Ver docs/records/beyond_market_shadow_reopening.json
    e docs/CURRENT_OPERATIONAL_STATE.md.

.NOTES
    Local ao operador, nao parte do pacote instalavel (nao esta em
    pyproject.toml). Versionado aqui só para nao depender só do disco de uma
    maquina especifica.

.EXAMPLE
    Registro como tarefa agendada diaria as 9h:

    $script = Join-Path (Get-Location) "scripts\windows\run_market_shadow_cycle.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
    Register-ScheduledTask -TaskName "cs-predictor-market-shadow" -Action $action `
        -Trigger $trigger -RunLevel Limited `
        -Description "Coleta/importa/liquida shadow Beyond Market (SHADOW_ONLY_NO_CAPITAL) do cs-predictor"
#>
param([string]$RepoPath = $null)

if (-not $RepoPath) {
    # scripts/windows/<este arquivo> -> scripts/windows -> scripts -> raiz do repo
    $RepoPath = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
Set-Location $RepoPath

New-Item -ItemType Directory -Force -Path (Join-Path $RepoPath "logs") | Out-Null
Start-Transcript -Path (Join-Path $RepoPath "logs\market_shadow_cycle.log") -Append

function Step($name, [scriptblock]$block) {
    Write-Host "=== $name ==="
    try { & $block } catch { Write-Host "FALHOU: $name -> $_" }
}

$recentSince = (Get-Date).AddDays(-5).ToString("yyyy-MM-dd")

Step "1/4 ingest HLTV (janela recente)" { uv run --frozen python -m src.ingest_hltv --until $recentSince }
Step "2/4 coleta Polymarket"            { uv run --frozen python scripts/collect_polymarket_upcoming.py }
Step "3/4 importa cotacoes"             { uv run --frozen python scripts/import_market_quotes.py }
Step "4/4 liquida maturados"            { uv run --frozen python scripts/settle_prospective_market.py }

Write-Host "=== status ==="
uv run --frozen python scripts/market_shadow_status.py

Stop-Transcript
