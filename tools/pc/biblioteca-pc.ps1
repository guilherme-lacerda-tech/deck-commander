<#
.SYNOPSIS
  Deck Commander - biblioteca de jogos do PC para o Sunshine (aba "Computador" do Steam Deck).

.DESCRIPTION
  Varre os jogos instalados no PC (Epic, Riot, Steam, GOG, Ubisoft, Xbox/Microsoft Store) e mantem
  uma entrada por jogo no apps.json do Sunshine. O Deck le essa lista com "moonlight list" e cria um
  atalho para cada jogo.

  - Apps feitas a mao (ex.: "Desktop", "Steam Big Picture") nunca sao tocadas. O script so mexe nas
    entradas que ele mesmo criou (lista em C:\ProgramData\DeckCommander\biblioteca-pc.json).
  - Backup do apps.json antes de gravar; so grava se mudou; reinicia o SunshineService so se mudou
    e se nenhum Deck estiver conectado (senao fica pendente para a proxima rodada).
  - Ao fechar o jogo no Moonlight, o Sunshine roda fechar-jogo.ps1 (fecha os processos da pasta do jogo)
    e o agente da casa poe o PC para dormir 2 min depois (se ele foi acordado pela rede).

  Texto so em ASCII de proposito: o PowerShell 5.1 le .ps1 sem BOM como ANSI.

.PARAMETER Simular
  So mostra o que geraria (nao grava nada, nao precisa de administrador).
.PARAMETER Instalar
  Pede o UAC uma vez, copia os scripts para C:\Program Files\DeckCommander\pc e cria a tarefa
  agendada SYSTEM "DeckCommander Biblioteca PC" (no boot e diaria), rodando-a uma vez em seguida.
.PARAMETER NaoReiniciar
  Grava mas nao reinicia o Sunshine (testes com uma copia do apps.json).
.PARAMETER Desinstalar
  Remove a tarefa agendada (as entradas no Sunshine ficam; o backup do apps.json tambem).
#>
[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$Instalar,
    [switch]$Desinstalar,
    [switch]$NaoReiniciar,
    [string]$AppsJson = (Join-Path $env:ProgramFiles 'Sunshine\config\apps.json'),
    [string]$Dados = (Join-Path $env:ProgramData 'DeckCommander')
)
$ErrorActionPreference = 'Stop'

$NomeTarefa = 'DeckCommander Biblioteca PC'
$Destino = Join-Path $env:ProgramFiles 'DeckCommander\pc'
$FecharJogo = Join-Path $Destino 'fechar-jogo.ps1'
$Capas = Join-Path $Dados 'capas'
$ArqEstado = Join-Path $Dados 'biblioteca-pc.json'
$ArqLog = Join-Path $Dados 'biblioteca-pc.log'
$LogSunshine = Join-Path (Split-Path $AppsJson) 'sunshine.log'

function Escrever([string]$msg) {
    Write-Host $msg
    if (-not $Simular) {
        try {
            New-Item -ItemType Directory -Force -Path $Dados | Out-Null
            Add-Content -LiteralPath $ArqLog -Value ("{0} {1}" -f (Get-Date -Format s), $msg) -Encoding UTF8
        } catch { }
    }
}

