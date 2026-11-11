# Deck Commander - transferência segura de um jogo do PC para o Steam Deck (o sentido contrário de transferir-do-deck.ps1).
#
# Leva o jogo + os dados do emulador do PC (saves, config do jogo, mods, keys/firmware/BIOS do próprio usuário):
#   1. monta o MANIFESTO DO PC (cada arquivo com sha256) e vê se o Deck tem o emulador;
#   2. copia por sftp para a área de recebimento do Deck (put/reput: rode de novo e ele continua de onde parou);
#   3. confere tudo NO DECK com sha256sum -c (o que vier errado é mandado de novo, até -Tentativas rodadas);
#   4. no Deck, `python3 -m dc.transferir receber <id>` instala: jogo em ~/Emulation/roms/<console>/<jogo>, dados nos
#      caminhos Linux do emulador (caminhos D:/... trocados pelos do Deck), backup antes de sobrescrever, emulador
#      OFICIAL instalado se faltar (Flatpak do Flathub ou AppImage da página oficial) e o jogo entra na biblioteca do Steam.
# Nada é apagado no PC.
#
# Uso:  enviar-para-deck.ps1 -Listar                       jogos do PC que podem ir (-Json para máquina)
#       enviar-para-deck.ps1 -Jogo psx-hercules           envia e instala
#       enviar-para-deck.ps1 -Jogo <id> -Simular          só mostra o que iria (e o emulador que seria instalado)
#       enviar-para-deck.ps1 -Jogo <id> -DestinoTeste ~/dc-teste-receber   copia e "instala" dentro da pasta de teste
#       enviar-para-deck.ps1 -Detectar                    emuladores dos dois lados + o que seria baixado (não baixa nada)
#       enviar-para-deck.ps1 -Publicar                    manda a lista de jogos do PC para o Deck (/trazer, painel)
[CmdletBinding()]
param(
    [string]$Jogo,
    [switch]$Listar,
    [switch]$Json,
    [switch]$Publicar,
    [switch]$Detectar,
    [switch]$Simular,
    [string]$DestinoTeste,
    [switch]$SemEmulador,
    [switch]$ConfigGlobal,
    [switch]$Forcar,
    [string]$Jogos = 'D:\DeckCommander\Jogos',
    [string]$Emuladores = 'D:\Emuladores',
    [string]$Destino = 'D:\DeckCommander\Enviados',
    [string]$Deck = '',   # vazio = lê %USERPROFILE%\.deck-commander\deck.txt (ex.: deck@192.168.0.50); senão deck@steamdeck
    [string]$Chave = (Join-Path $env:USERPROFILE '.ssh\deck_commander_ed25519'),
    [int]$Tentativas = 3
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'transferencia-funcoes.psm1') -Force -DisableNameChecking
if (-not $Deck) {
    $arqDeck = Join-Path $env:USERPROFILE '.deck-commander\deck.txt'
    $Deck = if (Test-Path $arqDeck) { (Get-Content $arqDeck -TotalCount 1).Trim() } else { 'deck@steamdeck' }
}
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$Tab = Get-TabelaEmuladores
$ArqTabela = Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'config\emuladores-oficiais.json'
$ModuloLocal = Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'dc\receber.py'
function Msg([string]$t, [string]$cor = 'Gray') { if (-not $Json) { Write-Host $t -ForegroundColor $cor } }
function Deck([string]$remoto, [string]$texto, [string]$arquivo) { Invoke-DeckSsh -Deck $Deck -Chave $Chave -Remoto $remoto -EntradaTexto $texto -EntradaArquivo $arquivo }

