# Deck Commander — busca no Steam Deck os jogos pedidos com /transferir <jogo> (botão "Enviar pro PC") e copia.
#
# Roda pela tarefa agendada "DeckCommander Transferencias" (a cada 5 min e no logon). Instalar a tarefa (sem admin):
#     powershell -ExecutionPolicy Bypass -File tools\pc\transferir-fila.ps1 -Instalar
#
# Para cada pedido: marca "copiando" no Deck, avisa a automação da casa que há trabalho em andamento (o PC não dorme
# enquanto copia; 3 min depois de terminar, se ele foi acordado pela rede e ninguém o usa, volta a dormir), copia com
# transferir-do-deck.ps1 (sha256 por arquivo, retomada, backup antes de sobrescrever) e marca "pronto" ou "falhou".
param(
    [switch]$Instalar,
    [switch]$Desinstalar,
    [string]$Deck = 'deck@192.168.100.24',
    [string]$Chave = (Join-Path $env:USERPROFILE '.ssh\deck_commander_ed25519')
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding $false   # texto para o ssh em UTF-8 (senão "Ragnarök" vira "Ragnar?k")
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$tarefa = 'DeckCommander Transferencias'
$logDir = 'D:\DeckCommander\logs'
$trabalhos = 'C:\AutomacaoCasa\agente\trabalhos'   # pasta vigiada pelo agente da casa (não dorme com *.ativo recente)

if ($Instalar) {
    $acao = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"" + $MyInvocation.MyCommand.Path + "`"")
    $gat = @((New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
             (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)))
    $cfg = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
    Register-ScheduledTask -TaskName $tarefa -Action $acao -Trigger $gat -Settings $cfg -Force | Out-Null
    Write-Host "Tarefa '$tarefa' instalada (a cada 5 min e no logon)."
    exit 0
}
if ($Desinstalar) { Unregister-ScheduledTask -TaskName $tarefa -Confirm:$false; Write-Host 'Tarefa removida.'; exit 0 }

New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('transferir-fila-' + (Get-Date -Format 'yyyyMMdd') + '.log')
function L([string]$t) { Add-Content -Path $log -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $t) -Encoding UTF8 }
$sshArgs = @('-i', $Chave, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', $Deck)

# Lista de jogos do PC (apps do Sunshine) -> Deck, quando muda: é dela que sai a aba "Computador"
# (o "moonlight list" sem tela trava ao baixar capas novas; esta lista não depende disso)
try {
    $appsJson = 'C:\Program Files\Sunshine\config\apps.json'
    if (Test-Path $appsJson) {
        $nomes = @((Get-Content $appsJson -Raw -Encoding UTF8 | ConvertFrom-Json).apps | ForEach-Object { $_.name } | Where-Object { $_ })
        $corpo = (@{ apps = $nomes; em = (Get-Date -Format o) } | ConvertTo-Json -Compress)
        $marca = Join-Path $logDir 'pc-apps.enviado'
        $assin = ($nomes -join "`n")
        if (-not (Test-Path $marca) -or (Get-Content $marca -Raw -Encoding UTF8) -ne $assin) {
            $tmp = [IO.Path]::GetTempFileName()
            [IO.File]::WriteAllText($tmp, $corpo, (New-Object Text.UTF8Encoding $false))
            Get-Content $tmp -Raw -Encoding UTF8 | & ssh.exe @sshArgs 'cat > ~/.local/share/deck-commander/pc-apps.json && cd ~/deck-commander && python3 -m dc x pc sincronizar' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { [IO.File]::WriteAllText($marca, $assin, (New-Object Text.UTF8Encoding $false)); L ("lista de jogos do PC enviada ao Deck (" + $nomes.Count + ")") }
            Remove-Item $tmp -ErrorAction SilentlyContinue
        }
    }
} catch { L ("lista de jogos: " + $_.Exception.Message) }

# fila no Deck (só pedidos "na fila"/"copiando"); Deck desligado/fora de alcance = tenta na próxima rodada
try {
    $json = & ssh.exe @sshArgs 'cd ~/deck-commander && python3 -m dc.transferir fila-json' 2>$null
} catch { exit 0 }
if ($LASTEXITCODE -ne 0 -or -not $json) { exit 0 }
$fila = @($json | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.id })  # "[]" vira lista vazia de verdade
if ($fila.Count -eq 0) { exit 0 }

New-Item -ItemType Directory -Force $trabalhos -ErrorAction SilentlyContinue | Out-Null
$ativo = Join-Path $trabalhos 'deck-commander-transferencia.ativo'
# mantém o arquivo "ativo" atualizado a cada minuto enquanto copia (o agente da casa olha a data dele)
$pulso = Start-Job -ScriptBlock { param($f) while ($true) { Set-Content -Path $f -Value (Get-Date -Format o); Start-Sleep 60 } } -ArgumentList $ativo

function Marcar([string]$id, [string]$status, [string]$nota) {
    $nota | & ssh.exe @sshArgs "cd ~/deck-commander && python3 -m dc.transferir marcar '$id' '$status' -" 2>$null | Out-Null
}

try {
    foreach ($p in $fila) {
        L ("pedido " + $p.id + " (" + $p.titulo + ")")
        Marcar $p.id 'copiando' 'o PC está copiando'
        $saida = Join-Path $logDir ('transferir-' + $p.game_id + '.log')
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $aqui 'transferir-do-deck.ps1') -Jogo $p.game_id -SemEmuladorLinux -Deck $Deck -Chave $Chave *> $saida
        $rc = $LASTEXITCODE
        $fim = (Get-Content $saida -Tail 12 -ErrorAction SilentlyContinue) -join "`n"
        if ($rc -eq 0) { Marcar $p.id 'pronto' $fim; L ("pronto: " + $p.game_id) }
        else { Marcar $p.id 'falhou' ("código $rc`n" + $fim); L ("falhou ($rc): " + $p.game_id) }
    }
} finally {
    # o arquivo fica (com a hora do último pulso): é por ele que o agente sabe que o trabalho acabou e, 3 min
    # depois, devolve o PC ao sono se foi acordado pela rede
    Stop-Job $pulso -ErrorAction SilentlyContinue; Remove-Job $pulso -Force -ErrorAction SilentlyContinue
}
