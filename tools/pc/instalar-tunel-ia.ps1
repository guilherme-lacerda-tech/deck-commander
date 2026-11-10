# Instala (ou atualiza) a tarefa "DeckCommander-IA": abre o tunel da IA do PC para o Deck ao entrar no Windows.
# Uso:     powershell -ExecutionPolicy Bypass -File instalar-tunel-ia.ps1 -Deck deck@IP-DO-DECK
# Remover: Unregister-ScheduledTask -TaskName DeckCommander-IA -Confirm:$false
# Religa sozinho: alem do login, a tarefa e chamada a cada 15 min; se o tunel ja estiver aberto, nada acontece
# (IgnoreNew). Antes (09/11) so havia o gatilho de login: se o processo morresse, ficava parado ate o proximo login.
param([string]$Deck = "")
$cfg = Join-Path $env:USERPROFILE ".deck-commander-pc.txt"
if ($Deck) { Set-Content -Path $cfg -Value $Deck -Encoding ascii }
elseif (Test-Path $cfg) { $Deck = (Get-Content $cfg -TotalCount 1).Trim() }
else { Write-Output "Informe o Deck: -Deck deck@IP-DO-DECK (veja o IP no Deck: Configuracoes > Internet)"; exit 2 }
$script = Join-Path $PSScriptRoot "tunel-ia.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "DeckCommander-IA" -Action $action -Trigger @($logon, $every) -Settings $settings `
    -Description "Deck Commander: IA do PC para traduzir jogos no Steam Deck (tunel SSH reverso)" -Force | Out-Null
Start-ScheduledTask -TaskName "DeckCommander-IA"
Write-Output "Tarefa DeckCommander-IA instalada (login + a cada 15 min) para $Deck. Log: $env:LOCALAPPDATA\DeckCommander\tunel-ia.log"