function Eh-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------------------------------------------------------------------------------------------- instalar
if ($Instalar -or $Desinstalar) {
    if (-not (Eh-Admin)) {
        $modo = '-Instalar'
        if ($Desinstalar) { $modo = '-Desinstalar' }
        Write-Host 'Pedindo permissao de administrador (clique Sim)...'
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), $modo)
        return
    }
    if ($Desinstalar) {
        Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Tarefa '$NomeTarefa' removida. As entradas no Sunshine ficaram (apague pela pagina do Sunshine se quiser)."
        return
    }
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    $aqui = Split-Path -Parent $PSCommandPath
    Copy-Item -LiteralPath (Join-Path $aqui 'biblioteca-pc.ps1') -Destination $Destino -Force
    Copy-Item -LiteralPath (Join-Path $aqui 'fechar-jogo.ps1') -Destination $Destino -Force
    if (Test-Path (Join-Path $aqui 'perfil-controle.ps1')) {
        Copy-Item -LiteralPath (Join-Path $aqui 'perfil-controle.ps1') -Destination $Destino -Force
    }
    $acao = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $Destino 'biblioteca-pc.ps1'))
    $boot = New-ScheduledTaskTrigger -AtStartup
    $boot.Delay = 'PT2M'
    $diaria = New-ScheduledTaskTrigger -Daily -At '05:00'
    $quem = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    # StartWhenAvailable: o PC dorme a maior parte do tempo; a rodada perdida acontece quando ele acordar.
    # Nunca acorda o PC (WakeToRun desligado).
    $cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger @($boot, $diaria) -Principal $quem `
        -Settings $cfg -Description 'Deck Commander: jogos do PC no Sunshine (aba Computador do Steam Deck)' -Force | Out-Null
    Start-ScheduledTask -TaskName $NomeTarefa
    Write-Host "Pronto: tarefa '$NomeTarefa' criada e rodando agora. Log: $ArqLog"
    Start-Sleep -Seconds 3
    return
}

# ---------------------------------------------------------------------------------------------- utilidades
function Limpar-Nome([string]$n) {
    if (-not $n) { return '' }
    foreach ($c in @([char]0x2122, [char]0x00AE, [char]0x00A9, '"')) { $n = $n.Replace([string]$c, '') }
    return ($n -replace '\s{2,}', ' ').Trim()
}

function Slug([string]$s) {
    $d = $s.Normalize([Text.NormalizationForm]::FormD)
    $sb = New-Object Text.StringBuilder
    foreach ($ch in $d.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne [Globalization.UnicodeCategory]::NonSpacingMark) { [void]$sb.Append($ch) }
    }
    return (($sb.ToString().ToLower() -replace '[^a-z0-9]+', '-').Trim('-'))
}

function Jogo([string]$nome, [string]$loja, [string]$lancar, [string]$pasta, [string]$capa) {
    return [pscustomobject]@{ Nome = (Limpar-Nome $nome); Loja = $loja; Lancar = $lancar; Pasta = $pasta; Capa = $capa }
}

# ---------------------------------------------------------------------------------------------- lojas
function Ler-Epic {
    $dir = Join-Path $env:ProgramData 'Epic\EpicGamesLauncher\Data\Manifests'
    $out = @()
    if (-not (Test-Path $dir)) { return $out }
    foreach ($f in Get-ChildItem -Path $dir -Filter '*.item' -File) {
        try { $j = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
        $cats = @($j.AppCategories)
        if ($cats -notcontains 'games') { continue }                       # Unreal Engine, plugins do Fab...
        if ($j.bIsIncompleteInstall) { continue }
        if ($j.MainGameAppName -and $j.MainGameAppName -ne $j.AppName) { continue }   # DLC
        if (-not $j.InstallLocation -or -not (Test-Path -LiteralPath $j.InstallLocation)) { continue }
        $uri = 'com.epicgames.launcher://apps/{0}%3A{1}%3A{2}?action=launch&silent=true' -f $j.CatalogNamespace, $j.CatalogItemId, $j.AppName
        $out += Jogo $j.DisplayName 'Epic' $uri $j.InstallLocation $null
    }
    return $out
}

$RiotNomes = @{ 'lion' = '2XKO'; 'valorant' = 'VALORANT'; 'league_of_legends' = 'League of Legends'; 'bacon' = 'Legends of Runeterra' }

function Ler-Riot {
    $base = Join-Path $env:ProgramData 'Riot Games'
    $out = @()
    $instJson = Join-Path $base 'RiotClientInstalls.json'
    if (-not (Test-Path $instJson)) { return $out }
    $inst = Get-Content -LiteralPath $instJson -Raw -Encoding UTF8 | ConvertFrom-Json
    $padrao = @($inst.rc_default, $inst.rc_live) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    foreach ($yaml in Get-ChildItem -Path (Join-Path $base 'Metadata') -Filter '*.product_settings.yaml' -Recurse -File -ErrorAction SilentlyContinue) {
        $id = $yaml.Directory.Name                                     # ex.: valorant.live
        if ($id -notmatch '^(.+)\.([a-z]+)$') { continue }
        $produto, $linha = $Matches[1], $Matches[2]
        if (-not $RiotNomes.ContainsKey($produto)) { continue }        # TFT abre pelo LoL; Riot Client nao e jogo
        $txt = Get-Content -LiteralPath $yaml.FullName -Raw -Encoding UTF8
        if ($txt -notmatch 'product_install_full_path:\s*"([^"]+)"') { continue }
        $pasta = $Matches[1]
        if (-not (Test-Path -LiteralPath $pasta)) { continue }         # configurado mas nao instalado
        $cliente = $null
        if ($inst.associated_client) {
            foreach ($p in $inst.associated_client.PSObject.Properties) {
                if ($p.Name.TrimEnd('/', '\') -ieq $pasta.TrimEnd('/', '\') -and (Test-Path -LiteralPath $p.Value)) { $cliente = $p.Value; break }
            }
        }
        if (-not $cliente) { $cliente = $padrao }
        if (-not $cliente) { continue }
        $cliente = $cliente.Replace('/', '\')
        $lancar = '"{0}" --launch-product={1} --launch-patchline={2}' -f $cliente, $produto, $linha
        $ico = Join-Path $yaml.Directory.FullName ($id + '.ico')
        $capa = $null
        if (Test-Path -LiteralPath $ico) { $capa = $ico }
        $out += Jogo $RiotNomes[$produto] 'Riot' $lancar $pasta.Replace('/', '\') $capa
    }
    return $out
}

$SteamFora = @('228980', '1070560', '1391110', '1628350', '1493710', '2180100', '2348590', '1826330', '250820', '1007')
function Ler-Steam {
    $out = @()
    $raiz = $null
    foreach ($k in 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam') {
        try { $raiz = (Get-ItemProperty -Path $k -ErrorAction Stop).InstallPath; if ($raiz) { break } } catch { }
    }
    if (-not $raiz) { $raiz = Join-Path ${env:ProgramFiles(x86)} 'Steam' }
    $vdf = Join-Path $raiz 'steamapps\libraryfolders.vdf'
    if (-not (Test-Path -LiteralPath $vdf)) { return $out }
    $libs = @([regex]::Matches((Get-Content -LiteralPath $vdf -Raw -Encoding UTF8), '"path"\s+"([^"]+)"') | ForEach-Object { $_.Groups[1].Value.Replace('\\', '\') })
    foreach ($lib in ($libs | Select-Object -Unique)) {
        $sa = Join-Path $lib 'steamapps'
        foreach ($acf in Get-ChildItem -Path $sa -Filter 'appmanifest_*.acf' -File -ErrorAction SilentlyContinue) {
            $t = Get-Content -LiteralPath $acf.FullName -Raw -Encoding UTF8
            $id = [regex]::Match($t, '"appid"\s+"(\d+)"').Groups[1].Value
            $nome = [regex]::Match($t, '"name"\s+"([^"]*)"').Groups[1].Value
            $dir = [regex]::Match($t, '"installdir"\s+"([^"]*)"').Groups[1].Value
            $flags = [regex]::Match($t, '"StateFlags"\s+"(\d+)"').Groups[1].Value
            if (-not $id -or -not $nome -or $SteamFora -contains $id) { continue }
            if ($nome -match 'Redistributable|Steamworks|Proton|Steam Linux Runtime|SteamVR|Dedicated Server') { continue }
            if (-not $flags -or (([int]$flags) -band 4) -eq 0) { continue }    # 4 = totalmente instalado
            $pasta = Join-Path $sa ('common\' + $dir)
            $capa = $null
            $cache = Join-Path $raiz ('appcache\librarycache\' + $id)
            foreach ($nomeCapa in 'library_600x900.jpg', 'library_capsule.jpg', 'library_header.jpg', 'header.jpg') {
                $c = Get-ChildItem -Path $cache -Filter $nomeCapa -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($c) { $capa = $c.FullName; break }
            }
            $out += Jogo $nome 'Steam' ('steam://rungameid/' + $id) $pasta $capa
        }
    }
    return $out
}

function Ler-Gog {
    $out = @()
    foreach ($k in Get-ChildItem -Path 'HKLM:\SOFTWARE\WOW6432Node\GOG.com\Games' -ErrorAction SilentlyContinue) {
        $p = Get-ItemProperty -Path $k.PSPath
        if (-not $p.gameName -or -not $p.path -or -not (Test-Path -LiteralPath $p.path)) { continue }
        $lancar = $p.launchCommand
        if (-not $lancar -and $p.exe) { $lancar = '"{0}"' -f $p.exe }
        if (-not $lancar) { continue }
        $out += Jogo $p.gameName 'GOG' $lancar $p.path $null
    }
    return $out
}

# Qualquer outro jogo (emulador, jogo sem loja): ponha um ATALHO (.lnk) nesta pasta e ele vai para o Deck.
# Ex.: "Donkey Kong Bananza.lnk" -> lichii.exe -f -g "...\main". O nome do atalho e o nome que aparece no Deck.
$PastaAtalhos = Join-Path $env:PUBLIC 'Documents\Deck Commander\Jogos do PC'

function Ler-Atalhos {
    $out = @()
    if (-not (Test-Path -LiteralPath $PastaAtalhos)) { return $out }
    $ws = New-Object -ComObject WScript.Shell
    foreach ($f in Get-ChildItem -LiteralPath $PastaAtalhos -Filter '*.lnk' -File) {
        try { $l = $ws.CreateShortcut($f.FullName) } catch { continue }
        if (-not $l.TargetPath -or -not (Test-Path -LiteralPath $l.TargetPath)) { continue }
        $pasta = if ($l.WorkingDirectory) { $l.WorkingDirectory } else { Split-Path $l.TargetPath -Parent }
        $lancar = ('"{0}" {1}' -f $l.TargetPath, $l.Arguments).Trim()
        $out += Jogo $f.BaseName 'Atalho' $lancar $pasta $null
    }
    return $out
}

function Ler-Ubisoft {
    $out = @()
    foreach ($k in Get-ChildItem -Path 'HKLM:\SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs' -ErrorAction SilentlyContinue) {
        $dir = (Get-ItemProperty -Path $k.PSPath).InstallDir
        if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { continue }
        $out += Jogo (Split-Path ($dir.TrimEnd('/', '\')) -Leaf) 'Ubisoft' ('uplay://launch/{0}/0' -f $k.PSChildName) $dir.Replace('/', '\') $null
    }
    return $out
}

function Ler-Xbox {
    # Jogos da Microsoft Store/Xbox app: pacote com MicrosoftGame.config na pasta de instalacao.
    $out = @()
    try { $pkgs = Get-AppxPackage -AllUsers -ErrorAction Stop } catch { try { $pkgs = Get-AppxPackage } catch { return $out } }
    foreach ($p in $pkgs) {
        if ($p.IsFramework -or -not $p.InstallLocation) { continue }
        $mg = Join-Path $p.InstallLocation 'MicrosoftGame.config'
        if (-not (Test-Path -LiteralPath $mg)) { continue }
        try {
            [xml]$x = Get-Content -LiteralPath $mg -Raw -Encoding UTF8
            $nome = $x.Game.ShellVisuals.DefaultDisplayName
            if (-not $nome -or $nome -like 'ms-resource*') { $nome = $p.Name }
            $app = $x.Game.ExecutableList.Executable | Select-Object -First 1
            $aid = 'Game'
            if ($app -and $app.Id) { $aid = $app.Id }
            $out += Jogo $nome 'Xbox' ('explorer.exe shell:AppsFolder\{0}!{1}' -f $p.PackageFamilyName, $aid) $p.InstallLocation $null
        } catch { continue }
    }
    return $out
}

# ---------------------------------------------------------------------------------------------- capas
function Capa-Png($jogo) {
    # O Sunshine so aceita PNG: converte .jpg/.ico para C:\ProgramData\DeckCommander\capas\<slug>.png
    if (-not $jogo.Capa) { return $null }
    $dest = Join-Path $Capas ((Slug $jogo.Nome) + '.png')
    if ($Simular) { return $dest }
    try {
        New-Item -ItemType Directory -Force -Path $Capas | Out-Null
        if ((Test-Path -LiteralPath $dest) -and (Get-Item -LiteralPath $dest).LastWriteTime -ge (Get-Item -LiteralPath $jogo.Capa).LastWriteTime) { return $dest }
        Add-Type -AssemblyName System.Drawing
        if ($jogo.Capa -like '*.ico') {
            $ic = New-Object System.Drawing.Icon($jogo.Capa, 256, 256)
            $bmp = $ic.ToBitmap(); $ic.Dispose()
        } else {
            $bmp = [System.Drawing.Image]::FromFile($jogo.Capa)
        }
        $tmp = $dest + '.tmp'
        $bmp.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
        Move-Item -LiteralPath $tmp -Destination $dest -Force
        return $dest
    } catch {
        Escrever ("capa de {0} nao convertida: {1}" -f $jogo.Nome, $_.Exception.Message)
        return $null
    }
}

function Entrada($jogo) {
    $e = [ordered]@{ name = $jogo.Nome }
    $img = Capa-Png $jogo
    if ($img) { $e['image-path'] = $img }
    # So "detached": o Sunshine mantem a sessao ate o Moonlight sair (como a "Desktop"); o lancador abre o jogo.
    $e['detached'] = [object[]]@($jogo.Lancar)
    $undo = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Pasta "{1}"' -f $FecharJogo, $jogo.Pasta.TrimEnd('\')
    $prep = @([ordered]@{ do = ''; undo = $undo; elevated = $false })
    $perfil = Join-Path (Split-Path -Parent $FecharJogo) 'perfil-controle.ps1'
    if ($jogo.Loja -eq 'Atalho' -and (Test-Path -LiteralPath $perfil)) {
        # jogo de emulador: antes do stream entra o perfil de controle "do Deck"; depois volta o da mesa
        $base = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Acao ' -f $perfil
        $prep += [ordered]@{ do = $base + 'Aplicar'; undo = $base + 'Restaurar'; elevated = $false }
    }
    $e['prep-cmd'] = [object[]]$prep
    $e['auto-detach'] = $true
    return $e
}

function Cliente-Conectado {
    # Ultimo evento do log do Sunshine: CLIENT CONNECTED sem DISCONNECTED depois = alguem jogando agora.
    if (-not (Test-Path -LiteralPath $LogSunshine)) { return $false }
    try {
        $fs = New-Object IO.FileStream($LogSunshine, 'Open', 'Read', 'ReadWrite, Delete')
        $len = $fs.Length
        if ($len -gt 262144) { [void]$fs.Seek($len - 262144, 'Begin') }
        $txt = (New-Object IO.StreamReader($fs)).ReadToEnd(); $fs.Close()
    } catch { return $false }
    $c = $txt.LastIndexOf('CLIENT CONNECTED'); $d = $txt.LastIndexOf('CLIENT DISCONNECTED')
    return ($c -ge 0 -and $c -gt $d)
}

# ---------------------------------------------------------------------------------------------- principal
$jogos = @()
foreach ($leitor in 'Ler-Epic', 'Ler-Riot', 'Ler-Steam', 'Ler-Gog', 'Ler-Ubisoft', 'Ler-Xbox', 'Ler-Atalhos') {
    try { $jogos += @(& $leitor) } catch { Escrever ("{0}: falhou ({1})" -f $leitor, $_.Exception.Message) }
}
# mesmo nome em duas lojas: o segundo ganha a loja no nome
$vistos = @{}
foreach ($j in $jogos) {
    $k = $j.Nome.ToLower()
    if ($vistos.ContainsKey($k)) { $j.Nome = '{0} ({1})' -f $j.Nome, $j.Loja }
    $vistos[$j.Nome.ToLower()] = $true
}
$jogos = @($jogos | Where-Object { $_.Nome } | Sort-Object Nome)

$apps = Get-Content -LiteralPath $AppsJson -Raw -Encoding UTF8 | ConvertFrom-Json
$estado = [pscustomobject]@{ gerados = @(); reinicio_pendente = $false }
if (Test-Path -LiteralPath $ArqEstado) {
    try { $estado = Get-Content -LiteralPath $ArqEstado -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
}
$gerados = @($estado.gerados)
$manuais = @($apps.apps | Where-Object { $gerados -notcontains $_.name })
$nomesManuais = @($manuais | ForEach-Object { $_.name.ToLower() })

$novas = @()
$ignorados = @()
foreach ($j in $jogos) {
    if ($nomesManuais -contains $j.Nome.ToLower()) { $ignorados += $j.Nome; continue }   # app feita a mao vence
    $novas += , (Entrada $j)
}
$env0 = $apps.env
if ($null -eq $env0) { $env0 = [pscustomobject]@{} }
$novo = [ordered]@{ env = $env0; apps = [object[]]($manuais + $novas) }

$antes = $apps | ConvertTo-Json -Depth 12 -Compress
$depois = $novo | ConvertTo-Json -Depth 12 -Compress
$mudou = $antes -ne $depois

Write-Host ("Jogos encontrados no PC: {0}" -f $jogos.Count)
foreach ($j in $jogos) {
    $c = 'sem capa'
    if ($j.Capa) { $c = 'capa: ' + $j.Capa }
    Write-Host ("  [{0}] {1}`n      lancar: {2}`n      pasta:  {3}`n      {4}" -f $j.Loja, $j.Nome, $j.Lancar, $j.Pasta, $c)
}
Write-Host ("Apps mantidas (feitas a mao): {0}" -f (($manuais | ForEach-Object { $_.name }) -join ', '))
if ($ignorados) { Write-Host ("Ja existem como app feita a mao (nao duplicados): {0}" -f ($ignorados -join ', ')) }
$saem = @($gerados | Where-Object { $n = $_; -not ($novas | Where-Object { $_.name -eq $n }) })
if ($saem) { Write-Host ("Saem do Sunshine (nao estao mais no PC): {0}" -f ($saem -join ', ')) }

