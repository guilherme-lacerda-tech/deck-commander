# Deck Commander - funções da transferência nos dois sentidos (PC -> Deck e o emulador do outro lado).
# Usado por enviar-para-deck.ps1, emulador-oficial.ps1, transferir-do-deck.ps1 e transferir-fila.ps1.
# Testes: Invoke-Pester tools\pc\transferencia.Tests.ps1   (Pester 3.4)
#
# Só lê o PC (nada é apagado). A tabela de origens oficiais dos emuladores fica em config\emuladores-oficiais.json.

$script:Utf8 = New-Object System.Text.UTF8Encoding($false)
$script:Latin1 = [Text.Encoding]::GetEncoding(28591)
$script:RaizRepo = Split-Path (Split-Path $PSScriptRoot)

# extensões de jogo por console (o mesmo que dc/emulators.py; pastas de ROM dos emuladores)
$script:ExtsConsole = @{
    'psx' = @('.m3u', '.chd', '.pbp', '.cue', '.mds'); 'ps2' = @('.chd', '.iso', '.cso'); 'psp' = @('.chd', '.cso', '.iso', '.pbp')
    'switch' = @('.xci', '.nsp', '.nsz', '.xcz'); 'gc' = @('.rvz', '.iso', '.gcz', '.ciso'); 'wii' = @('.rvz', '.wbfs', '.iso', '.wad')
    'x360' = @('.iso', '.xex', '.zar'); 'n3ds' = @('.3ds', '.cci', '.cxi', '.z3ds'); 'nds' = @('.nds'); 'wiiu' = @('.wua', '.wux', '.wud', '.rpx')
}
$script:CueLike = @('.cue', '.m3u', '.gdi', '.ccd', '.mds')
$script:TextoExts = @('.ini', '.json', '.cfg', '.opt', '.rmp', '.txt', '.pnach', '.cht', '.m3u', '.cue')

