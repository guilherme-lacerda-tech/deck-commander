# Deck Commander - transferência segura de um jogo do Steam Deck para este PC (Windows).
#
# Copia TUDO do jogo: arquivos (base/update/DLC), emulador (binário Linux, só referência) e toda a
# configuração (global e do jogo, controles, mods, cheats, saves, keys/firmware/BIOS do usuário).
# Cache de shader NÃO vem: depende da GPU/driver/sistema; o emulador do PC recompila.
#
# Segura:  * cada arquivo conferido por sha256 (Get-FileHash) contra o manifesto feito no Deck
#          * retomável: rode de novo e ele só baixa o que falta (arquivo pela metade continua com reget)
#          * backup de qualquer arquivo do emulador do PC antes de sobrescrever
#          * nada é apagado no Deck (só leitura por ssh/sftp)
#
# Uso:  transferir-do-deck.bat                       (pergunta o jogo)
#       transferir-do-deck.bat -Jogo switch2-donkey-kong-bananza
#       transferir-do-deck.bat -Jogo <id> -Destino E:\DoDeck -Jogos E:\Jogos -Emuladores E:\Emuladores
#       transferir-do-deck.bat -Jogo <id> -SoInstalar  (já copiou; só instala no emulador do PC)
#
# Onde fica cada coisa:
#   -Jogos       arquivos do jogo:  <Jogos>\<console>\<jogo>\...           (padrão D:\DeckCommander\Jogos)
#   -Destino     manifesto, cópia dos dados do emulador, LEIA-ME:  <Destino>\<id>\  (padrão D:\DeckCommander\Transferidos)
#   -Emuladores  emuladores portáteis procurados primeiro aqui (padrão D:\Emuladores):
#                Lichii\lichii.exe (dados em Lichii\user), Ryujinx\publish\Ryujinx.exe (dados em ...\portable),
#                PCSX2 (portable.ini), DuckStation (portable.txt), PPSSPP, Xenia (portable.txt)
#   -EmuDir      força a pasta de DADOS do emulador (pula a detecção)
[CmdletBinding()]
param(
    [string]$Jogo,
    [string]$Destino = 'D:\DeckCommander\Transferidos',
    [string]$Jogos = 'D:\DeckCommander\Jogos',
    [string]$Emuladores = 'D:\Emuladores',
    [switch]$SoInstalar,
    [switch]$SemInstalar,
    [string]$Deck = 'deck@192.168.100.24',
    [string]$Chave = (Join-Path $env:USERPROFILE '.ssh\deck_commander_ed25519'),
    [string]$EmuDir,
    [switch]$SemEmuladorLinux,
    [switch]$SoConfig,
    [switch]$SemCacheNoDeck,
    [int]$Tentativas = 3,
    [int]$Lote = 1500
)
$ErrorActionPreference = 'Stop'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Msg([string]$t, [string]$cor = 'Gray') { Write-Host $t -ForegroundColor $cor }
function Caminho-Longo([string]$p) {   # caminho longo (>260)
    if ($p.StartsWith('\\?\')) { return $p }
    return ('\\?\' + $p)
}

function Sha256([string]$p) { (Get-FileHash -Algorithm SHA256 -LiteralPath (Caminho-Longo $p)).Hash.ToLower() }

# ---------------------------------------------------------------- ssh ---------------------
$SshBase = @('-i', $Chave, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15')

function Invoke-Deck([string]$remoto, [string]$entrada) {
    # stdout em UTF-8 exato (o PowerShell 5.1 estragaria acentos se lesse direto)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'ssh.exe'
    $args2 = $SshBase + @($Deck, $remoto)
    $psi.Arguments = ($args2 | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.StandardOutputEncoding = $Utf8
    $psi.StandardErrorEncoding = $Utf8
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEndAsync()
    $err = $p.StandardError.ReadToEndAsync()
    if ($entrada) {
        $b = [IO.File]::ReadAllBytes($entrada)
        $p.StandardInput.BaseStream.Write($b, 0, $b.Length)
    }
    $p.StandardInput.Close()
    $p.WaitForExit()
    return @{ Codigo = $p.ExitCode; Saida = $out.Result; Erro = $err.Result }
}

# O módulo instalado no Deck (~/deck-commander) ou, se ainda não foi instalado lá, o deste repositório
# mandado pela entrada padrão (não grava nada no Deck).
$ModuloLocal = Join-Path $PSScriptRoot '..\..\dc\transferir.py'
function Invoke-Transferir([string]$sub) {
    $r = Invoke-Deck 'test -f ~/deck-commander/dc/transferir.py && echo SIM' $null
    if ($r.Saida -match 'SIM') {
        return Invoke-Deck "cd ~/deck-commander && python3 -m dc.transferir $sub" $null
    }
    if (-not (Test-Path $ModuloLocal)) { throw 'dc/transferir.py não está no Deck nem ao lado deste script.' }
    return Invoke-Deck "python3 - $sub" (Resolve-Path $ModuloLocal).Path
}

# ---------------------------------------------------------------- manifesto ---------------
function Ler-Manifesto([string]$texto) {
    $linhas = $texto -split "`n"
    if (-not $linhas[0].StartsWith("DCMANIFESTO`t")) { throw "resposta do Deck não é um manifesto: $($linhas[0])" }
    $meta = ($linhas[0].Split("`t", 3))[2] | ConvertFrom-Json
    $arqs = New-Object System.Collections.Generic.List[object]
    foreach ($l in $linhas) {
        if (-not $l.StartsWith("F`t")) { continue }
        $c = $l.TrimEnd("`r").Split("`t")
        $arqs.Add([pscustomobject]@{ Sha = $c[1]; Tam = [int64]$c[2]; Cat = $c[3]; Reescrever = ($c[4] -eq '1');
                                     Destino = $c[5]; Origem = $c[6]; Local = $null })
    }
    return @{ Meta = $meta; Arquivos = $arqs }
}

function Caminho-Local([string]$destino, [string]$raiz) {
    # {JOGOS}/<console>/<jogo>/... -> <Jogos>\<console>\<jogo>\... ; {EMU} e {LINUX} ficam na pasta da transferência
    # (sem pipeline: roda 166 mil vezes no Switch 2). Caracteres proibidos no Windows viram '_'.
    $i = $destino.IndexOf('/')
    $tok = $destino.Substring(0, $i)
    $resto = ($destino.Substring($i + 1) -replace '[<>:"|?*\\]', '_') -replace '[ .]+(?=/|$)', '_'
    $resto = $resto.Replace('/', '\')
    switch ($tok) {
        '{JOGOS}' { return $Jogos.TrimEnd('\') + '\' + $resto }
        '{EMU}'   { return $raiz.TrimEnd('\') + '\emulador\' + $resto }
        '{LINUX}' { return $raiz.TrimEnd('\') + '\emulador-linux\' + $resto }
        default   { throw "destino desconhecido no manifesto: $destino" }
    }
}

# ---------------------------------------------------------------- conferência -------------
$Conferidos = @{}
function Carregar-Conferidos([string]$arq) {
    if (Test-Path $arq) {
        foreach ($l in [IO.File]::ReadAllLines($arq, $Utf8)) {
            $c = $l.Split("`t"); if ($c.Count -eq 4) { $Conferidos[$c[0]] = $c }
        }
    }
}
function Conferir($a, [string]$arqCache) {
    # $true se o arquivo local bate com o sha256 do manifesto (com cache por tamanho+data, para não refazer 19 GB)
    $fi = [IO.FileInfo]::new((Caminho-Longo $a.Local))
    if (-not $fi.Exists -or $fi.Length -ne $a.Tam) { return $false }
    $k = $a.Local; $t = [string]$fi.LastWriteTimeUtc.Ticks
    $c = $Conferidos[$k]
    if ($c -and $c[1] -eq [string]$a.Tam -and $c[2] -eq $t -and $c[3] -eq $a.Sha) { return $true }
    if ((Sha256 $a.Local) -ne $a.Sha) { return $false }
    $Conferidos[$k] = @($k, [string]$a.Tam, $t, $a.Sha)
    [IO.File]::AppendAllText($arqCache, (@($k, $a.Tam, $t, $a.Sha) -join "`t") + "`n", $Utf8)
    return $true
}

# ---------------------------------------------------------------- cópia (sftp) ------------
function Baixar($lista, [string]$raiz) {
    $batch = Join-Path $raiz '.sftp-lote.txt'
    $log = Join-Path $raiz 'transferencia.log'
    $total = ($lista | Measure-Object Tam -Sum).Sum; $feito = 0; $i = 0
    for ($ini = 0; $ini -lt $lista.Count; $ini += $Lote) {
        $parte = $lista[$ini..([Math]::Min($ini + $Lote, $lista.Count) - 1)]
        $sb = New-Object System.Text.StringBuilder
        foreach ($a in $parte) {
            $d = [IO.Path]::GetDirectoryName($a.Local)
            [void][IO.Directory]::CreateDirectory((Caminho-Longo $d))
            $fi = [IO.FileInfo]::new((Caminho-Longo $a.Local))
            $cmd = 'get'
            if ($fi.Exists -and $fi.Length -gt 0 -and $fi.Length -lt $a.Tam) { $cmd = 'reget' }   # continua de onde parou
            elseif ($fi.Exists) { $fi.Delete() }   # só a cópia local (pasta de transferência), nunca o Deck
            # entre aspas o sftp trata [ ] * ? como texto; '-' = segue o lote mesmo se um arquivo falhar
            [void]$sb.Append("-$cmd `"$($a.Origem)`" `"$($a.Local.Replace('\', '/'))`"`n")
        }
        [IO.File]::WriteAllText($batch, $sb.ToString(), $Utf8)
        $feito += ($parte | Measure-Object Tam -Sum).Sum; $i += $parte.Count
        Msg ("  copiando {0}/{1} arquivos ({2:N2} de {3:N2} GB)..." -f $i, $lista.Count, ($feito / 1e9), ($total / 1e9))
        $sftpArgs = @('-q', '-b', "`"$batch`"", '-i', "`"$Chave`"", '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=15', $Deck)
        $p = Start-Process sftp.exe -ArgumentList $sftpArgs -NoNewWindow -Wait -PassThru `
             -RedirectStandardOutput "$log.out" -RedirectStandardError "$log.err"
        Get-Content "$log.err" -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content $log -Encoding UTF8
        if ($p.ExitCode -ne 0) { Msg "  (sftp saiu com código $($p.ExitCode); confiro e tento de novo o que faltar)" 'Yellow' }
    }
    Remove-Item $batch, "$log.out", "$log.err" -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------- emulador do PC ----------
function Achar-Exe([string[]]$nomes) {
    $docs = [Environment]::GetFolderPath('MyDocuments'); $desk = [Environment]::GetFolderPath('Desktop')
    $locais = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA 'Programs'),
                (Join-Path $env:USERPROFILE 'Downloads'), $desk, $docs, 'C:\Emuladores', 'D:\Emuladores',
                'C:\Games', 'D:\Games', 'C:\RetroArch-Win64', 'D:\DeckCommander\Emuladores') | Where-Object { $_ -and (Test-Path $_) }
    foreach ($l in $locais) {
        foreach ($n in $nomes) {
            $h = Get-ChildItem -Path $l -Filter $n -Recurse -Depth 3 -File -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($h) { return $h.FullName }
        }
    }
    return $null
}

function Achar-Emulador([string]$emu) {
    # devolve @{ Exe; Dados } ou $null se o emulador não está neste PC
    $docs = [Environment]::GetFolderPath('MyDocuments')
    if ($EmuDir) { return @{ Exe = $null; Dados = $EmuDir } }
    # 1º: emuladores portáteis em -Emuladores (padrão D:\Emuladores)
    $E = $Emuladores
    $portateis = @{
        'lichii'      = @(@{ Exe = "$E\Lichii\lichii.exe"; Dados = "$E\Lichii\user" })
        'ryujinx'     = @(@{ Exe = "$E\Ryujinx\publish\Ryujinx.exe"; Dados = "$E\Ryujinx\publish\portable" },
                          @{ Exe = "$E\Ryujinx\Ryujinx.exe"; Dados = "$E\Ryujinx\portable" })
        'pcsx2'       = @(@{ Exe = "$E\PCSX2\pcsx2-qt.exe"; Dados = "$E\PCSX2" })
        'duckstation' = @(@{ Exe = "$E\DuckStation\duckstation-qt-x64-ReleaseLTCG.exe"; Dados = "$E\DuckStation" })
        'ppsspp'      = @(@{ Exe = "$E\PPSSPP\PPSSPPWindows64.exe"; Dados = "$E\PPSSPP\memstick" })
        'xenia'       = @(@{ Exe = "$E\Xenia\xenia_canary.exe"; Dados = "$E\Xenia" })
        'retroarch'   = @(@{ Exe = "$E\RetroArch\retroarch.exe"; Dados = "$E\RetroArch" })
    }
    if ($E -and $portateis.ContainsKey($emu)) {
        foreach ($c in $portateis[$emu]) { if (Test-Path -LiteralPath $c.Exe) { return $c } }
    }
    switch ($emu) {
        'ryujinx' { $exe = Achar-Exe @('Ryujinx.exe'); $dados = Join-Path $env:APPDATA 'Ryujinx'
                    if ($exe -and (Test-Path (Join-Path (Split-Path $exe) 'portable'))) { $dados = Join-Path (Split-Path $exe) 'portable' } }
        'lichii'  { $exe = Achar-Exe @('lichii*.exe', 'Lichii*.exe', 'eden.exe'); $dados = Join-Path $env:APPDATA 'eden'
                    if ($exe -and (Test-Path (Join-Path (Split-Path $exe) 'user'))) { $dados = Join-Path (Split-Path $exe) 'user' } }
        'duckstation' { $exe = Achar-Exe @('duckstation*.exe'); $dados = Join-Path $docs 'DuckStation'
                    if ($exe -and (Test-Path (Join-Path (Split-Path $exe) 'portable.txt'))) { $dados = Split-Path $exe } }
        'pcsx2'   { $exe = Achar-Exe @('pcsx2*.exe'); $dados = Join-Path $docs 'PCSX2'
                    if ($exe -and ((Test-Path (Join-Path (Split-Path $exe) 'portable.ini')) -or (Test-Path (Join-Path (Split-Path $exe) 'portable.txt')))) { $dados = Split-Path $exe } }
        'retroarch' { $exe = Achar-Exe @('retroarch.exe'); $dados = Join-Path $env:APPDATA 'RetroArch'
                    if ($exe) { $dados = Split-Path $exe } }
        default   { return $null }
    }
    if (-not $exe -and -not (Test-Path $dados)) { return $null }
    return @{ Exe = $exe; Dados = $dados }
}

function Trocar-Caminhos([string]$txt, $regras, [string]$raizJogos, [string]$raizEmu) {
    foreach ($r in $regras) {
        $para = $r.para.Replace('{JOGOS}', $raizJogos.Replace('\', '/')).Replace('{EMU}', $raizEmu.Replace('\', '/'))
        $txt = $txt.Replace($r.de, $para)
    }
    return $txt
}

function Instalar($man, [string]$raiz, $emu) {
    $meta = $man.Meta
    $dados = $emu.Dados
    [void][IO.Directory]::CreateDirectory((Caminho-Longo $dados))
    # backup fica junto do emulador (sobrevive mesmo se a pasta da transferência for apagada)
    $bk = Join-Path $dados "_backup-deck-commander\$Stamp-$($meta.game_id)"
    $res = @{ Instalados = 0; Iguais = 0; Backups = 0; Pulados = @(); Sobras = @() }
    $jogosPc = $Jogos
    # Ryujinx: o índice de saves (imkvdb.arc) liga title id -> pasta do save. Se o PC já tem um índice
    # DIFERENTE (outros jogos), não troco o índice nem os saves (misturar quebraria os saves do PC).
    $pularRyu = $false
    if ($meta.emulador -eq 'ryujinx') {
        $idx = Join-Path $dados 'bis\system\save\8000000000000000\0\imkvdb.arc'
        $nosso = $man.Arquivos | Where-Object { $_.Destino -eq '{EMU}/bis/system/save/8000000000000000/0/imkvdb.arc' } | Select-Object -First 1
        if ((Test-Path $idx) -and $nosso -and ((Sha256 $idx) -ne $nosso.Sha)) { $pularRyu = $true }
    }
    foreach ($a in $man.Arquivos) {
        if (-not $a.Destino.StartsWith('{EMU}/')) { continue }
        $rel = $a.Destino.Substring(6)
        if ($meta.emulador -eq 'retroarch' -and $rel -eq 'retroarch.cfg') { $res.Pulados += "$rel (config global do RetroArch do Linux; ficou só como referência)"; continue }
        if ($pularRyu -and ($rel.StartsWith('bis/system/save/8000000000000000/') -or $rel.StartsWith('bis/user/save/'))) {
            $res.Pulados += "$rel (o Ryujinx do PC já tem outros saves; veja o LEIA-ME)"; continue
        }
        $alvo = Join-Path $dados ($rel.Split('/') -join '\')
        if ($a.Reescrever) {
            $txt = [IO.File]::ReadAllText((Caminho-Longo $a.Local), $Utf8)
            $txt = Trocar-Caminhos $txt $meta.reescrever $jogosPc $dados
            foreach ($ln in ($txt -split "`n")) { if ($ln -match '/home/deck|/run/media/deck') { $res.Sobras += "${rel}: $($ln.Trim())" } }
            $bytes = $Utf8.GetBytes($txt)
        } else { $bytes = $null }
        if (Test-Path -LiteralPath (Caminho-Longo $alvo)) {
            $igual = if ($bytes) { [Convert]::ToBase64String([IO.File]::ReadAllBytes((Caminho-Longo $alvo))) -eq [Convert]::ToBase64String($bytes) } else { (Sha256 $alvo) -eq $a.Sha }
            if ($igual) { $res.Iguais++; continue }
            $b = Join-Path $bk ($rel.Split('/') -join '\')
            [void][IO.Directory]::CreateDirectory((Caminho-Longo (Split-Path $b)))
            [IO.File]::Copy((Caminho-Longo $alvo), (Caminho-Longo $b), $true); $res.Backups++
        }
        [void][IO.Directory]::CreateDirectory((Caminho-Longo (Split-Path $alvo)))
        if ($bytes) { [IO.File]::WriteAllBytes((Caminho-Longo $alvo), $bytes) } else { [IO.File]::Copy((Caminho-Longo $a.Local), (Caminho-Longo $alvo), $true) }
        $res.Instalados++
    }
    $res.PularRyu = $pularRyu
    $res.Backup = $bk
    return $res
}

# ---------------------------------------------------------------- LEIA-ME -----------------
function Escrever-LeiaMe($man, [string]$raiz, $emu, $inst, [int]$falhas) {
    $m = $man.Meta; $ew = $m.emulador_windows
    $L = New-Object System.Collections.Generic.List[string]
    $L.Add("TRANSFERÊNCIA DO DECK - $($m.titulo) ($($m.console))")
    $L.Add("Gerado em $(Get-Date -Format 'dd/MM/yyyy HH:mm'). Jogo no Deck: $($m.game_id)")
    $L.Add('')
    $L.Add("Arquivos: $($man.Arquivos.Count), $([Math]::Round($m.total_bytes / 1e9, 2)) GB, todos conferidos por sha256." + $(if ($falhas) { " ATENÇÃO: $falhas arquivo(s) NÃO bateram - rode de novo." } else { '' }))
    foreach ($p in $m.resumo.PSObject.Properties) { $L.Add("  - $($p.Name): $($p.Value.arquivos) arquivos, $([Math]::Round($p.Value.bytes / 1e6, 1)) MB") }
    $L.Add('')
    $L.Add('PASTAS')
    $L.Add("  Jogo (base/update/DLC): $Jogos\$($m.console)\  - o emulador do PC abre daqui")
    $L.Add("  Aqui ($raiz):")
    $L.Add("  emulador\        dados do emulador como estavam no Deck (saves, config, mods, keys/firmware/BIOS)")
    $L.Add("  emulador-linux\  o emulador do Deck (Linux) - não roda no Windows, é só referência")
    $L.Add("  manifesto.tsv    lista com sha256 de tudo")
    $L.Add('')
    $L.Add("EMULADOR NO WINDOWS: $($ew.projeto)")
    $L.Add("  Página oficial de releases: $($ew.releases)")
    $L.Add("  Pasta de dados no PC: $($ew.dados)")
    if (-not $emu) {
        $L.Add('')
        $L.Add('>>> O EMULADOR AINDA NÃO ESTÁ NESTE PC. Faça assim:')
        $L.Add("  1. Baixe o $($ew.projeto) da página acima (versão portátil) e descompacte em $Emuladores\<nome> (você baixa; este script não baixa nada).")
        $L.Add("  2. Rode:  tools\pc\transferir-do-deck.bat -Jogo $($m.game_id) -Destino `"$(Split-Path $raiz)`" -Jogos `"$Jogos`" -SoInstalar")
        $L.Add('     (instala saves/config/mods/keys no emulador, com backup do que já existir, e acerta os caminhos)')
        $L.Add('     Emuladores em outra pasta: -Emuladores "<pasta>"; pasta de dados fora do comum: -EmuDir "<pasta de dados>".')
    } else {
        $L.Add('')
        $L.Add("INSTALADO em: $($emu.Dados)" + $(if ($emu.Exe) { "  (emulador: $($emu.Exe))" } else { '' }))
        $L.Add("  $($inst.Instalados) arquivo(s) instalados, $($inst.Iguais) já iguais, $($inst.Backups) backup(s) do PC em: $($inst.Backup)")
        foreach ($p in $inst.Pulados | Select-Object -First 20) { $L.Add("  pulado: $p") }
        if ($inst.PularRyu) {
            $L.Add('  SAVES DO RYUJINX NÃO INSTALADOS: o Ryujinx deste PC já tem saves de outros jogos (índice imkvdb.arc diferente).')
            $L.Add('  Para levar o save: abra o jogo uma vez no PC, feche, clique com o botão direito no jogo >')
            $L.Add('  "Abrir pasta de save do usuário" e copie para lá o conteúdo de:')
            foreach ($s in $m.saves_ryujinx) { $L.Add("    $raiz\emulador\bis\user\save\$($s.save_data_id)\  (as pastas 0 e 1)") }
        }
        if ($inst.Sobras.Count) {
            $L.Add('  Caminhos do Deck que ficaram nos arquivos de config (apontam para coisas que não vieram; ajuste no emulador se precisar):')
            foreach ($s in $inst.Sobras | Select-Object -First 15) { $L.Add("    $s") }
        }
    }
    $L.Add('')
    $L.Add('ONDE ESTAVAM OS SAVES NO DECK')
    foreach ($s in $m.saves) { $L.Add("  $s") }
    if (-not $m.saves) { $L.Add('  (o jogo ainda não tinha save no Deck)') }
    $L.Add('')
    $L.Add('NOTAS')
    foreach ($n in $m.notas) { $L.Add("  - $n") }
    foreach ($x in $m.excluidos) { $L.Add("  - não veio: $($x.caminho) ($($x.motivo))") }
    foreach ($a in $m.avisos) { $L.Add("  - aviso: $a") }
    $L.Add('')
    $L.Add('Nada foi apagado no Deck. Para conferir/retomar, rode o mesmo comando de novo: só copia o que faltar.')
    [IO.File]::WriteAllLines((Join-Path $raiz 'LEIA-ME.txt'), $L, (New-Object System.Text.UTF8Encoding($true)))
}

# ================================================================= principal ==============
if (-not (Test-Path $Chave)) { throw "Chave ssh não encontrada: $Chave" }
foreach ($v in 'Destino', 'Jogos') {
    $val = Get-Variable $v -ValueOnly
    $qual = Split-Path -Qualifier $val -ErrorAction SilentlyContinue
    if ($qual -and -not (Test-Path "$qual\")) {
        $novo = Join-Path $env:USERPROFILE ('DeckCommander\' + (Split-Path $val -Leaf))
        Set-Variable $v $novo
        Msg "Unidade $qual não existe; usando $novo" 'Yellow'
    }
}

if (-not $Jogo) {
    $r = Invoke-Transferir 'lista'
    if ($r.Codigo -ne 0) { throw "Não consegui listar os jogos do Deck: $($r.Erro)" }
    $opcoes = @($r.Saida -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { $c = $_.TrimEnd("`r").Split("`t"); [pscustomobject]@{ Id = $c[0]; Titulo = $c[1]; Console = $c[2] } })
    for ($i = 0; $i -lt $opcoes.Count; $i++) { Msg ("{0,3}. {1}  [{2}]" -f ($i + 1), $opcoes[$i].Titulo, $opcoes[$i].Console) }
    $n = Read-Host 'Número do jogo'
    $Jogo = $opcoes[[int]$n - 1].Id
}
if ($Jogo -notmatch '^[a-z0-9][a-z0-9._-]*$') { throw "Id de jogo inválido: $Jogo" }

$Raiz = Join-Path $Destino $Jogo
[void][IO.Directory]::CreateDirectory($Raiz)
$ArqManifesto = Join-Path $Raiz 'manifesto.tsv'
$ArqConf = Join-Path $Raiz '.conferidos.tsv'

if ($SoInstalar) {
    if (-not (Test-Path $ArqManifesto)) { throw "Ainda não há transferência em $Raiz (rode sem -SoInstalar)." }
    $texto = [IO.File]::ReadAllText($ArqManifesto, $Utf8)
} else {
    Msg "Pedindo ao Deck o manifesto de $Jogo (calcula sha256; jogos grandes demoram na 1ª vez)..." 'Cyan'
    $sub = "manifesto $Jogo --tsv" + $(if ($SemCacheNoDeck) { ' --sem-cache' } else { '' })
    $r = Invoke-Transferir $sub
    if ($r.Codigo -ne 0) { throw "O Deck não montou o manifesto: $($r.Erro)" }
    $texto = $r.Saida
    [IO.File]::WriteAllText($ArqManifesto, $texto, $Utf8)
}
$Man = Ler-Manifesto $texto
$Meta = $Man.Meta
$fora = @()
if ($SemEmuladorLinux) { $fora += 'emulador-linux' }
if ($SoConfig) { $fora += @('jogo', 'update', 'dlc', 'emulador-linux') }   # só saves/config/mods/keys
if ($fora.Count) {
    $l2 = New-Object System.Collections.Generic.List[object]
    foreach ($a in $Man.Arquivos) { if ($fora -notcontains $a.Cat) { $l2.Add($a) } }
    $Man.Arquivos = $l2
}
foreach ($a in $Man.Arquivos) { $a.Local = Caminho-Local $a.Destino $Raiz }
$bytesSel = ($Man.Arquivos | Measure-Object Tam -Sum).Sum
Msg ("{0} ({1}): {2} arquivos, {3:N2} GB -> {4}" -f $Meta.titulo, $Meta.console, $Man.Arquivos.Count, ($bytesSel / 1e9), $Raiz) 'Cyan'
Msg '  no Deck (tudo do jogo):'
foreach ($p in $Meta.resumo.PSObject.Properties) { Msg ("  {0}: {1} arquivos, {2:N1} MB" -f $p.Name, $p.Value.arquivos, ($p.Value.bytes / 1e6)) }

Carregar-Conferidos $ArqConf
$falhas = @()
for ($t = 0; $t -le $Tentativas; $t++) {
    Msg 'Conferindo o que já está no PC (sha256)...'
    $faltam = @(foreach ($a in $Man.Arquivos) { if (-not (Conferir $a $ArqConf)) { $a } })
    if (-not $faltam.Count) { $falhas = @(); break }
    $falhas = $faltam
    if ($SoInstalar -or $t -eq $Tentativas) { break }
    Msg ("Faltam {0} arquivo(s), {1:N2} GB (rodada {2})" -f $faltam.Count, (($faltam | Measure-Object Tam -Sum).Sum / 1e9), ($t + 1)) 'Cyan'
    if ($t -gt 0) {   # na repetição, o que veio com hash errado é baixado do zero
        foreach ($a in $faltam) { $fi = [IO.FileInfo]::new((Caminho-Longo $a.Local)); if ($fi.Exists -and $fi.Length -eq $a.Tam) { $fi.Delete() } }
    }
    Baixar $faltam $Raiz
}
if ($falhas.Count) {
    Msg "$($falhas.Count) arquivo(s) NÃO conferem com o Deck:" 'Red'
    $falhas | Select-Object -First 10 | ForEach-Object { Msg "  $($_.Origem)" 'Red' }
} else { Msg 'Todos os arquivos conferem com o Deck (sha256).' 'Green' }

$Emu = $null; $Inst = $null
if (-not $SemInstalar -and -not $falhas.Count) {
    $Emu = Achar-Emulador $Meta.emulador
    if ($Emu) {
        Msg "Instalando no emulador do PC: $($Emu.Dados)" 'Cyan'
        $Inst = Instalar $Man $Raiz $Emu
        Msg ("  {0} instalados, {1} já iguais, {2} backup(s) em {3}" -f $Inst.Instalados, $Inst.Iguais, $Inst.Backups, $Inst.Backup) 'Green'
    } else {
        Msg "O emulador ($($Meta.emulador_windows.projeto)) não está neste PC. Tudo ficou organizado em $Raiz; veja o LEIA-ME.txt." 'Yellow'
    }
}
Escrever-LeiaMe $Man $Raiz $Emu $Inst $falhas.Count
Msg "Pronto. Leia: $(Join-Path $Raiz 'LEIA-ME.txt')" 'Green'
if ($falhas.Count) { exit 1 }
exit 0