# raiz das áreas no Deck (relativa à home) e a tabela de origens oficiais que vai junto
$RaizAreas = if ($DestinoTeste) { (Split-Path (Get-AreaRemota 'x' $DestinoTeste) -Parent).Replace('\', '/') } else { '.local/share/deck-commander/receber' }
$OptTeste = if ($DestinoTeste) { ' --destino-teste ~/' + ($DestinoTeste -replace '^~/', '').TrimEnd('/') } else { '' }   # já validado por Get-AreaRemota

function Enviar-Tabela {
    $r = Deck "mkdir -p '$RaizAreas' && cat > '$RaizAreas/emuladores-oficiais.json'" $null $ArqTabela
    if ($r.Codigo -ne 0) { throw "não consegui falar com o Deck ($Deck): $($r.Erro)" }
}

function Modulo-Deck([string]$sub) {
    # dc.transferir instalado no Deck, ou dc/receber.py deste repositório mandado pela entrada padrão (nada é instalado)
    $env1 = "DC_EMU_TABELA=`"`$HOME/$RaizAreas/emuladores-oficiais.json`""
    $r = Deck 'test -f ~/deck-commander/dc/receber.py && echo SIM' $null $null
    if ($r.Saida -match 'SIM') { return Deck "cd ~/deck-commander && $env1 python3 -m dc.transferir $sub" $null $null }
    return Deck "cd ~/deck-commander 2>/dev/null; $env1 python3 - $sub" $null (Resolve-Path $ModuloLocal).Path
}

# ================================================================= listar / publicar ========
if ($Listar -or $Publicar) {
    $js = @(Get-JogosPC -Jogos $Jogos -Emuladores $Emuladores -Tab $Tab)
    # a lista só é refeita quando os jogos/emuladores mudam (ler 166 mil arquivos do Switch 2 leva ~1 min)
    New-Item -ItemType Directory -Force $Destino | Out-Null
    $arqLista = Join-Path $Destino '_lista-pc.json'; $arqAssin = Join-Path $Destino '_lista-pc.assinatura'
    $assin = Get-AssinaturaJogos $js $Emuladores $Tab
    if (-not $Forcar -and (Test-Path $arqLista) -and (Test-Path $arqAssin) -and [IO.File]::ReadAllText($arqAssin, $Utf8) -eq $assin) {
        $texto = [IO.File]::ReadAllText($arqLista, $Utf8)
    } else {
        $texto = ConvertTo-Json (ConvertTo-ListaPublicada $js $Tab $Emuladores $Jogos) -Depth 6 -Compress
        [IO.File]::WriteAllText($arqLista, $texto, $Utf8); [IO.File]::WriteAllText($arqAssin, $assin, $Utf8)
    }
    $lista = $texto | ConvertFrom-Json
    if ($Listar) {
        if ($Json) { $texto } else {
            foreach ($j in @($lista.jogos)) { Msg ("{0,-40} {1,-8} {2,10:N1} MB  ({3})" -f $j.id, $j.console, ($j.tamanho / 1e6), $j.titulo) }
            Msg ("emuladores no PC: " + (($lista.emuladores_pc.PSObject.Properties | ForEach-Object { $_.Name }) -join ', '))
        }
    }
    if ($Publicar) {
        $marca = Join-Path $Destino '_lista-pc.enviada'
        if (-not $Forcar -and (Test-Path $marca) -and [IO.File]::ReadAllText($marca, $Utf8) -eq $texto) { Msg 'lista do PC já está no Deck (sem mudança)'; exit 0 }
        $r = Deck 'mkdir -p ~/.local/share/deck-commander && cat > ~/.local/share/deck-commander/pc-jogos-transferiveis.json' $texto $null
        if ($r.Codigo -ne 0) { throw "não consegui mandar a lista ao Deck: $($r.Erro)" }
        [IO.File]::WriteAllText($marca, $texto, $Utf8)
        Msg "lista de $(@($lista.jogos).Count) jogo(s) do PC enviada ao Deck" 'Green'
    }
    exit 0
}

# ================================================================= detectar (os dois lados) =
if ($Detectar) {
    Msg 'EMULADORES NO PC' 'Cyan'
    $pc = Get-EmuladoresPC $Emuladores $Tab
    foreach ($k in ($Tab.Keys | Sort-Object)) {
        if ($pc.Contains($k)) { Msg ("  {0,-12} SIM  {1}{2}" -f $k, $pc[$k].Exe, $(if ($pc[$k].Versao) { "  ($($pc[$k].Versao))" } else { '' })) 'Green' }
        else {
            $pl = Get-PlanoEmuladorPC -Emu $k -Tab $Tab -Emuladores $Emuladores
            Msg ("  {0,-12} não  -> [simulação] {1}" -f $k, (Format-PlanoEmulador $pl)) 'Yellow'
        }
    }
    Msg "EMULADORES NO DECK ($Deck)" 'Cyan'
    Enviar-Tabela
    $r = Modulo-Deck 'emuladores --json'
    if ($r.Codigo -ne 0) { throw "detecção no Deck falhou: $($r.Erro)" }
    foreach ($d in ($r.Saida | ConvertFrom-Json | ForEach-Object { $_ })) {
        if ($d.instalado) { Msg ("  {0,-12} SIM  {1,-9} {2}{3}" -f $d.emulador, $d.tipo, $d.onde, $(if ($d.versao) { "  ($($d.versao))" } else { '' })) 'Green' }
        else {
            $v = if ($pc.Contains($d.emulador) -and $pc[$d.emulador].Versao) { " --versao $($pc[$d.emulador].Versao)" } else { '' }
            $p = Modulo-Deck "emulador-plano $($d.emulador)$v"
            Msg ("  {0,-12} não  -> [simulação] {1}" -f $d.emulador, $p.Saida.Trim()) 'Yellow'
        }
    }
    exit 0
}

# ================================================================= enviar um jogo ==========
if (-not (Test-Path $Chave)) { throw "Chave ssh não encontrada: $Chave" }
$js = @(Get-JogosPC -Jogos $Jogos -Emuladores $Emuladores -Tab $Tab)
if (-not $Jogo) {
    for ($i = 0; $i -lt $js.Count; $i++) { Msg ("{0,3}. {1}  [{2}]" -f ($i + 1), $js[$i].Titulo, $js[$i].Console) }
    $n = Read-Host 'Número do jogo'
    $Jogo = $js[[int]$n - 1].Id
}
if ($Jogo -notmatch '^[a-z0-9][a-z0-9._-]*$') { throw "Id de jogo inválido: $Jogo" }
$J = $js | Where-Object { $_.Id -eq $Jogo } | Select-Object -First 1
if (-not $J) { throw "Jogo não encontrado no PC: $Jogo (veja -Listar)" }

$Local = Join-Path $Destino $Jogo
New-Item -ItemType Directory -Force $Local | Out-Null
Msg "Montando o manifesto do PC de $($J.Titulo) (sha256 de cada arquivo; jogos grandes demoram na 1ª vez)..." 'Cyan'
$Man = Get-ManifestoPC $J $Tab $Emuladores $Jogos -ComHash -CacheHash (Join-Path $Local '.hash-cache.tsv')
$ArqMan = Join-Path $Local 'manifesto.json'
[IO.File]::WriteAllText($ArqMan, (ConvertTo-Json $Man -Depth 8), $Utf8)
$ArqSums = Join-Path $Local 'SHA256SUMS'
[IO.File]::WriteAllText($ArqSums, (Format-Sha256Sums $Man.arquivos), $Utf8)
Msg ("{0} ({1}, emulador {2}): {3} arquivos, {4:N1} MB" -f $Man.titulo, $Man.console, $Man.emulador, @($Man.arquivos).Count, ($Man.total_bytes / 1e6)) 'Cyan'
foreach ($kv in $Man['resumo'].GetEnumerator()) { Msg ("  {0}: {1} arquivos, {2:N1} MB" -f $kv.Key, $kv.Value['arquivos'], ($kv.Value['bytes'] / 1e6)) }
foreach ($a in $Man.avisos) { Msg "  aviso: $a" 'Yellow' }

# emulador do outro lado
Enviar-Tabela
if ($Man.emulador) {
    $r = Modulo-Deck 'emuladores --json'
    $d = if ($r.Codigo -eq 0) { $r.Saida | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.emulador -eq $Man.emulador } | Select-Object -First 1 } else { $null }
    if ($d -and $d.instalado) { Msg "  emulador no Deck: $($d.onde)" 'Green' }
    elseif ($d) {
        $v = if ($Man.emulador_pc -and $Man.emulador_pc.versao) { " --versao $($Man.emulador_pc.versao)" } else { '' }
        $p = Modulo-Deck "emulador-plano $($Man.emulador)$v"
        Msg ("  " + $p.Saida.Trim() + $(if ($SemEmulador) { ' (pulado: -SemEmulador)' } elseif ($DestinoTeste) { ' (teste: só simulado)' } else { '' })) 'Yellow'
    }
}
if ($Simular) { Msg '[simulação] nada foi copiado.' 'Yellow'; exit 0 }

$Area = Get-AreaRemota $Jogo $DestinoTeste
Msg "Copiando para o Deck: ~/$Area" 'Cyan'
$dirs = @($Man.arquivos | ForEach-Object { $i = $_.rel.LastIndexOf('/'); if ($i -gt 0) { $_.rel.Substring(0, $i) } } | Sort-Object -Unique)
$r = Deck "mkdir -p '$Area/arquivos' && cd '$Area/arquivos' && while IFS= read -r d; do mkdir -p -- `"`$d`"; done" (($dirs -join "`n") + "`n") $null
if ($r.Codigo -ne 0) { throw "não consegui criar a área no Deck: $($r.Erro)" }
foreach ($par in @(@($ArqMan, 'manifesto.json'), @($ArqSums, 'SHA256SUMS'), @($ArqTabela, 'emuladores-oficiais.json'))) {
    $r = Deck "cat > '$Area/$($par[1])'" $null $par[0]
    if ($r.Codigo -ne 0) { throw "não consegui mandar $($par[1]): $($r.Erro)" }
}

$reenviar = @{}
$falhas = @()
for ($t = 0; $t -le $Tentativas; $t++) {
    $r = Deck "cd '$Area/arquivos' && find . -type f -printf '%s\t%P\n'" $null $null
    $remotos = Read-TamanhosRemotos $r.Saida
    foreach ($k in $reenviar.Keys) { $remotos.Remove($k) }   # hash errado na rodada anterior: manda do zero
    $lote = New-LoteSftpPut -Arquivos $Man.arquivos -Remotos $remotos -AreaRemota $Area
    if ($lote.Quantos -gt 0) {
        if ($t -eq $Tentativas) { $falhas = @('ainda faltam arquivos'); break }
        Msg ("  enviando {0} arquivo(s) (rodada {1})..." -f $lote.Quantos, ($t + 1))
        $batch = Join-Path $Local '.sftp-lote.txt'
        $linhas = @($lote.Texto -split "`n" | Where-Object { $_ })
        for ($ini = 0; $ini -lt $linhas.Count; $ini += 200) {   # em partes: dá para mostrar o progresso
            $parte = $linhas[$ini..([Math]::Min($ini + 200, $linhas.Count) - 1)]
            [IO.File]::WriteAllText($batch, (($parte -join "`n") + "`n"), $Utf8)
            $sftpArgs = @('-q', '-b', "`"$batch`"", '-i', "`"$Chave`"", '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=15', $Deck)
            $p = Start-Process sftp.exe -ArgumentList $sftpArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$Local\sftp.out" -RedirectStandardError "$Local\sftp.err"
            if ($p.ExitCode -ne 0) { Msg "  (sftp saiu com código $($p.ExitCode); confiro e mando de novo o que faltar)" 'Yellow' }
            Msg ("  enviando {0}/{1} arquivos..." -f ([Math]::Min($ini + 200, $linhas.Count)), $linhas.Count)
        }
        Remove-Item $batch -ErrorAction SilentlyContinue
    }
    Msg '  conferindo no Deck (sha256sum -c)...'
    $r = Deck "cd '$Area/arquivos' && sha256sum --quiet --strict -c ../SHA256SUMS 2>&1; true" $null $null
    $falhas = @(Read-FalhasSha256Sum $r.Saida)
    if (-not $falhas.Count) { break }
    $reenviar = @{}; foreach ($f in $falhas) { $reenviar[$f] = 1 }
    Msg ("  {0} arquivo(s) não conferem; mando de novo" -f $falhas.Count) 'Yellow'
}
if ($falhas.Count) { Msg "$($falhas.Count) arquivo(s) NÃO conferem no Deck: $($falhas | Select-Object -First 5)" 'Red'; exit 1 }
Msg "Todos os $(@($Man.arquivos).Count) arquivos conferem no Deck (sha256sum)." 'Green'

$opts = $OptTeste
if ($SemEmulador) { $opts += ' --sem-emulador' }
if ($ConfigGlobal) { $opts += ' --config-global' }
Msg 'Instalando no Deck...' 'Cyan'
$r = Modulo-Deck "receber $Jogo$opts"
[IO.File]::WriteAllText((Join-Path $Local 'receber.log'), $r.Saida + $r.Erro, $Utf8)
if ($Json) { $r.Saida } else { Write-Host $r.Saida; if ($r.Erro) { Write-Host $r.Erro -ForegroundColor Yellow } }
if ($r.Codigo -ne 0) { exit 1 }
Msg 'Pronto. Nada foi apagado no PC.' 'Green'
exit 0
