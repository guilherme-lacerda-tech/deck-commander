# Instala (ou atualiza) a tarefa "DeckCommander-IA": abre o túnel da IA do PC para o Deck ao entrar no Windows.
# Remover:  Unregister-ScheduledTask -TaskName DeckCommander-IA -Confirm:$false
param([string]$Deck = "deck@192.168.100.24")
$script = Join-Path $PSScriptRoot "tunel-ia.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Deck $Deck"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "DeckCommander-IA" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Deck Commander: IA do PC para traduzir jogos no Steam Deck (túnel SSH reverso)" -Force | Out-Null
Start-ScheduledTask -TaskName "DeckCommander-IA"
Write-Output "Tarefa DeckCommander-IA instalada e iniciada."