function Get-CaminhoLongo([string]$p) { if ($p.StartsWith('\\?\')) { return $p }; return ('\\?\' + $p) }

# ------------------------------------------------------------------ tabela oficial --------
function Get-TabelaEmuladores {
    param([string]$Arquivo = (Join-Path $script:RaizRepo 'config\emuladores-oficiais.json'))
    $t = [IO.File]::ReadAllText($Arquivo, $script:Utf8) | ConvertFrom-Json
    $h = @{}
    foreach ($p in $t.emuladores.PSObject.Properties) { $h[$p.Name] = $p.Value }
    return $h
}

function Get-EmuDoConsole([string]$Console, $Tab) {
    foreach ($k in $Tab.Keys) { if (@($Tab[$k].consoles) -contains $Console) { return $k } }
    return $null
}

# ------------------------------------------------------------------ texto / ids -----------
function ConvertTo-Slug([string]$Texto) {
    $n = $Texto.Normalize([Text.NormalizationForm]::FormD)
    $sb = New-Object Text.StringBuilder
    foreach ($ch in $n.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne [Globalization.UnicodeCategory]::NonSpacingMark) { [void]$sb.Append($ch) }
    }
    $s = ($sb.ToString().ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
    if (-not $s) { $s = 'jogo' }
    return $s
}

# ------------------------------------------------------------------ formatos --------------
function Get-TidNpdm([string]$Npdm) {
    # program id do main.npdm (META -> ACI0 + 0x10), em 16 dígitos hex maiúsculos
    if (-not (Test-Path -LiteralPath $Npdm)) { return $null }
    $b = [IO.File]::ReadAllBytes($Npdm)
    if ($b.Length -lt 0x80 -or [Text.Encoding]::ASCII.GetString($b, 0, 4) -ne 'META') { return $null }
    $off = [BitConverter]::ToUInt32($b, 0x70)
    if ($off + 0x18 -gt $b.Length -or [Text.Encoding]::ASCII.GetString($b, $off, 4) -ne 'ACI0') { return $null }
    return ('{0:X16}' -f [BitConverter]::ToUInt64($b, $off + 0x10))
}

function Read-Imkvdb([string]$Arc) {
    # índice de saves do Ryujinx (formato no topo de dc/transferir.py)
    $out = @()
    if (-not (Test-Path -LiteralPath $Arc)) { return $out }
    $b = [IO.File]::ReadAllBytes($Arc)
    if ($b.Length -lt 12 -or [Text.Encoding]::ASCII.GetString($b, 0, 4) -ne 'IMKV') { return $out }
    $n = [BitConverter]::ToUInt32($b, 8); $o = 12
    for ($i = 0; $i -lt $n; $i++) {
        if ($o + 12 -gt $b.Length -or [Text.Encoding]::ASCII.GetString($b, $o, 4) -ne 'IMEN') { break }
        $ks = [BitConverter]::ToUInt32($b, $o + 4); $vs = [BitConverter]::ToUInt32($b, $o + 8)
        $k = $o + 12; $v = $k + $ks
        $out += [pscustomobject]@{ ProgramId = [BitConverter]::ToUInt64($b, $k); Tipo = $b[$k + 0x20]
                                   SaveDataId = ('{0:x16}' -f [BitConverter]::ToUInt64($b, $v)) }
        $o = $v + $vs
    }
    return $out
}

function Get-SerialDisco([string]$Nome, [string[]]$Arquivos) {
    # SLUS-00529: do nome ([SLUS-00529] Hercules) ou do SYSTEM.CNF lido no começo da imagem
    $m = [regex]::Match($Nome, '\b(S[CL][EUP][SMD]|SL[A-Z]{2}|SC[A-Z]{2})[_-](\d{3})\.?(\d{2})\b')
    if ($m.Success) { return ('{0}-{1}{2}' -f $m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value) }
    foreach ($a in $Arquivos) {
        if (@('.bin', '.iso', '.img', '.mdf') -notcontains ([IO.Path]::GetExtension($a).ToLower())) { continue }
        $txt = Read-InicioArquivo $a (16MB)
        $m = [regex]::Match($txt, 'BOOT2?\s*=\s*cdrom0?:\\?([A-Z]{4})_(\d{3})\.(\d{2})')
        if ($m.Success) { return ('{0}-{1}{2}' -f $m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value) }
    }
    return $null
}

function Get-IdPsp([string[]]$Arquivos) {
    # id do jogo de PSP (ULUS-10041) que dá nome à pasta de save (ULUS10041...): UMD_DATA.BIN no começo da ISO
    foreach ($a in $Arquivos) {
        if ([IO.Path]::GetExtension($a).ToLower() -ne '.iso') { continue }
        $m = [regex]::Match((Read-InicioArquivo $a (4MB)), '([A-Z]{4})-(\d{5})\|')
        if ($m.Success) { return ($m.Groups[1].Value + $m.Groups[2].Value) }
    }
    return $null
}

function Read-InicioArquivo([string]$Arq, [int]$Max) {
    try {
        $f = [IO.File]::OpenRead((Get-CaminhoLongo $Arq))
        try { $buf = New-Object byte[] ([Math]::Min($Max, $f.Length)); [void]$f.Read($buf, 0, $buf.Length) } finally { $f.Dispose() }
        return $script:Latin1.GetString($buf)
    } catch { return '' }
}

function Get-RefsDisco([string]$Rom) {
    # arquivos que um .cue/.m3u/.gdi referencia (recursivo m3u -> cue)
    $out = @(); $ext = [IO.Path]::GetExtension($Rom).ToLower(); $dir = Split-Path $Rom
    if (-not (Test-Path -LiteralPath $Rom)) { return $out }
    $txt = [IO.File]::ReadAllText($Rom, $script:Utf8)
    if ($ext -eq '.cue') {
        foreach ($m in [regex]::Matches($txt, '(?im)^\s*FILE\s+"?(.+?)"?\s+\S+\s*$')) { $out += (Join-Path $dir $m.Groups[1].Value) }
    } elseif ($ext -eq '.m3u') {
        foreach ($l in ($txt -split "`r?`n")) {
            $l = $l.Trim(); if (-not $l -or $l.StartsWith('#')) { continue }
            $q = Join-Path $dir $l; $out += $q
            if ($script:CueLike -contains ([IO.Path]::GetExtension($q).ToLower())) { $out += Get-RefsDisco $q }
        }
    } elseif ($ext -eq '.gdi') {
        foreach ($l in ($txt -split "`r?`n" | Select-Object -Skip 1)) {
            $m = [regex]::Match($l, '^\s*\d+\s+\d+\s+\d+\s+\d+\s+("([^"]+)"|(\S+))')
            if ($m.Success) { $out += (Join-Path $dir ($m.Groups[2].Value + $m.Groups[3].Value)) }
        }
    }
    return $out
}

function Get-IniValor([string]$Arq, [string]$Chave, [string]$Secao) {
    if (-not (Test-Path -LiteralPath $Arq)) { return $null }
    $sec = ''
    foreach ($l in [IO.File]::ReadAllLines($Arq, $script:Utf8)) {
        $t = $l.Trim()
        if ($t -match '^\[(.+)\]$') { $sec = $Matches[1]; continue }
        if ($Secao -and $sec -ne $Secao) { continue }
        $i = $t.IndexOf('=')
        if ($i -gt 0 -and $t.Substring(0, $i).Trim() -eq $Chave) { $v = $t.Substring($i + 1).Trim(); if ($v) { return $v } }
    }
    return $null
}

# ------------------------------------------------------------------ emulador do PC --------
function Find-EmuladorPC {
    # @{ Emu; Exe; Pasta; Dados; Versao } do emulador portátil em -Emuladores (padrão D:\Emuladores), ou $null
    param([string]$Emu, [string]$Emuladores, $Tab)
    $e = $Tab[$Emu]; if (-not $e -or -not $Emuladores) { return $null }
    $w = $e.windows; $pasta = [IO.Path]::Combine($Emuladores, $w.pasta)
    foreach ($rel in @($w.exe)) {
        $hit = $null
        if ($rel -match '[*?]') { $hit = Get-ChildItem -Path (Join-Path $pasta $rel) -File -ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_.FullName } }
        elseif (Test-Path -LiteralPath (Join-Path $pasta $rel)) { $hit = Join-Path $pasta $rel }
        if ($hit) {
            $dir = Split-Path $hit
            $dados = if ($w.dados -eq '.') { $dir } else { Join-Path $dir $w.dados }
            return [pscustomobject]@{ Emu = $Emu; Exe = $hit; Pasta = $pasta; Dados = $dados; Versao = (Get-VersaoRegistrada $Emuladores $e) }
        }
    }
    return $null
}

function Get-EmuladoresPC([string]$Emuladores, $Tab) {
    $h = [ordered]@{}
    foreach ($k in ($Tab.Keys | Sort-Object)) { $x = Find-EmuladorPC $k $Emuladores $Tab; if ($x) { $h[$k] = $x } }
    return $h
}

function Get-RegistroDownloads([string]$Emuladores) {
    $arq = Join-Path $Emuladores '_downloads\downloads.json'
    if (-not (Test-Path $arq)) { return @() }
    $j = [IO.File]::ReadAllText($arq, $script:Utf8) | ConvertFrom-Json   # PS 5.1: a lista vem como UM objeto
    return @($j | ForEach-Object { $_ })
}

function Get-VersaoRegistrada([string]$Emuladores, $E) {
    # versão que está no PC, pelo registro dos downloads oficiais (url .../download/<tag>/arquivo)
    $regs = @(Get-RegistroDownloads $Emuladores | Where-Object { $_.nome -eq $E.windows.pasta -or $_.nome -eq $E.nome -or $_.pasta -eq $E.windows.pasta })
    if (-not $regs.Count) { return $null }
    $r = $regs[-1]
    if ($r.versao) { return [string]$r.versao }
    $m = [regex]::Match([string]$r.url, '/download/([^/]+)/')
    if ($m.Success -and $m.Groups[1].Value -ne 'latest') { return $m.Groups[1].Value }
    return $null
}

# ------------------------------------------------------------------ releases oficiais -----
function Invoke-ApiJson([string]$Url) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    return Invoke-RestMethod -Uri $Url -Headers @{ 'User-Agent' = 'deck-commander-transferencia'; 'Accept' = 'application/json' } -TimeoutSec 30
}

function Get-ApiBase($Fonte, [switch]$Linux) {
    if ($Fonte.tipo -eq 'github') {
        $repo = if ($Linux -and $Fonte.repo_linux) { $Fonte.repo_linux } else { $Fonte.repo }
        return "https://api.github.com/repos/$repo"
    }
    if ($Fonte.tipo -eq 'forgejo') { return $Fonte.api }
    return $null
}

function ConvertTo-Release($r, [string]$Pedida) {
    $assets = @(foreach ($a in @($r.assets)) {
        $sha = $null; if ($a.digest -and ([string]$a.digest).StartsWith('sha256:')) { $sha = ([string]$a.digest).Substring(7) }
        [pscustomobject]@{ Nome = $a.name; Url = $a.browser_download_url; Tamanho = $a.size; Sha256 = $sha }
    })
    return [pscustomobject]@{ Versao = [string]$r.tag_name; Assets = $assets; Pedida = $Pedida; Mesma = ($Pedida -and [string]$r.tag_name -eq $Pedida) }
}

function Get-ReleaseOficial {
    # release da versão pedida (mesma build do outro lado) ou a estável mais recente
    param($Fonte, [string]$Versao, [switch]$Linux, [scriptblock]$Get = { param($u) Invoke-ApiJson $u })
    $base = Get-ApiBase $Fonte -Linux:$Linux
    if (-not $base) { return $null }
    $r = $null
    if ($Versao) { try { $r = & $Get "$base/releases/tags/$Versao" } catch { $r = $null } }
    if (-not $r) { $r = & $Get "$base/releases/latest" }
    return ConvertTo-Release $r $Versao
}

function Find-VersaoPorDigest {
    # qual release tem um arquivo com este sha256 (ex.: o AppImage do Deck) -> a mesma build para o Windows
    param($Fonte, [string]$Sha256, [switch]$Linux, [scriptblock]$Get = { param($u) Invoke-ApiJson $u })
    $base = Get-ApiBase $Fonte -Linux:$Linux
    if (-not $base -or -not $Sha256) { return $null }
    try { $lista = @(& $Get "$base/releases?per_page=40" | ForEach-Object { $_ }) } catch { return $null }   # PS 5.1: lista vem como UM objeto
    foreach ($r in $lista) { foreach ($a in @($r.assets)) { if ([string]$a.digest -eq "sha256:$($Sha256.ToLower())") { return [string]$r.tag_name } } }
    return $null
}

function Get-PlanoEmuladorPC {
    # o que baixar para o Windows quando o PC não tem o emulador (consulta a API oficial; não baixa)
    param([string]$Emu, [string]$Versao, [string]$Sha256Linux, $Tab, [string]$Emuladores,
          [scriptblock]$Get = { param($u) Invoke-ApiJson $u })
    $e = $Tab[$Emu]
    if (-not $e) { return [pscustomobject]@{ Acao = 'nenhum'; Emu = $Emu; Nome = $Emu; Motivo = "emulador sem origem oficial na tabela: $Emu" } }
    $w = $e.windows
    $base = @{ Emu = $Emu; Nome = $e.nome; Pagina = $e.pagina; Pasta = ([IO.Path]::Combine($Emuladores, $w.pasta)) }
    if ($w.manual) { return [pscustomobject](@{ Acao = 'manual'; Motivo = "baixe pela página oficial: $($e.pagina)" } + $base) }
    $comoVersao = 'pedida'
    if (-not $Versao -and $Sha256Linux) {
        $Versao = Find-VersaoPorDigest $e.fonte $Sha256Linux -Linux -Get $Get
        if ($Versao) { $comoVersao = 'achada pelo sha256 do emulador do Deck' }
    }
    try { $rel = Get-ReleaseOficial $e.fonte $Versao -Get $Get } catch {
        return [pscustomobject](@{ Acao = 'nenhum'; Motivo = "não consegui consultar a página oficial: $($_.Exception.Message)" } + $base)
    }
    if (-not $rel) { return [pscustomobject](@{ Acao = 'nenhum'; Motivo = 'fonte oficial sem API de releases' } + $base) }
    if ($w.url) {
        $vs = $rel.Versao.TrimStart('v')
        $url = $w.url.Replace('{versao_sem_v}', $vs).Replace('{versao}', $rel.Versao)
        return [pscustomobject](@{ Acao = 'baixar'; Versao = $rel.Versao; Mesma = $rel.Mesma; Url = $url; Arquivo = (Split-Path $url -Leaf)
                                   Sha256 = $null; Tamanho = $null; ComoVersao = $comoVersao } + $base)
    }
    $a = $rel.Assets | Where-Object { $_.Nome -match $w.asset } | Select-Object -First 1
    if (-not $a) { return [pscustomobject](@{ Acao = 'nenhum'; Motivo = "a release $($rel.Versao) não tem o arquivo Windows esperado" } + $base) }
    return [pscustomobject](@{ Acao = 'baixar'; Versao = $rel.Versao; Mesma = $rel.Mesma; Url = $a.Url; Arquivo = $a.Nome
                               Sha256 = $a.Sha256; Tamanho = $a.Tamanho; ComoVersao = $comoVersao } + $base)
}

function Format-PlanoEmulador($P) {
    if ($P.Acao -eq 'baixar') {
        $mesma = if ($P.Mesma) { ' - mesma versão do Deck' } else { '' }
        $conf = if ($P.Sha256) { 'sha256 publicado: ' + $P.Sha256 } else { 'sem sha256 publicado (confiro o tamanho)' }
        return "o emulador $($P.Nome) vai ser instalado no PC (versão $($P.Versao)$mesma, da página oficial: $($P.Url); $conf) em $($P.Pasta)"
    }
    if ($P.Acao -eq 'manual') { return "o PC não tem o $($P.Nome): $($P.Motivo)" }
    return "o emulador $($P.Nome) não está no PC e não dá para instalar sozinho: $($P.Motivo)"
}

function Install-EmuladorPC {
    # baixa a versão Windows OFICIAL, confere o sha256 publicado, extrai em modo portátil e registra em downloads.json.
    # Nunca sobrescreve: se a pasta já existe com arquivos, para.
    param($Plano, [string]$Emuladores, $Tab, [switch]$Simular)
    if ($Simular -or $Plano.Acao -ne 'baixar') { return ($(if ($Simular) { '[simulação] ' } else { '' }) + (Format-PlanoEmulador $Plano)) }
    $e = $Tab[$Plano.Emu]; $w = $e.windows
    $pasta = $Plano.Pasta
    if ((Test-Path $pasta) -and (Get-ChildItem $pasta -Force | Select-Object -First 1)) { throw "$pasta já existe e não está vazia: não mexo (confira o emulador ou use outra pasta em -Emuladores)" }
    $dl = Join-Path $Emuladores '_downloads'
    New-Item -ItemType Directory -Force $dl | Out-Null
    $arq = Join-Path $dl $Plano.Arquivo
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tmp = "$arq.baixando"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $Plano.Url -OutFile $tmp -UseBasicParsing -Headers @{ 'User-Agent' = 'deck-commander-transferencia' }
    $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLower()
    if ($Plano.Sha256 -and $sha -ne $Plano.Sha256.ToLower()) { Remove-Item $tmp -Force; throw "sha256 do download não confere com o publicado ($($Plano.Url))" }
    if ($Plano.Tamanho -and (Get-Item $tmp).Length -ne [int64]$Plano.Tamanho) { Remove-Item $tmp -Force; throw "tamanho do download não confere ($($Plano.Url))" }
    Move-Item $tmp $arq -Force
    New-Item -ItemType Directory -Force $pasta | Out-Null
    if ($arq.EndsWith('.zip')) { Expand-Archive -LiteralPath $arq -DestinationPath $pasta -Force }
    elseif ($arq.EndsWith('.7z')) {
        $sete = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $sete) { throw "para extrair $arq instale o 7-Zip (7-zip.org) ou extraia à mão em $pasta" }
        & $sete x -y "-o$pasta" $arq | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "7-Zip falhou ao extrair $arq" }
    } else { Copy-Item $arq $pasta }
    $x = Find-EmuladorPC $Plano.Emu $Emuladores $Tab
    if (-not $x) { throw "extraí em $pasta mas não achei $(@($w.exe) -join ' / ')" }
    $dir = Split-Path $x.Exe
    foreach ($d in @($w.portatil.pastas)) { if ($d) { New-Item -ItemType Directory -Force (Join-Path $dir $d) | Out-Null } }
    foreach ($f in @($w.portatil.arquivos)) { if ($f -and -not (Test-Path (Join-Path $dir $f))) { [IO.File]::WriteAllText((Join-Path $dir $f), '', $script:Utf8) } }
    $regs = @(Get-RegistroDownloads $Emuladores)
    $regs += [pscustomobject]@{ nome = $w.pasta; arquivo = $Plano.Arquivo; url = $Plano.Url; bytes = (Get-Item $arq).Length; sha256 = $sha
                                confere_github = [bool]$Plano.Sha256; versao = $Plano.Versao; exe = $x.Exe; instalado_em = (Get-Date -Format o)
                                por = 'deck-commander transferencia' }
    [IO.File]::WriteAllText((Join-Path $dl 'downloads.json'), (ConvertTo-Json @($regs) -Depth 4), $script:Utf8)
    return "instalado: $($Plano.Nome) $($Plano.Versao) em $($x.Exe) (modo portátil; registro em $dl\downloads.json)"
}

