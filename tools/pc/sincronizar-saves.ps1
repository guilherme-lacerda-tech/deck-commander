# Deck Commander — sincroniza os SAVES de um jogo entre o Steam Deck e o PC (os dois lados ficam com o mais novo).
#
#   powershell -ExecutionPolicy Bypass -File tools\pc\sincronizar-saves.ps1 -Jogo switch2-donkey-kong-bananza
#
# Quem decide é o Deck (python3 -m dc.saves_sync plano): copia só o lado que mudou; se os DOIS mudaram, é conflito e
# nada é sobrescrito (você escolhe no bot: /saves <jogo> deck|pc). Antes de trocar um save, o antigo vira
# "<arquivo>.antes-sync-<data>" (no PC e no Deck). Nada é apagado.
param(
    [Parameter(Mandatory = $true)][string]$Jogo,
    [string]$Jogos = 'D:\DeckCommander\Jogos',
    [string]$Emuladores = 'D:\Emuladores',
    [string]$Deck = '',
    [string]$Chave = (Join-Path $env:USERPROFILE '.ssh\deck_commander_ed25519')
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding $false
if (-not $Deck) {
    $arqDeck = Join-Path $env:USERPROFILE '.deck-commander\deck.txt'
    $Deck = if (Test-Path $arqDeck) { (Get-Content $arqDeck -TotalCount 1).Trim() } else { 'deck@steamdeck' }
}
Import-Module (Join-Path $PSScriptRoot 'transferencia-funcoes.psm1') -Force
$ssh = @('-i', $Chave, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', $Deck)
$data = Get-Date -Format 'yyyyMMdd-HHmmss'

function Saves-PC($m) {
    $out = @{}
    foreach ($a in @($m.arquivos | Where-Object { $_.categoria -eq 'save' -and $_.origem -and (Test-Path -LiteralPath $_.origem) })) {
        $fi = Get-Item -LiteralPath $a.origem
        $out[$a.destino] = @{ sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $a.origem).Hash.ToLower()
                              mtime = [int][double]::Parse((Get-Date $fi.LastWriteTimeUtc -UFormat %s)); origem = $a.origem }
    }
    return $out
}
function Para-Deck($tab) {   # só sha256/mtime vão para o Deck
    $h = @{}; foreach ($k in $tab.Keys) { $h[$k] = @{ sha256 = $tab[$k].sha256; mtime = $tab[$k].mtime } }
    return ($h | ConvertTo-Json -Compress -Depth 4)
}

$tab = Get-TabelaEmuladores
$j = Get-JogosPC -Jogos $Jogos -Emuladores $Emuladores -Tab $tab | Where-Object { $_.Id -eq $Jogo } | Select-Object -First 1
if (-not $j) { Write-Host "O jogo $Jogo não está no PC (copie com /transferir primeiro)."; exit 1 }
$m = Get-ManifestoPC -J $j -Tab $tab -Emuladores $Emuladores -Jogos $Jogos
$pc = Saves-PC $m
# pasta real do {EMU} no PC (para save novo que só existe no Deck)
$basePC = $null
foreach ($a in @($m.arquivos | Where-Object { $_.destino -like '{EMU}/*' -and $_.origem })) {
    $suf = $a.destino.Substring(5).Replace('/', '\')
    if ($a.origem.EndsWith($suf)) { $basePC = $a.origem.Substring(0, $a.origem.Length - $suf.Length); break }
}

$plano = (Para-Deck $pc) | & ssh.exe @ssh "cd ~/deck-commander && python3 -m dc.saves_sync plano '$Jogo'" | ConvertFrom-Json
Write-Host $plano.resumo
$tmp = Join-Path $env:TEMP "dc-saves-$data"; New-Item -ItemType Directory -Force $tmp | Out-Null
foreach ($a in @($plano.acoes)) {
    if ($a.acao -eq 'deck->pc') {
        $alvo = if ($pc.ContainsKey($a.destino)) { $pc[$a.destino].origem } elseif ($basePC) { $basePC + $a.destino.Substring(5).Replace('/', '\') } else { $null }
        if (-not $alvo) { Write-Host "  (sem pasta do emulador no PC para $($a.destino))"; continue }
        $baixado = Join-Path $tmp ([IO.Path]::GetFileName($alvo))
        & scp.exe -q -i $Chave -o BatchMode=yes "${Deck}:`"$($a.caminho_deck)`"" $baixado
        if ($LASTEXITCODE -ne 0) { Write-Host "  falhou ao baixar $($a.destino)"; continue }
        New-Item -ItemType Directory -Force (Split-Path $alvo) | Out-Null
        if (Test-Path -LiteralPath $alvo) { Copy-Item -LiteralPath $alvo -Destination "$alvo.antes-sync-$data" -Force }
        Move-Item -LiteralPath $baixado -Destination $alvo -Force
        Write-Host "  Deck -> PC: $($a.destino) ($($a.motivo))"
    } elseif ($a.acao -eq 'pc->deck') {
        $dest = if ($a.caminho_deck) { $a.caminho_deck } elseif ($plano.base_deck) { $plano.base_deck + $a.destino.Substring(5) } else { $null }
        if (-not $dest) { Write-Host "  (sem pasta do emulador no Deck para $($a.destino))"; continue }
        & ssh.exe @ssh "mkdir -p `"`$(dirname '$dest')`" && if [ -f '$dest' ]; then cp -p '$dest' '$dest.antes-sync-$data'; fi" | Out-Null
        & scp.exe -q -i $Chave -o BatchMode=yes $pc[$a.destino].origem "${Deck}:`"$dest`""
        if ($LASTEXITCODE -ne 0) { Write-Host "  falhou ao enviar $($a.destino)"; continue }
        Write-Host "  PC -> Deck: $($a.destino) ($($a.motivo))"
    } else {
        Write-Host "  CONFLITO: $($a.destino) — escolha no bot: /saves $Jogo deck  ou  /saves $Jogo pc"
    }
}
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
$final = Saves-PC $m
$r = (Para-Deck $final) | & ssh.exe @ssh "cd ~/deck-commander && python3 -m dc.saves_sync confirmar '$Jogo'" | ConvertFrom-Json
Write-Host "Pronto: $($r.sincronizados) save(s) iguais nos dois lados."
