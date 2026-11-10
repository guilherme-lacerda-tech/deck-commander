# Deck Commander - funções do Assistente do PC (tools/pc/assistente.ps1).
#
# Aqui fica a parte que dá para testar sem abrir janela: montar comandos (ssh, PowerShell), detectar
# emuladores numa pasta, ler a rede ativa, interpretar o que o Deck responde. A janela só chama estas funções.
# Testes: tools/pc/assistente.Tests.ps1 (Pester).
#
# Salvo em UTF-8 COM BOM de propósito: o PowerShell 5.1 lê arquivo sem BOM como ANSI e estragaria os acentos.

$script:ChavesPcPermitidas = @('host_casa', 'rede_casa', 'mac', 'host_tailscale')

# ------------------------------------------------------------------------------------------------ caminhos
function Get-DcCaminhos {
    param([string]$Perfil = $env:USERPROFILE)
    $chave = Join-Path $Perfil '.ssh\deck_commander_ed25519'
    [pscustomobject]@{
        Chave       = $chave
        ChavePub    = $chave + '.pub'
        PastaConfig = Join-Path $Perfil '.deck-commander'
        DeckTxt     = Join-Path $Perfil '.deck-commander\deck.txt'
        Scripts     = $PSScriptRoot
    }
}

# ------------------------------------------------------------------------------------------------ endereço do Deck
function ConvertTo-DeckEndereco {
    <# "192.168.0.50" -> "deck@192.168.0.50"; "deck@steamdeck" fica igual; lixo -> $null #>
    param([string]$Texto)
    if ($null -eq $Texto) { return $null }
    $t = $Texto.Trim()
    if (-not $t) { return $null }
    if ($t -notmatch '@') { $t = 'deck@' + $t }
    if ($t -match '^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$') { return $t }
    return $null
}

function Get-HostDoEndereco {
    param([string]$Deck)
    if (-not $Deck) { return '' }
    return ($Deck -split '@')[-1]
}

function Read-DeckSalvo {
    param([string]$Arquivo = (Get-DcCaminhos).DeckTxt)
    if (-not (Test-Path -LiteralPath $Arquivo)) { return $null }
    $l = Get-Content -LiteralPath $Arquivo -TotalCount 1 -ErrorAction SilentlyContinue
    if (-not $l) { return $null }
    return ConvertTo-DeckEndereco $l
}

function Save-DeckEndereco {
    param([Parameter(Mandatory)][string]$Deck, [string]$Arquivo = (Get-DcCaminhos).DeckTxt)
    $d = ConvertTo-DeckEndereco $Deck
    if (-not $d) { throw "Endereço do Deck inválido: '$Deck'" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Arquivo) | Out-Null
    Set-Content -LiteralPath $Arquivo -Value $d -Encoding ascii
    return $d
}