if ($Simular) {
    Write-Host ''
    if ($mudou) { Write-Host 'SIMULACAO: o apps.json MUDARIA. Entradas geradas:' } else { Write-Host 'SIMULACAO: nada mudaria no apps.json.' }
    if ($mudou) { Write-Host ($novas | ConvertTo-Json -Depth 8) }
    return
}

$pendente = [bool]$estado.reinicio_pendente
if ($mudou) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dados 'backup') | Out-Null
    $bak = Join-Path $Dados ('backup\apps.json.' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $AppsJson -Destination $bak -Force
    Get-ChildItem -Path (Join-Path $Dados 'backup') -Filter 'apps.json.*' | Sort-Object Name -Descending | Select-Object -Skip 10 | Remove-Item -Force
    $tmp = $AppsJson + '.dc-tmp'
    [IO.File]::WriteAllText($tmp, ($novo | ConvertTo-Json -Depth 12), (New-Object Text.UTF8Encoding($false)))   # sem BOM
    $null = Get-Content -LiteralPath $tmp -Raw -Encoding UTF8 | ConvertFrom-Json    # confere antes de trocar
    Move-Item -LiteralPath $tmp -Destination $AppsJson -Force
    Escrever ("apps.json atualizado ({0} jogo(s)); backup em {1}" -f $novas.Count, $bak)
    $pendente = $true
} else {
    Escrever ("apps.json ja estava em dia ({0} jogo(s))" -f $novas.Count)
}
if ($pendente -and $NaoReiniciar) {
    Escrever 'reinicio do Sunshine pulado (-NaoReiniciar)'
} elseif ($pendente) {
    if (Cliente-Conectado) {
        Escrever 'Deck conectado agora: o reinicio do Sunshine fica para a proxima rodada'
    } else {
        Restart-Service -Name 'SunshineService' -Force
        Escrever 'SunshineService reiniciado'
        $pendente = $false
    }
}
$estado = [ordered]@{ gerados = [object[]]@($novas | ForEach-Object { $_.name }); reinicio_pendente = $pendente
                      atualizado = (Get-Date -Format s) }
New-Item -ItemType Directory -Force -Path $Dados | Out-Null
[IO.File]::WriteAllText($ArqEstado, ($estado | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