# ------------------------------------------------------------------ jogos do PC ------------
function Get-PastasRomEmuladores([string]$Emuladores, $Tab) {
    # pastas de jogos configuradas nos emuladores portáteis (só leitura; ignora caminhos do Deck)
    $out = New-Object System.Collections.Generic.List[object]
    $add = { param($c, $p) if ($p -and $p -match '^[A-Za-z]:' -and (Test-Path -LiteralPath $p)) { $out.Add([pscustomobject]@{ Console = $c; Pasta = $p.Replace('/', '\') }) } }
    $x = Find-EmuladorPC 'duckstation' $Emuladores $Tab
    if ($x) { foreach ($k in 'RecursivePaths', 'Paths') { $v = Get-IniValor (Join-Path $x.Dados 'settings.ini') $k 'GameList'; if ($v) { & $add 'psx' $v } } }
    $x = Find-EmuladorPC 'pcsx2' $Emuladores $Tab
    if ($x) { foreach ($k in 'RecursivePaths', 'Paths') { $v = Get-IniValor (Join-Path $x.Dados 'inis\PCSX2.ini') $k 'GameList'; if ($v) { & $add 'ps2' $v } } }
    $x = Find-EmuladorPC 'lichii' $Emuladores $Tab
    if ($x) {
        $ini = Join-Path $x.Dados 'config\qt-config.ini'
        if (Test-Path $ini) { foreach ($l in [IO.File]::ReadAllLines($ini, $script:Utf8)) { if ($l -match '^Paths\\gamedirs\\\d+\\path=(.+)$') { & $add 'switch2' $Matches[1].Trim() } } }
    }
    $x = Find-EmuladorPC 'ryujinx' $Emuladores $Tab
    if ($x -and (Test-Path (Join-Path $x.Dados 'Config.json'))) {
        try { foreach ($d in @(([IO.File]::ReadAllText((Join-Path $x.Dados 'Config.json'), $script:Utf8) | ConvertFrom-Json).game_dirs)) { & $add 'switch' $d } } catch {}
    }
    return $out
}

function Get-JogosPC {
    # jogos em <Jogos>\<console>\<jogo> + jogos soltos nas pastas de ROM dos emuladores portáteis
    param([string]$Jogos, [string]$Emuladores, $Tab, [switch]$SemPastasEmuladores)
    $lista = New-Object System.Collections.Generic.List[object]
    $ids = @{}
    $novoId = { param($c, $t) $b = $c + '-' + (ConvertTo-Slug $t); $i = $b; $n = 2; while ($ids.ContainsKey($i)) { $i = "$b-$n"; $n++ }; $ids[$i] = 1; return $i }
    if ($Jogos -and (Test-Path -LiteralPath $Jogos)) {
        foreach ($dc in Get-ChildItem -LiteralPath $Jogos -Directory -ErrorAction SilentlyContinue | Sort-Object Name) {
            $con = $dc.Name.ToLower()
            foreach ($it in Get-ChildItem -LiteralPath $dc.FullName -ErrorAction SilentlyContinue | Sort-Object Name) {
                if ($it.PSIsContainer) {
                    $lista.Add([pscustomobject]@{ Id = (& $novoId $con $it.Name); Titulo = $it.Name; Console = $con; Raiz = $it.FullName; Pasta = $it.Name; Rom = $null; Origem = 'jogos' })
                } elseif ($script:ExtsConsole[$con] -and ($script:ExtsConsole[$con] -contains $it.Extension.ToLower())) {
                    $lista.Add([pscustomobject]@{ Id = (& $novoId $con $it.BaseName); Titulo = $it.BaseName; Console = $con; Raiz = $dc.FullName; Pasta = $it.BaseName; Rom = $it.FullName; Origem = 'jogos' })
                }
            }
        }
    }
    if (-not $SemPastasEmuladores -and $Emuladores) {
        $raizJogos = if ($Jogos) { [IO.Path]::GetFullPath($Jogos).TrimEnd('\') + '\' } else { '' }
        foreach ($pr in Get-PastasRomEmuladores $Emuladores $Tab) {
            $p = [IO.Path]::GetFullPath($pr.Pasta).TrimEnd('\') + '\'
            if ($raizJogos -and $p.StartsWith($raizJogos, [StringComparison]::OrdinalIgnoreCase)) { continue }   # já listado
            if ($pr.Console -eq 'switch2') {
                foreach ($m in Get-ChildItem -LiteralPath $pr.Pasta -Recurse -Depth 4 -Filter 'main.npdm' -File -ErrorAction SilentlyContinue) {
                    if ($m.Directory.Name -ne 'exefs' -or $m.Directory.Parent.Name -ne 'base') { continue }   # <jogo>\base\exefs\main.npdm
                    $raiz = $m.Directory.Parent.Parent
                    $lista.Add([pscustomobject]@{ Id = (& $novoId 'switch2' $raiz.Name); Titulo = $raiz.Name; Console = 'switch2'; Raiz = $raiz.FullName; Pasta = $raiz.Name; Rom = $null; Origem = 'emulador' })
                }
                continue
            }
            $exts = $script:ExtsConsole[$pr.Console]
            $arqs = @(Get-ChildItem -LiteralPath $pr.Pasta -Recurse -Depth 2 -File -ErrorAction SilentlyContinue | Where-Object { $exts -contains $_.Extension.ToLower() })
            # m3u/cue têm preferência sobre os .bin que eles citam
            $citados = @{}
            foreach ($a in $arqs) { if ($script:CueLike -contains $a.Extension.ToLower()) { foreach ($r in Get-RefsDisco $a.FullName) { $citados[[IO.Path]::GetFullPath($r).ToLower()] = 1 } } }
            foreach ($a in $arqs) {
                if ($citados.ContainsKey($a.FullName.ToLower())) { continue }
                $lista.Add([pscustomobject]@{ Id = (& $novoId $pr.Console $a.BaseName); Titulo = $a.BaseName; Console = $pr.Console; Raiz = $a.DirectoryName; Pasta = $a.BaseName; Rom = $a.FullName; Origem = 'emulador' })
            }
        }
    }
    return $lista
}

# ------------------------------------------------------------------ manifesto do PC --------
function New-ColecaoArquivos { return [pscustomobject]@{ Itens = (New-Object System.Collections.Generic.List[object]); Vistos = @{}; Excluidos = @(); Avisos = @(); Notas = @() } }

function Add-Arq($Col, [string]$Caminho, [string]$Cat, [string]$Destino) {
    if (-not $Caminho -or $Col.Vistos.ContainsKey($Caminho.ToLower())) { return }
    if ($Destino -match "[`t`r`n`"\\]") { $Col.Excluidos += "$Caminho (nome com TAB/aspas/quebra de linha)"; return }
    $fi = [IO.FileInfo]::new((Get-CaminhoLongo $Caminho))
    if (-not $fi.Exists) { return }
    $Col.Vistos[$Caminho.ToLower()] = 1
    $Col.Itens.Add([pscustomobject]@{ Origem = $Caminho; Categoria = $Cat; Destino = $Destino; Tamanho = $fi.Length; Sha256 = $null
                                      Reescrever = ($Cat.StartsWith('config') -and ($script:TextoExts -contains $fi.Extension.ToLower())) })
}

function Add-Arvore($Col, [string]$Raiz, [string]$Cat, [string]$Destino, [string[]]$Pular = @()) {
    if (-not $Raiz -or -not (Test-Path -LiteralPath $Raiz -PathType Container)) { return }
    $base = [IO.Path]::GetFullPath($Raiz).TrimEnd('\')
    foreach ($f in [IO.Directory]::EnumerateFiles($base, '*', [IO.SearchOption]::AllDirectories)) {
        $rel = $f.Substring($base.Length + 1).Replace('\', '/')
        $pulou = $false; foreach ($p in $Pular) { if ($rel -eq $p -or $rel.StartsWith("$p/")) { $pulou = $true; break } }
        if (-not $pulou) { Add-Arq $Col $f $Cat "$Destino/$rel" }
    }
}

function Get-NomesCaixa([string]$Pasta, [string]$Nome) {
    if (-not (Test-Path -LiteralPath $Pasta)) { return @() }
    return @(Get-ChildItem -LiteralPath $Pasta -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq $Nome } | ForEach-Object { $_.Name })
}

function Add-ArquivosJogo($Col, $J) {
    $con = $J.Console
    if (-not $J.Rom) {   # jogo em pasta: tudo
        $base = $J.Raiz.TrimEnd('\')
        foreach ($f in [IO.Directory]::EnumerateFiles($base, '*', [IO.SearchOption]::AllDirectories)) {
            $rel = $f.Substring($base.Length + 1).Replace('\', '/')
            $top = $rel.Split('/')[0].ToLower()
            $cat = if ($con -eq 'switch2' -and ($top -eq 'updates' -or $top -eq 'update')) { 'update' } elseif ($con -eq 'switch2' -and $top -eq 'dlc') { 'dlc' } else { 'jogo' }
            Add-Arq $Col $f $cat "{JOGOS}/$con/$($J.Pasta)/$rel"
        }
        return
    }
    $dir = Split-Path $J.Rom
    $extras = @(Get-RefsDisco $J.Rom)
    $stem = [IO.Path]::GetFileNameWithoutExtension($J.Rom)
    $extras += @(Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -eq $stem } | ForEach-Object { $_.FullName })
    if ($con -eq 'switch') {
        $m = [regex]::Match([IO.Path]::GetFileName($J.Rom), '\[(0100[0-9A-Fa-f]{12})\]')
        if ($m.Success) {
            $pref = $m.Groups[1].Value.Substring(0, 12)
            $extras += @(Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\[$pref[0-9A-Fa-f]{4}\]" -and $script:ExtsConsole['switch'] -contains $_.Extension.ToLower() } | ForEach-Object { $_.FullName })
        }
    }
    foreach ($a in @($J.Rom) + $extras) {
        if (-not (Test-Path -LiteralPath $a)) { $Col.Avisos += "arquivo citado não existe: $a"; continue }
        $cat = 'jogo'
        if ($con -eq 'switch' -and $m -and $m.Success) {
            $t = [regex]::Match([IO.Path]::GetFileName($a), '\[(0100[0-9A-Fa-f]{12})\]')
            if ($t.Success -and $t.Groups[1].Value -ne $m.Groups[1].Value) { $cat = if (([Convert]::ToUInt64($t.Groups[1].Value, 16) -band 0xFFF) -eq 0x800) { 'update' } else { 'dlc' } }
        }
        Add-Arq $Col $a $cat "{JOGOS}/$con/$($J.Pasta)/$([IO.Path]::GetFileName($a))"
    }
}

function Add-DadosEmulador($Col, $J, $X, [hashtable]$Info) {
    # dados do emulador do PC que pertencem ao jogo (o inverso dos coletores de dc/transferir.py)
    $D = $X.Dados
    switch ($X.Emu) {
        'lichii' {
            $tid = Get-TidNpdm (Join-Path $J.Raiz 'base\exefs\main.npdm'); $Info.title_id = $tid
            Add-Arq $Col (Join-Path $D 'config\qt-config.ini') 'config-global' '{EMU}/config/qt-config.ini'
            if ($tid) {
                Get-ChildItem -LiteralPath (Join-Path $D 'config\custom') -Filter '*.ini' -File -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -ieq $tid } |
                    ForEach-Object { Add-Arq $Col $_.FullName 'config-jogo' "{EMU}/config/custom/$($_.Name)" }
                $sv = Join-Path $D 'nand\user\save'
                $saves = @(Get-ChildItem -LiteralPath $sv -Directory -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue } |
                           ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue } | Where-Object { $_.Name -ieq $tid })
                foreach ($s in $saves) { Add-Arvore $Col $s.FullName 'save' ('{EMU}/' + $s.FullName.Substring($D.TrimEnd('\').Length + 1).Replace('\', '/')) }
                $Info.saves = @($saves | ForEach-Object { $_.FullName })
                foreach ($d in 'load', 'sdmc\atmosphere\contents') { foreach ($n in Get-NomesCaixa (Join-Path $D $d) $tid) { Add-Arvore $Col (Join-Path (Join-Path $D $d) $n) 'mods' ("{EMU}/$($d.Replace('\', '/'))/$n") } }
            } else { $Col.Avisos += 'não achei o title id do jogo (base\exefs\main.npdm): saves/mods do Lichii não entraram' }
            Add-Arvore $Col (Join-Path $D 'keys') 'keys' '{EMU}/keys'
            Add-Arvore $Col (Join-Path $D 'nand\system\Contents') 'keys' '{EMU}/nand/system/Contents'
            Add-Arvore $Col (Join-Path $D 'nand\system\save') 'config-global' '{EMU}/nand/system/save'
            Add-Arvore $Col (Join-Path $D 'play_time') 'config-global' '{EMU}/play_time'
            $Col.Notas += 'Lichii: config global (qt-config.ini) e perfis só entram no Deck se ele ainda não tiver; saves, config do jogo, mods e keys entram (com backup).'
        }
        'ryujinx' {
            $m = [regex]::Match([IO.Path]::GetFileName([string]$J.Rom), '\[(0100[0-9A-Fa-f]{12})\]')
            $tid = if ($m.Success) { $m.Groups[1].Value.ToLower() } else { $null }; $Info.title_id = $tid
            Add-Arq $Col (Join-Path $D 'Config.json') 'config-global' '{EMU}/Config.json'
            Add-Arvore $Col (Join-Path $D 'profiles') 'config-global' '{EMU}/profiles'
            Add-Arq $Col (Join-Path $D 'system\Profiles.json') 'config-global' '{EMU}/system/Profiles.json'
            Get-ChildItem -LiteralPath (Join-Path $D 'system') -Filter '*.keys' -File -ErrorAction SilentlyContinue | ForEach-Object { Add-Arq $Col $_.FullName 'keys' "{EMU}/system/$($_.Name)" }
            Add-Arvore $Col (Join-Path $D 'bis\system\Contents') 'keys' '{EMU}/bis/system/Contents'
            Add-Arvore $Col (Join-Path $D 'bis\system\save') 'config-global' '{EMU}/bis/system/save'
            if ($tid) {
                $pid2 = [Convert]::ToUInt64($tid, 16)
                $saves = @(Read-Imkvdb (Join-Path $D 'bis\system\save\8000000000000000\0\imkvdb.arc') | Where-Object { $_.ProgramId -eq $pid2 })
                foreach ($s in $saves) { Add-Arvore $Col (Join-Path $D "bis\user\save\$($s.SaveDataId)") 'save' "{EMU}/bis/user/save/$($s.SaveDataId)" }
                $Info.saves = @($saves | ForEach-Object { Join-Path $D "bis\user\save\$($_.SaveDataId)" })
                Add-Arvore $Col (Join-Path $D "mods\contents\$tid") 'mods' "{EMU}/mods/contents/$tid"
                Add-Arvore $Col (Join-Path $D "sdcard\atmosphere\contents\$($tid.ToUpper())") 'mods' "{EMU}/sdcard/atmosphere/contents/$($tid.ToUpper())"
                Add-Arvore $Col (Join-Path $D "games\$tid") 'config-jogo' "{EMU}/games/$tid" @('cache')
            } else { $Col.Avisos += 'sem title id no nome do arquivo ([0100…]): saves/mods do Ryujinx não entraram' }
        }
        'duckstation' {
            $jogosArq = @($Col.Itens | Where-Object { $_.Categoria -eq 'jogo' } | ForEach-Object { $_.Origem })
            $serial = Get-SerialDisco ($J.Titulo + ' ' + [IO.Path]::GetFileName([string]$J.Rom)) $jogosArq; $Info.serial = $serial
            Add-Arq $Col (Join-Path $D 'settings.ini') 'config-global' '{EMU}/settings.ini'
            Add-Arq $Col (Join-Path $D 'playtime.dat') 'config-global' '{EMU}/playtime.dat'
            Add-Arvore $Col (Join-Path $D 'inputprofiles') 'config-global' '{EMU}/inputprofiles'
            $bios = Get-IniValor (Join-Path $D 'settings.ini') 'SearchDirectory' 'BIOS'
            if (-not $bios -or $bios -match '^/') { $bios = Join-Path $D 'bios' } elseif ($bios -notmatch '^[A-Za-z]:') { $bios = Join-Path $D $bios }
            Get-ChildItem -LiteralPath $bios -Filter '*.bin' -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -eq 512KB } | ForEach-Object { Add-Arq $Col $_.FullName 'keys' "{EMU}/bios/$($_.Name)" }
            $nomes = @($serial, $J.Titulo, [IO.Path]::GetFileNameWithoutExtension([string]$J.Rom)) | Where-Object { $_ }
            $saves = @()
            foreach ($par in @(@('gamesettings', 'config-jogo'), @('savestates', 'save'), @('memcards', 'save'), @('cheats', 'mods'), @('patches', 'mods'))) {
                foreach ($f in Get-ChildItem -LiteralPath (Join-Path $D $par[0]) -File -ErrorAction SilentlyContinue) {
                    $ok = $false; foreach ($n in $nomes) { if ($f.Name.StartsWith($n, [StringComparison]::OrdinalIgnoreCase)) { $ok = $true } }
                    if ($ok) { Add-Arq $Col $f.FullName $par[1] "{EMU}/$($par[0])/$($f.Name)"; if ($par[1] -eq 'save') { $saves += $f.FullName } }
                }
            }
            $Info.saves = $saves
        }
        'pcsx2' {
            $jogosArq = @($Col.Itens | Where-Object { $_.Categoria -eq 'jogo' } | ForEach-Object { $_.Origem })
            $serial = Get-SerialDisco ($J.Titulo + ' ' + [IO.Path]::GetFileName([string]$J.Rom)) $jogosArq; $Info.serial = $serial
            Add-Arq $Col (Join-Path $D 'inis\PCSX2.ini') 'config-global' '{EMU}/inis/PCSX2.ini'
            Add-Arvore $Col (Join-Path $D 'inputprofiles') 'config-global' '{EMU}/inputprofiles'
            Add-Arvore $Col (Join-Path $D 'memcards') 'save' '{EMU}/memcards'
            $Info.saves = @((Join-Path $D 'memcards'))
            $bios = Get-IniValor (Join-Path $D 'inis\PCSX2.ini') 'Bios' 'Folders'
            if (-not $bios -or $bios -match '^/') { $bios = Join-Path $D 'bios' } elseif ($bios -notmatch '^[A-Za-z]:') { $bios = Join-Path $D $bios }
            Get-ChildItem -LiteralPath $bios -File -ErrorAction SilentlyContinue | Where-Object { -not ($_.Extension -eq '.bin' -and $_.Length -eq 512KB) } | ForEach-Object { Add-Arq $Col $_.FullName 'keys' "{EMU}/bios/$($_.Name)" }
            if ($serial) { foreach ($par in @(@('gamesettings', 'config-jogo'), @('sstates', 'save'))) {
                Get-ChildItem -LiteralPath (Join-Path $D $par[0]) -Filter "$serial*" -File -ErrorAction SilentlyContinue | ForEach-Object { Add-Arq $Col $_.FullName $par[1] "{EMU}/$($par[0])/$($_.Name)" } } }
            $Col.Notas += 'PCSX2: memcards Mcd001/Mcd002 são compartilhados por todos os jogos; o do Deck é guardado no backup antes de trocar.'
        }
        'ppsspp' {
            Add-Arq $Col (Join-Path $D 'PSP\SYSTEM\ppsspp.ini') 'config-global' '{EMU}/PSP/SYSTEM/ppsspp.ini'
            Add-Arq $Col (Join-Path $D 'PSP\SYSTEM\controls.ini') 'config-global' '{EMU}/PSP/SYSTEM/controls.ini'
            $jogosArq = @($Col.Itens | Where-Object { $_.Categoria -eq 'jogo' } | ForEach-Object { $_.Origem })
            $gidPsp = Get-IdPsp $jogosArq; $Info.serial = $gidPsp
            if ($gidPsp) {
                $saves = @(Get-ChildItem -LiteralPath (Join-Path $D 'PSP\SAVEDATA') -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name.StartsWith($gidPsp) })
                foreach ($s in $saves) { Add-Arvore $Col $s.FullName 'save' "{EMU}/PSP/SAVEDATA/$($s.Name)" }
                Get-ChildItem -LiteralPath (Join-Path $D 'PSP\PPSSPP_STATE') -Filter "$gidPsp*" -File -ErrorAction SilentlyContinue | ForEach-Object { Add-Arq $Col $_.FullName 'save' "{EMU}/PSP/PPSSPP_STATE/$($_.Name)" }
                $Info.saves = @($saves | ForEach-Object { $_.FullName })
            } else { $Col.Avisos += 'não achei o id do jogo de PSP (UMD_DATA.BIN): saves do PPSSPP não entraram' }
        }
        'retroarch' {
            $stem = [IO.Path]::GetFileNameWithoutExtension([string]$J.Rom)
            foreach ($sub in 'config', 'remaps') { Get-ChildItem -LiteralPath (Join-Path $D $sub) -Recurse -Depth 1 -File -Filter "$stem.*" -ErrorAction SilentlyContinue |
                ForEach-Object { Add-Arq $Col $_.FullName 'config-jogo' "{EMU}/$sub/$($_.Directory.Name)/$($_.Name)" } }
            foreach ($sub in 'saves', 'states') { Get-ChildItem -LiteralPath (Join-Path $D $sub) -Recurse -File -Filter "$stem.*" -ErrorAction SilentlyContinue |
                ForEach-Object { Add-Arq $Col $_.FullName 'save' ("{EMU}/$sub/" + $_.FullName.Substring((Join-Path $D $sub).Length + 1).Replace('\', '/')) } }
        }
        default { $Col.Avisos += "config do emulador $($X.Emu) ainda não entra na transferência (só o jogo)" }
    }
}

function Get-ManifestoPC {
    # manifesto PC -> Deck de um jogo: arquivos com destino lógico ({JOGOS}/..., {EMU}/...), tamanho e (opcional) sha256
    param($J, $Tab, [string]$Emuladores, [string]$Jogos, [switch]$ComHash, [string]$CacheHash, [switch]$SoDados)
    $col = New-ColecaoArquivos
    if (-not $SoDados) { Add-ArquivosJogo $col $J }   # -SoDados: saves/config, sem listar o jogo inteiro
    $emu = Get-EmuDoConsole $J.Console $Tab
    $X = if ($emu) { Find-EmuladorPC $emu $Emuladores $Tab } else { $null }
    $info = @{ saves = @() }
    $regras = @()
    if ($X) {
        Add-DadosEmulador $col $J $X $info
        $regras += [pscustomobject]@{ de = $X.Dados.Replace('\', '/').TrimEnd('/'); para = '{EMU}' }
    } elseif ($emu) { $col.Avisos += "o emulador $emu não está no PC: vai só o jogo" }
    if ($Jogos) { $regras += [pscustomobject]@{ de = $Jogos.Replace('\', '/').TrimEnd('/'); para = '{JOGOS}' } }
    if ($J.Origem -eq 'emulador') { $regras += [pscustomobject]@{ de = $J.Raiz.Replace('\', '/').TrimEnd('/'); para = "{JOGOS}/$($J.Console)/$($J.Pasta)" } }
    if ($ComHash) {
        $cache = Read-CacheHash $CacheHash
        foreach ($a in $col.Itens) { $a.Sha256 = Get-Sha256Cache $a.Origem $cache $CacheHash }
    }
    $resumo = [ordered]@{}
    foreach ($a in $col.Itens) {
        if (-not $resumo.Contains($a.Categoria)) { $resumo[$a.Categoria] = [ordered]@{ arquivos = 0; bytes = [int64]0 } }
        $resumo[$a.Categoria].arquivos++; $resumo[$a.Categoria].bytes += $a.Tamanho
    }
    $arquivos = @(foreach ($a in $col.Itens) {
        [ordered]@{ rel = ConvertTo-RelArea $a.Destino; destino = $a.Destino; sha256 = $a.Sha256; tamanho = $a.Tamanho; categoria = $a.Categoria
                    reescrever = [bool]$a.Reescrever; origem = $a.Origem }
    })
    return [ordered]@{
        versao = 1; direcao = 'pc->deck'; game_id = $J.Id; titulo = $J.Titulo; console = $J.Console; emulador = $emu
        emulador_pc = $(if ($X) { [ordered]@{ versao = $X.Versao; exe = $X.Exe; dados = $X.Dados } } else { $null })
        title_id = $info.title_id; serial = $info.serial; saves = @($info.saves)
        total_bytes = [int64](($col.Itens | Measure-Object Tamanho -Sum).Sum); resumo = $resumo
        reescrever = $regras; avisos = @($col.Avisos); notas = @($col.Notas); excluidos = @($col.Excluidos); arquivos = $arquivos
        gerado_em = (Get-Date -Format o)
    }
}

function ConvertTo-RelArea([string]$Destino) {
    # {JOGOS}/psx/X/a.bin -> JOGOS/psx/X/a.bin (caminho dentro da área de recebimento do Deck)
    return ($Destino -replace '^\{(JOGOS|EMU)\}', '$1')
}

# ------------------------------------------------------------------ hash ------------------
function Read-CacheHash([string]$Arq) {
    $h = @{}
    if ($Arq -and (Test-Path -LiteralPath $Arq)) {
        foreach ($l in [IO.File]::ReadAllLines($Arq, $script:Utf8)) { $c = $l.Split("`t"); if ($c.Count -eq 4) { $h[$c[0]] = $c } }
    }
    return $h
}

function Get-Sha256Cache([string]$Caminho, [hashtable]$Cache, [string]$ArqCache) {
    $fi = [IO.FileInfo]::new((Get-CaminhoLongo $Caminho))
    $t = [string]$fi.LastWriteTimeUtc.Ticks; $c = $Cache[$Caminho]
    if ($c -and $c[1] -eq [string]$fi.Length -and $c[2] -eq $t) { return $c[3] }
    $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Get-CaminhoLongo $Caminho)).Hash.ToLower()
    $Cache[$Caminho] = @($Caminho, [string]$fi.Length, $t, $sha)
    if ($ArqCache) { [IO.File]::AppendAllText($ArqCache, (@($Caminho, $fi.Length, $t, $sha) -join "`t") + "`n", $script:Utf8) }
    return $sha
}

function Format-Sha256Sums($Arquivos) {
    # formato do sha256sum -c (dois espaços; caminho relativo a <área>/arquivos)
    $sb = New-Object Text.StringBuilder
    foreach ($a in $Arquivos) { [void]$sb.Append("$($a.sha256)  $($a.rel)`n") }
    return $sb.ToString()
}

function Read-FalhasSha256Sum([string]$Saida) {
    # linhas "caminho: FAILED" / "caminho: FAILED open or read" do sha256sum -c --quiet
    # "improperly formatted" (linha que o sha256sum não leu = arquivo NÃO conferido) também é falha
    $out = @()
    foreach ($l in ($Saida -split "`r?`n")) {
        $m = [regex]::Match($l, '^(.+): FAILED( open or read)?$')
        if ($m.Success) {
            $n = $m.Groups[1].Value
            # coreutils novo põe entre aspas simples nomes com espaço/colchete: 'a b.cue' (e ' vira '\'')
            if ($n.Length -ge 2 -and $n.StartsWith("'") -and $n.EndsWith("'")) { $n = $n.Substring(1, $n.Length - 2).Replace("'\''", "'") }
            $out += $n
        }
        elseif ($l -match 'improperly formatted') { $out += '(SHA256SUMS mal formado)' }
    }
    return $out
}

# ------------------------------------------------------------------ envio (sftp) ------------
function Read-TamanhosRemotos([string]$Saida) {
    $h = @{}
    foreach ($l in ($Saida -split "`n")) { $c = $l.TrimEnd("`r").Split("`t", 2); if ($c.Count -eq 2 -and $c[0] -match '^\d+$') { $h[$c[1]] = [int64]$c[0] } }
    return $h
}

function New-LoteSftpPut {
    # put (do zero) ou reput (continua de onde parou) para cada arquivo que falta no Deck
    param($Arquivos, [hashtable]$Remotos, [string]$AreaRemota)
    $sb = New-Object Text.StringBuilder; $n = 0
    foreach ($a in $Arquivos) {
        $tem = $Remotos[$a.rel]
        if ($null -ne $tem -and $tem -eq $a.tamanho) { continue }   # tamanho certo: o sha256sum -c confere depois
        $cmd = if ($null -ne $tem -and $tem -gt 0 -and $tem -lt $a.tamanho) { 'reput' } else { 'put' }
        [void]$sb.Append("-$cmd `"$($a.origem.Replace('\', '/'))`" `"$AreaRemota/arquivos/$($a.rel)`"`n"); $n++
    }
    return [pscustomobject]@{ Texto = $sb.ToString(); Quantos = $n }
}

function Get-AreaRemota([string]$Id, [string]$DestinoTeste) {
    # caminho relativo à home do Deck (o sftp e o ssh começam na home)
    if ($DestinoTeste) {
        $t = $DestinoTeste -replace '^~/', ''
        if ($t -match '^/|\.\.' -or $t -notmatch '^[A-Za-z0-9._/-]+$') { throw "-DestinoTeste inválido: use uma pasta na home do Deck, ex.: ~/dc-teste-receber" }
        return "$($t.TrimEnd('/'))/area/$Id"
    }
    return ".local/share/deck-commander/receber/$Id"
}

function Invoke-DeckSsh {
    # roda um comando no Deck; entrada opcional (texto ou arquivo) em bytes exatos; saída em UTF-8 exato
    param([string]$Deck, [string]$Chave, [string]$Remoto, [string]$EntradaTexto, [string]$EntradaArquivo, [int]$Timeout = 15)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'ssh.exe'
    $a = @('-i', $Chave, '-o', 'BatchMode=yes', '-o', "ConnectTimeout=$Timeout", '-o', 'ServerAliveInterval=15', $Deck, $Remoto)
    $psi.Arguments = ($a | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.RedirectStandardInput = $true
    $psi.StandardOutputEncoding = $script:Utf8; $psi.StandardErrorEncoding = $script:Utf8
    # a entrada padrão do processo usa a codificação do console: se for UTF-8 COM BOM, o .NET manda o BOM antes
    # dos bytes (quebra JSON e o SHA256SUMS no Deck). Durante o Start, UTF-8 sem BOM.
    $encAntes = $null
    try { $encAntes = [Console]::InputEncoding; [Console]::InputEncoding = $script:Utf8 } catch { $encAntes = $null }
    try { $p = [System.Diagnostics.Process]::Start($psi) } finally { if ($encAntes) { try { [Console]::InputEncoding = $encAntes } catch {} } }
    $out = $p.StandardOutput.ReadToEndAsync(); $err = $p.StandardError.ReadToEndAsync()
    $b = $null
    if ($EntradaArquivo) { $b = [IO.File]::ReadAllBytes($EntradaArquivo) } elseif ($EntradaTexto) { $b = $script:Utf8.GetBytes($EntradaTexto) }
    if ($b) { $p.StandardInput.BaseStream.Write($b, 0, $b.Length) }
    $p.StandardInput.Close(); $p.WaitForExit()
    return [pscustomobject]@{ Codigo = $p.ExitCode; Saida = $out.Result; Erro = $err.Result }
}

# ------------------------------------------------------------------ lista para o Deck -----
function Get-AssinaturaJogos($Jogos, [string]$Emuladores, $Tab) {
    # muda quando um jogo entra/sai/muda (data da pasta e das subpastas) ou um emulador entra: só então a lista é refeita
    $sb = New-Object Text.StringBuilder
    foreach ($j in $Jogos) {
        [void]$sb.Append("$($j.Id)|$($j.Raiz)|$($j.Rom)")
        $alvo = if ($j.Rom) { $j.Rom } else { $j.Raiz }
        if (Test-Path -LiteralPath $alvo) { [void]$sb.Append('|' + (Get-Item -LiteralPath $alvo).LastWriteTimeUtc.Ticks) }
        if (-not $j.Rom) { foreach ($d in Get-ChildItem -LiteralPath $j.Raiz -Directory -ErrorAction SilentlyContinue) { [void]$sb.Append("|$($d.Name):$($d.LastWriteTimeUtc.Ticks)") } }
        [void]$sb.Append("`n")
    }
    foreach ($kv in (Get-EmuladoresPC $Emuladores $Tab).GetEnumerator()) { [void]$sb.Append("emu:$($kv.Key):$($kv.Value.Versao)`n") }
    return $sb.ToString()
}

function ConvertTo-ListaPublicada {
    # pc-jogos-transferiveis.json: o que o Deck mostra em "Do PC para o Deck" e no /trazer
    param($Jogos, $Tab, [string]$Emuladores, [string]$RaizJogos)
    $saida = @(foreach ($j in $Jogos) {
        try { $m = Get-ManifestoPC $j $Tab $Emuladores $RaizJogos } catch { continue }
        [ordered]@{ id = $j.Id; titulo = $j.Titulo; console = $j.Console; emulador = $m.emulador; tamanho = $m.total_bytes
                    arquivos = @($m.arquivos).Count; resumo = $m.resumo; avisos = @($m.avisos) }
    })
    $emus = [ordered]@{}
    foreach ($kv in (Get-EmuladoresPC $Emuladores $Tab).GetEnumerator()) { $emus[$kv.Key] = [ordered]@{ versao = $kv.Value.Versao } }
    return [ordered]@{ versao = 1; em = (Get-Date -Format o); jogos = $saida; emuladores_pc = $emus }
}

Export-ModuleMember -Function *