# ------------------------------------------------------------------------------------------------ linha de comando
function Join-ArgsWindows {
    <# Junta argumentos numa linha de comando do Windows (regras do CommandLineToArgvW), com aspas onde precisa. #>
    param([string[]]$Argumentos)
    $partes = foreach ($a in $Argumentos) {
        if ($null -eq $a -or $a -eq '') { '""'; continue }
        if ($a -notmatch '[\s"]') { $a; continue }
        $sb = New-Object Text.StringBuilder
        [void]$sb.Append('"')
        $barras = 0
        foreach ($c in $a.ToCharArray()) {
            if ($c -eq '\') { $barras++; continue }
            if ($c -eq '"') { [void]$sb.Append('\' * ($barras * 2 + 1)); [void]$sb.Append('"'); $barras = 0; continue }
            if ($barras) { [void]$sb.Append('\' * $barras); $barras = 0 }
            [void]$sb.Append($c)
        }
        if ($barras) { [void]$sb.Append('\' * ($barras * 2)) }
        [void]$sb.Append('"')
        $sb.ToString()
    }
    return ($partes -join ' ')
}

function Get-SshArgs {
    param([Parameter(Mandatory)][string]$Deck, [string]$Chave = (Get-DcCaminhos).Chave, [int]$Timeout = 8)
    return @('-i', $Chave, '-o', 'BatchMode=yes', '-o', "ConnectTimeout=$Timeout",
             '-o', 'StrictHostKeyChecking=accept-new', $Deck)
}

function New-ComandoRemoto {
    <# Comandos que o PC roda no Deck por ssh. Sem aspas duplas de propósito (o PowerShell 5.1 as estraga). #>
    param([Parameter(Mandatory)][ValidateSet('teste', 'fila', 'historico', 'lista', 'pcstatus')][string]$Acao)
    $pre = 'cd ~/deck-commander && '
    switch ($Acao) {
        'teste'     { 'echo DC-OK; test -d ~/deck-commander/dc && echo DC-PROJ' }
        'fila'      { $pre + 'python3 -m dc.transferir fila-json' }
        'historico' { $pre + "python3 -c 'import json;from dc.transferir import ler_fila;print(json.dumps(ler_fila()[-15:],ensure_ascii=False))'" }
        'lista'     { $pre + 'python3 -m dc.transferir lista' }
        'pcstatus'  { $pre + 'python3 -m dc x pc status' }
    }
}

function New-ComandoConfigPc {
    <# Monta "python3 -m dc x pc config <chave> <valor>" para cada valor preenchido (só chaves e valores seguros). #>
    param([Parameter(Mandatory)][System.Collections.IDictionary]$Config)
    $cmds = @()
    foreach ($k in $script:ChavesPcPermitidas) {
        if (-not $Config.Contains($k)) { continue }
        $v = [string]$Config[$k]
        if (-not $v.Trim()) { continue }
        $v = $v.Trim()
        if ($v -notmatch '^[A-Za-z0-9.:-]+$') { throw "Valor estranho para ${k}: '$v'" }
        $cmds += "python3 -m dc x pc config $k '$v'"
    }
    foreach ($k in $Config.Keys) { if ($script:ChavesPcPermitidas -notcontains $k) { throw "Chave desconhecida: $k" } }
    if (-not $cmds) { throw 'Nada para gravar.' }
    return 'cd ~/deck-commander && ' + ($cmds -join ' && ')
}

function New-ComandoAutorizarChave {
    <# Comando que roda NO DECK: recebe a chave pública pela entrada padrão e a autoriza (sem duplicar). #>
    'mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && ' +
    "tr -d '\r' | grep . > ~/.ssh/dc_nova.pub && " +
    '(grep -qxFf ~/.ssh/dc_nova.pub ~/.ssh/authorized_keys || cat ~/.ssh/dc_nova.pub >> ~/.ssh/authorized_keys) && ' +
    'chmod 600 ~/.ssh/authorized_keys && rm -f ~/.ssh/dc_nova.pub && echo DC-OK'
}

function New-ScriptAutorizacao {
    <# Script (texto) da janela de console que pede a senha do Deck UMA vez. O assistente não vê a senha. #>
    param([Parameter(Mandatory)][string]$Deck, [Parameter(Mandatory)][string]$ChavePub)
    $q = { param($s) "'" + ($s -replace "'", "''") + "'" }
    $remoto = New-ComandoAutorizarChave
    @"
`$Host.UI.RawUI.WindowTitle = 'Deck Commander - senha do Deck'
Write-Host ''
Write-Host '  Deck Commander: autorizar este PC no Steam Deck' -ForegroundColor Cyan
Write-Host ''
Write-Host '  Digite a SENHA DO DECK (a que voce criou com passwd) e aperte Enter.'
Write-Host '  Ela nao aparece enquanto voce digita. E normal.'
Write-Host '  Isso so e pedido uma vez. O assistente nao ve nem guarda a senha.'
Write-Host ''
(Get-Content -LiteralPath $(& $q $ChavePub) -TotalCount 1).Trim() | & ssh.exe -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 $(& $q $Deck) $(& $q $remoto)
if (`$LASTEXITCODE -eq 0) { Write-Host ''; Write-Host '  Pronto! Pode voltar para o assistente.' -ForegroundColor Green; Start-Sleep -Seconds 2; exit 0 }
Write-Host ''
Write-Host '  Nao deu certo (senha errada ou Deck fora de alcance).' -ForegroundColor Yellow
Read-Host '  Aperte Enter para fechar esta janela' | Out-Null
exit 1
"@
}

function ConvertTo-ComandoCodificado {
    param([Parameter(Mandatory)][string]$Script)
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Script))
}

# ------------------------------------------------------------------------------------------------ processos
function Invoke-ProcessoCapturado {
    <# Roda um programa sem janela, captura saída e erro (UTF-8) e respeita um tempo máximo. #>
    param([Parameter(Mandatory)][string]$Arquivo, [string[]]$Argumentos = @(), [int]$TimeoutS = 60, [Text.Encoding]$Codificacao)
    if (-not $Codificacao) { $Codificacao = New-Object Text.UTF8Encoding $false }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Arquivo
    $psi.Arguments = Join-ArgsWindows $Argumentos
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.StandardOutputEncoding = $Codificacao
    $psi.StandardErrorEncoding = $Codificacao
    try { $p = [Diagnostics.Process]::Start($psi) }
    catch { return [pscustomobject]@{ Ok = $false; Codigo = -1; Saida = ''; Erro = $_.Exception.Message; Estourou = $false } }
    $p.StandardInput.Close()
    $out = $p.StandardOutput.ReadToEndAsync()
    $err = $p.StandardError.ReadToEndAsync()
    $estourou = -not $p.WaitForExit($TimeoutS * 1000)
    if ($estourou) { try { $p.Kill() } catch { } ; $p.WaitForExit(3000) | Out-Null }
    $p.WaitForExit()
    $codigo = if ($estourou) { -2 } else { $p.ExitCode }
    [pscustomobject]@{
        Ok = ($codigo -eq 0); Codigo = $codigo; Saida = $out.Result; Erro = $err.Result; Estourou = $estourou
    }
}

function Invoke-DeckSsh {
    param([Parameter(Mandatory)][string]$Deck, [Parameter(Mandatory)][string]$Comando,
          [string]$Chave = (Get-DcCaminhos).Chave, [int]$TimeoutS = 40)
    $a = @(Get-SshArgs -Deck $Deck -Chave $Chave) + @($Comando)
    return Invoke-ProcessoCapturado -Arquivo 'ssh.exe' -Argumentos $a -TimeoutS $TimeoutS
}

function Invoke-ScriptPc {
    <# Roda um script de tools/pc num PowerShell separado e captura o que ele escreve. #>
    param([Parameter(Mandatory)][string]$Script, [string[]]$Argumentos = @(), [int]$TimeoutS = 300)
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Script) + $Argumentos
    # o PowerShell filho escreve na página de código OEM do console (850 no Brasil), não em UTF-8
    $oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
    return Invoke-ProcessoCapturado -Arquivo 'powershell.exe' -Argumentos $a -TimeoutS $TimeoutS -Codificacao $oem
}

function Get-MensagemSsh {
    <# Traduz o resultado de um ssh em frase simples. #>
    param([Parameter(Mandatory)]$Resultado)
    if ($Resultado.Ok) { return 'Tudo certo.' }
    if ($Resultado.Estourou) { return 'O Deck demorou demais para responder. Tente de novo.' }
    $e = [string]$Resultado.Erro
    if ($Resultado.Codigo -eq -1) { return 'Não achei o programa ssh neste PC. Veja o passo "Antes de começar".' }
    if ($e -match 'Permission denied') { return 'O Deck recusou a chave deste PC. Use "Ligar ao Deck" para autorizar de novo.' }
    if ($e -match 'Could not resolve|Name or service not known|No such host') { return 'Não achei o Deck por esse nome. Use o IP (ex.: 192.168.0.50).' }
    if ($e -match 'timed out|Connection refused|No route|unreachable') {
        return 'Não consegui falar com o Deck. Ele está ligado, na mesma rede e com o SSH ativo (Parte 3.1)?'
    }
    if ($e -match 'No such file or directory' -or [string]$Resultado.Saida -match 'No module named') {
        return 'Conectou no Deck, mas o Deck Commander não está instalado em ~/deck-commander.'
    }
    $ultima = (($e -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 1)
    return "O Deck respondeu com erro (código $($Resultado.Codigo)): $ultima"
}

# ------------------------------------------------------------------------------------------------ emuladores
function Get-CatalogoEmuladores {
    @(
        [pscustomobject]@{ Nome = 'Lichii';      Console = 'Switch 2'; Exes = @('lichii.exe', 'eden.exe');                Pagina = 'https://github.com/zortos293/Lichii/releases' }
        [pscustomobject]@{ Nome = 'Ryujinx';     Console = 'Switch';   Exes = @('Ryujinx.exe');                           Pagina = 'https://git.ryujinx.app/projects/Ryubing/releases' }
        [pscustomobject]@{ Nome = 'PCSX2';       Console = 'PS2';      Exes = @('pcsx2-qt.exe', 'pcsx2*.exe');            Pagina = 'https://github.com/PCSX2/pcsx2/releases' }
        [pscustomobject]@{ Nome = 'DuckStation'; Console = 'PS1';      Exes = @('duckstation*.exe');                      Pagina = 'https://github.com/stenzek/duckstation/releases' }
        [pscustomobject]@{ Nome = 'PPSSPP';      Console = 'PSP';      Exes = @('PPSSPPWindows64.exe', 'PPSSPP*.exe');    Pagina = 'https://github.com/hrydgard/ppsspp/releases' }
        [pscustomobject]@{ Nome = 'Xenia';       Console = 'Xbox 360'; Exes = @('xenia_canary.exe', 'xenia*.exe');        Pagina = 'https://github.com/xenia-canary/xenia-canary-releases/releases' }
    )
}

function Find-EmuladorNaPasta {
    param([Parameter(Mandatory)]$Emulador, [Parameter(Mandatory)][string]$Pasta)
    # 1) pasta com o nome do emulador (D:\Emuladores\Ryujinx\...); 2) qualquer pasta cujo nome contenha o nome
    $candidatas = @(Get-ChildItem -LiteralPath $Pasta -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*$($Emulador.Nome)*" } | Sort-Object { $_.Name -ne $Emulador.Nome })
    foreach ($d in $candidatas) {
        foreach ($padrao in $Emulador.Exes) {
            $achou = Get-ChildItem -LiteralPath $d.FullName -Filter $padrao -File -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                Sort-Object { $_.FullName.Length } | Select-Object -First 1
            if ($achou) { return $achou.FullName }
        }
    }
    return $null
}

function Get-EmuladoresNaPasta {
    <# Diz, para cada emulador do catálogo, se existe na pasta e onde está o .exe. #>
    param([Parameter(Mandatory)][string]$Pasta)
    $existe = Test-Path -LiteralPath $Pasta -PathType Container
    foreach ($e in Get-CatalogoEmuladores) {
        $exe = if ($existe) { Find-EmuladorNaPasta -Emulador $e -Pasta $Pasta } else { $null }
        [pscustomobject]@{
            Nome = $e.Nome; Console = $e.Console; Encontrado = [bool]$exe; Exe = $exe; Pagina = $e.Pagina
        }
    }
}

# ------------------------------------------------------------------------------------------------ rede
function ConvertTo-RedeCasa {
    <# 192.168.0.20 /24 -> "192.168.0." (é assim que o Deck reconhece que está em casa) #>
    param([Parameter(Mandatory)][string]$Ip, [int]$Prefixo = 24)
    $o = $Ip.Split('.')
    if ($o.Count -ne 4) { throw "IP inválido: $Ip" }
    $n = [Math]::Min(3, [Math]::Max(1, [Math]::Floor($Prefixo / 8)))
    return (($o[0..($n - 1)]) -join '.') + '.'
}

function Test-AdaptadorVirtual {
    param([string]$Descricao, [string]$Nome)
    return ("$Descricao $Nome" -match 'Tailscale|WireGuard|VPN|Hyper-V|VirtualBox|VMware|vEthernet|Loopback|TAP-|ZeroTier|Bluetooth')
}

function Select-RedeAtiva {
    <# Escolhe a placa que leva à internet (rota padrão de menor métrica) e devolve IP, rede, MAC. Sem efeitos. #>
    param($Rotas, $Enderecos, $Adaptadores)
    $ordenadas = @($Rotas | Sort-Object { [int]$_.RouteMetric + [int]$_.InterfaceMetric })
    foreach ($r in $ordenadas) {
        $ad = $Adaptadores | Where-Object { $_.ifIndex -eq $r.ifIndex } | Select-Object -First 1
        if (-not $ad -or $ad.Status -ne 'Up') { continue }
        if (Test-AdaptadorVirtual $ad.InterfaceDescription $ad.Name) { continue }
        $ip = $Enderecos | Where-Object { $_.ifIndex -eq $r.ifIndex -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
        if (-not $ip) { continue }
        return [pscustomobject]@{
            Adaptador = $ad.Name
            Descricao = $ad.InterfaceDescription
            Ip        = $ip.IPAddress
            Prefixo   = [int]$ip.PrefixLength
            RedeCasa  = ConvertTo-RedeCasa -Ip $ip.IPAddress -Prefixo ([int]$ip.PrefixLength)
            Mac       = ([string]$ad.MacAddress).ToUpper()
            Gateway   = $r.NextHop
        }
    }
    return $null
}

function Get-RedeAtiva {
    $rotas = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $metricas = @{}
    Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $metricas[[int]$_.ifIndex] = $_.InterfaceMetric }
    $rotas = $rotas | ForEach-Object {
        [pscustomobject]@{ ifIndex = $_.ifIndex; RouteMetric = $_.RouteMetric; InterfaceMetric = [int]$metricas[[int]$_.ifIndex]; NextHop = $_.NextHop }
    }
    $end = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $ads = @(Get-NetAdapter -ErrorAction SilentlyContinue)
    return Select-RedeAtiva -Rotas $rotas -Enderecos $end -Adaptadores $ads
}

function Get-TailscaleExe {
    $c = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $c) { return $c }
    $g = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($g) { return $g.Source }
    return $null
}

function Get-IpTailscale {
    $exe = Get-TailscaleExe
    if (-not $exe) { return $null }
    $r = Invoke-ProcessoCapturado -Arquivo $exe -Argumentos @('ip', '-4') -TimeoutS 10
    $ip = ([string]$r.Saida -split "`r?`n") | Where-Object { $_ -match '^100\.\d+\.\d+\.\d+$' } | Select-Object -First 1
    return $ip
}

# ------------------------------------------------------------------------------------------------ procurar o Deck
function Get-IpsDaSubrede {
    <# Os 254 vizinhos do IP na mesma /24 (varredura leve; redes maiores ficam só na /24 do PC). #>
    param([Parameter(Mandatory)][string]$Ip)
    $o = $Ip.Split('.')
    $base = ($o[0..2] -join '.')
    1..254 | ForEach-Object { "$base.$_" } | Where-Object { $_ -ne $Ip }
}

function Test-PortasAbertas {
    <# Tenta conectar em vários IPs ao mesmo tempo (lotes) e devolve os que aceitaram. #>
    param([string[]]$Ips, [int]$Porta = 22, [int]$TimeoutMs = 700, [int]$Lote = 64)
    $abertos = New-Object Collections.Generic.List[string]
    for ($i = 0; $i -lt $Ips.Count; $i += $Lote) {
        $fatia = $Ips[$i..([Math]::Min($i + $Lote, $Ips.Count) - 1)]
        $tentativas = foreach ($ip in $fatia) {
            $c = New-Object Net.Sockets.TcpClient
            [pscustomobject]@{ Ip = $ip; Cliente = $c; Tarefa = $c.ConnectAsync($ip, $Porta) }
        }
        try { [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($tentativas.Tarefa), $TimeoutMs) | Out-Null } catch { }
        foreach ($t in $tentativas) {
            if ($t.Tarefa.Status -eq 'RanToCompletion' -and $t.Cliente.Connected) { $abertos.Add($t.Ip) }
            $t.Cliente.Close()
        }
    }
    return $abertos.ToArray()
}

function Resolve-NomeRapido {
    param([string]$Nome, [int]$TimeoutMs = 1500)
    try {
        $t = [Net.Dns]::GetHostAddressesAsync($Nome)
        if (-not $t.Wait($TimeoutMs)) { return $null }
        return ($t.Result | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1).IPAddressToString
    } catch { return $null }
}

function Find-DeckNaRede {
    <# Procura o Deck: primeiro pelo nome "steamdeck", depois quem tem a porta 22 (SSH) aberta na rede local. #>
    param([string]$IpLocal)
    $achados = New-Object Collections.Generic.List[object]
    foreach ($nome in @('steamdeck', 'steamdeck.local')) {
        $ip = Resolve-NomeRapido $nome
        if ($ip -and @(Test-PortasAbertas -Ips @($ip)).Count) { $achados.Add([pscustomobject]@{ Ip = $ip; Como = "nome $nome" }); break }
    }
    if (-not $IpLocal) { $r = Get-RedeAtiva; if ($r) { $IpLocal = $r.Ip } }
    if ($IpLocal) {
        foreach ($ip in Test-PortasAbertas -Ips @(Get-IpsDaSubrede $IpLocal)) {
            if (-not ($achados | Where-Object { $_.Ip -eq $ip })) { $achados.Add([pscustomobject]@{ Ip = $ip; Como = 'SSH aberto' }) }
        }
        # "steamdeck" pode resolver para o IP da Tailscale (100.x); para casa, o IP da rede local vem primeiro
        $base = (($IpLocal.Split('.'))[0..2] -join '.') + '.'
        return @($achados | Sort-Object @{ Expression = { -not $_.Ip.StartsWith($base) } }, @{ Expression = { $_.Como -eq 'SSH aberto' } })
    }
    return $achados.ToArray()
}

# ------------------------------------------------------------------------------------------------ respostas do Deck
function ConvertFrom-FilaJson {
    param([string]$Texto)
    if (-not $Texto -or -not $Texto.Trim()) { return }
    $itens = @($Texto | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.id })
    $saida = foreach ($e in $itens) {
        $quando = ''
        if ($e.pedido) { try { $quando = ([datetime]::Parse($e.pedido)).ToLocalTime().ToString('dd/MM HH:mm') } catch { $quando = [string]$e.pedido } }
        $nota = ''
        if ($e.PSObject.Properties['nota'] -and $e.nota) { $nota = (([string]$e.nota -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 1) }
        [pscustomobject]@{ Id = $e.id; GameId = $e.game_id; Titulo = $e.titulo; Status = $e.status; Pedido = $quando; Nota = $nota }
    }
    return $saida
}

function ConvertFrom-ListaJogos {
    <# Saída de "python3 -m dc.transferir lista": id<TAB>título<TAB>console por linha. #>
    param([string]$Texto)
    $saida = foreach ($l in ([string]$Texto -split "`r?`n")) {
        $c = $l.Split("`t")
        if ($c.Count -lt 2 -or -not $c[0].Trim()) { continue }
        [pscustomobject]@{ Id = $c[0].Trim(); Titulo = $c[1].Trim(); Console = $(if ($c.Count -ge 3) { $c[2].Trim() } else { '' }) }
    }
    return $saida
}

function ConvertFrom-SaidaBiblioteca {
    <# Da saída de "biblioteca-pc.ps1 -Simular" tira as linhas "  [Loja] Nome do jogo". #>
    param([string]$Texto)
    $saida = foreach ($l in ([string]$Texto -split "`r?`n")) {
        if ($l -match '^  \[([^\]]+)\] (.+)$') { [pscustomobject]@{ Loja = $Matches[1]; Nome = $Matches[2].Trim() } }
    }
    return $saida
}

function Format-StatusFila {
    param([string]$Status)
    switch ($Status) {
        'na fila'  { 'Esperando o PC' }
        'copiando' { 'Copiando agora' }
        'pronto'   { 'Pronto ✓' }
        'falhou'   { 'Deu erro' }
        default    { $Status }
    }
}

# ------------------------------------------------------------------------------------------------ o que já está no PC
function Get-SunshineEstado {
    $s = Get-Service -Name 'SunshineService' -ErrorAction SilentlyContinue
    [pscustomobject]@{ Instalado = [bool]$s; Rodando = [bool]($s -and $s.Status -eq 'Running') }
}

function Get-OllamaEstado {
    $exe = $null
    $c = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $c) { $exe = $c } else { $g = Get-Command ollama.exe -ErrorAction SilentlyContinue; if ($g) { $exe = $g.Source } }
    $rodando = [bool]@(Test-PortasAbertas -Ips @('127.0.0.1') -Porta 11434 -TimeoutMs 800).Count
    [pscustomobject]@{ Instalado = [bool]$exe; Exe = $exe; Rodando = $rodando }
}

function Get-TarefasDeckCommander {
    $nomes = [ordered]@{ Transferencias = 'DeckCommander Transferencias'; Biblioteca = 'DeckCommander Biblioteca PC'; IA = 'DeckCommander-IA' }
    $r = [ordered]@{}
    foreach ($k in $nomes.Keys) {
        $t = Get-ScheduledTask -TaskName $nomes[$k] -ErrorAction SilentlyContinue
        $r[$k] = [bool]($t -and $t.State -ne 'Disabled')
    }
    # a tarefa da biblioteca roda como SYSTEM e o Windows a esconde de quem não é administrador ("Acesso negado");
    # então vale também a instalação que o -Instalar deixa em Program Files
    if (-not $r.Biblioteca -and (Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'DeckCommander\pc\biblioteca-pc.ps1'))) { $r.Biblioteca = $true }
    return [pscustomobject]$r
}

function Test-Requisitos {
    [pscustomobject]@{
        Ssh       = [bool](Get-Command ssh.exe -ErrorAction SilentlyContinue)
        SshKeygen = [bool](Get-Command ssh-keygen.exe -ErrorAction SilentlyContinue)
    }
}

# ------------------------------------------------------------------------------------------------ ligar ao Deck
function New-ChaveDeck {
    <# Cria a chave do Deck Commander se ainda não existir. Devolve 'existia' ou 'criada'. #>
    param([string]$Chave = (Get-DcCaminhos).Chave)
    if (Test-Path -LiteralPath $Chave) { return 'existia' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Chave) | Out-Null
    $r = Invoke-ProcessoCapturado -Arquivo 'ssh-keygen.exe' -Argumentos @('-t', 'ed25519', '-f', $Chave, '-N', '', '-q', '-C', 'deck-commander') -TimeoutS 30
    if (-not (Test-Path -LiteralPath $Chave)) { throw "Não consegui criar a chave: $($r.Erro)" }
    return 'criada'
}

function Test-ConexaoDeck {
    param([Parameter(Mandatory)][string]$Deck, [string]$Chave = (Get-DcCaminhos).Chave)
    $r = Invoke-DeckSsh -Deck $Deck -Chave $Chave -Comando (New-ComandoRemoto teste) -TimeoutS 20
    [pscustomobject]@{
        Conectou = ([string]$r.Saida -match 'DC-OK')
        Projeto  = ([string]$r.Saida -match 'DC-PROJ')
        Mensagem = Get-MensagemSsh $r
    }
}

function Connect-Deck {
    <# Passo 1 inteiro: chave -> teste -> (se precisar) janela da senha -> teste -> grava deck.txt. #>
    param([Parameter(Mandatory)][string]$Deck, $Caminhos = (Get-DcCaminhos))
    $passos = New-Object Collections.Generic.List[string]
    $estado = New-ChaveDeck -Chave $Caminhos.Chave
    $passos.Add($(if ($estado -eq 'criada') { 'Chave de acesso criada neste PC.' } else { 'Chave de acesso deste PC: já existia.' }))
    $t = Test-ConexaoDeck -Deck $Deck -Chave $Caminhos.Chave
    if (-not $t.Conectou) {
        $passos.Add('Abrindo a janela que pede a senha do Deck (uma vez só)...')
        $script = New-ScriptAutorizacao -Deck $Deck -ChavePub $Caminhos.ChavePub
        $p = Start-Process -FilePath 'powershell.exe' -PassThru -Wait -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', (ConvertTo-ComandoCodificado $script))
        if ($p.ExitCode -ne 0) { $passos.Add('A autorização não foi concluída.') }
        $t = Test-ConexaoDeck -Deck $Deck -Chave $Caminhos.Chave
    }
    if ($t.Conectou) { Save-DeckEndereco -Deck $Deck -Arquivo $Caminhos.DeckTxt | Out-Null; $passos.Add("Endereço gravado em $($Caminhos.DeckTxt).") }
    else { $passos.Add($t.Mensagem) }
    if ($t.Conectou -and -not $t.Projeto) { $passos.Add('Atenção: o Deck respondeu, mas não achei ~/deck-commander nele (faça a Parte 1 do tutorial).') }
    [pscustomobject]@{ Ok = $t.Conectou; Projeto = $t.Projeto; Passos = $passos.ToArray() }
}

Export-ModuleMember -Function *-*
