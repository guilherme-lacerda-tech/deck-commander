# Deck Commander - Assistente do PC (Windows).
#
# Janela com Avançar/Voltar que faz, sem digitar comandos, as Partes 3, 4 e 5 do docs/TUTORIAL-INSTALACAO.md:
# ligar o PC ao Deck (chave ssh), conferir emuladores, ativar as transferências, preparar o "jogar o PC no Deck"
# e (opcional) emprestar a IA do PC. Abrir: duplo clique em "Assistente Deck Commander.bat".
#
# A lógica testável fica em assistente-funcoes.psm1. Tudo que demora roda em segundo plano (runspace), então a
# janela nunca congela. Salvo em UTF-8 COM BOM (o PowerShell 5.1 lê arquivo sem BOM como ANSI).
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$modulo = Join-Path $aqui 'assistente-funcoes.psm1'
Import-Module $modulo -Force -DisableNameChecking

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
try { Add-Type -Namespace DC -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -ErrorAction Stop; [DC.Dpi]::SetProcessDPIAware() | Out-Null } catch { }
[System.Windows.Forms.Application]::EnableVisualStyles()

# ------------------------------------------------------------------------------------------------ estado
$script:Caminhos = Get-DcCaminhos
$script:Estado = @{
    Deck = (Read-DeckSalvo -Arquivo $script:Caminhos.DeckTxt); DeckOk = $null
    Emuladores = $null; ConfigPcGravada = $false; Jogos = @()
}
$script:Trabalhos = New-Object System.Collections.ArrayList
$script:Ocupado = 0

$Fonte      = New-Object System.Drawing.Font('Segoe UI', 10)
$FonteNeg   = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
$FonteTit   = New-Object System.Drawing.Font('Segoe UI Semibold', 16)
$FonteSub   = New-Object System.Drawing.Font('Segoe UI Semibold', 11)
$CorFundo   = [System.Drawing.Color]::White
$CorLateral = [System.Drawing.Color]::FromArgb(32, 38, 52)
$CorAtual   = [System.Drawing.Color]::FromArgb(86, 156, 255)
$CorOk      = [System.Drawing.Color]::FromArgb(22, 128, 60)
$CorErro    = [System.Drawing.Color]::FromArgb(190, 40, 40)
$CorCinza   = [System.Drawing.Color]::FromArgb(90, 90, 90)

# ------------------------------------------------------------------------------------------------ segundo plano
function Iniciar-Trabalho {
    <# Roda $Bloco num runspace com o módulo carregado; quando acabar, chama $AoTerminar($resultado, $erro) na janela. #>
    param([string]$Texto, [scriptblock]$Bloco, [object[]]$Argumentos = @(), [scriptblock]$AoTerminar)
    $iss = [System.Management.Automation.Runspaces.InitialSessionState]::CreateDefault()
    $iss.ImportPSModule(@($modulo))
    $rs = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspace($iss)
    $rs.ApartmentState = 'STA'
    $rs.Open()
    $ps = [PowerShell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($Bloco.ToString())
    foreach ($a in $Argumentos) { [void]$ps.AddArgument($a) }
    $h = $ps.BeginInvoke()
    [void]$script:Trabalhos.Add(@{ Ps = $ps; H = $h; Fim = $AoTerminar; Texto = $Texto })
    $script:Ocupado++
    Atualizar-Barra $Texto
}

function Atualizar-Barra([string]$Texto) {
    if ($script:Ocupado -gt 0) {
        $script:Progresso.Visible = $true
        $script:LblTrabalho.Text = 'Trabalhando… ' + $Texto
    } else {
        $script:Progresso.Visible = $false
        $script:LblTrabalho.Text = ''
    }
}

function Verificar-Trabalhos {
    foreach ($t in @($script:Trabalhos)) {
        if (-not $t.H.IsCompleted) { continue }
        [void]$script:Trabalhos.Remove($t)
        $res = $null; $erro = $null
        try {
            $res = $t.Ps.EndInvoke($t.H)
            if ($t.Ps.Streams.Error.Count) { $erro = $t.Ps.Streams.Error[0].Exception.Message }
            if ($res -and $res.Count -eq 1) { $res = $res[0] }
        } catch { $erro = $_.Exception.InnerException.Message; if (-not $erro) { $erro = $_.Exception.Message } }
        try { $t.Ps.Runspace.Close(); $t.Ps.Dispose() } catch { }
        $script:Ocupado--
        Atualizar-Barra ''
        if ($t.Fim) {
            try { & $t.Fim $res $erro } catch { Mostrar $script:LblTrabalho ('Erro inesperado: ' + $_.Exception.Message) 'erro' }
        }
    }
}

# ------------------------------------------------------------------------------------------------ peças da janela
function Mostrar($Rotulo, [string]$Texto, [string]$Tipo = 'info') {
    $Rotulo.Text = $Texto
    $Rotulo.ForeColor = switch ($Tipo) { 'ok' { $CorOk } 'erro' { $CorErro } default { $CorCinza } }
}

function Nova-Pagina([string]$Titulo, [string]$Intro) {
    $p = New-Object System.Windows.Forms.FlowLayoutPanel
    $p.FlowDirection = 'TopDown'; $p.WrapContents = $false; $p.AutoScroll = $true
    $p.Dock = 'Fill'; $p.Padding = New-Object System.Windows.Forms.Padding(24, 18, 18, 10)
    $p.BackColor = $CorFundo; $p.Visible = $false
    $t = New-Object System.Windows.Forms.Label
    $t.Text = $Titulo; $t.Font = $FonteTit; $t.AutoSize = $true; $t.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 6)
    $p.Controls.Add($t)
    if ($Intro) { [void](Novo-Texto $p $Intro) }
    $script:Conteudo.Controls.Add($p)
    return $p
}

function Novo-Texto($Pai, [string]$Texto, [System.Drawing.Font]$F = $Fonte) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $Texto; $l.Font = $F; $l.AutoSize = $true
    $l.MaximumSize = New-Object System.Drawing.Size(600, 0)
    $l.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 4)
    $Pai.Controls.Add($l)
    return $l
}

function Novo-Subtitulo($Pai, [string]$Texto) {
    $l = Novo-Texto $Pai $Texto $FonteSub
    $l.Margin = New-Object System.Windows.Forms.Padding(0, 14, 0, 2)
    return $l
}

function Nova-Linha($Pai) {
    $f = New-Object System.Windows.Forms.FlowLayoutPanel
    $f.FlowDirection = 'LeftToRight'; $f.WrapContents = $false; $f.AutoSize = $true
    $f.Margin = New-Object System.Windows.Forms.Padding(0, 2, 0, 2)
    $Pai.Controls.Add($f)
    return $f
}

function Novo-Botao($Pai, [string]$Texto, [scriptblock]$Clique) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $Texto; $b.Font = $Fonte; $b.AutoSize = $true; $b.Padding = New-Object System.Windows.Forms.Padding(8, 2, 8, 2)
    $b.Margin = New-Object System.Windows.Forms.Padding(0, 2, 8, 2)
    $b.Add_Click($Clique)
    $Pai.Controls.Add($b)
    return $b
}

function Nova-Caixa($Pai, [int]$Largura = 260, [string]$Texto = '') {
    $c = New-Object System.Windows.Forms.TextBox
    $c.Font = $Fonte; $c.Width = $Largura; $c.Text = $Texto
    $c.Margin = New-Object System.Windows.Forms.Padding(0, 4, 8, 2)
    $Pai.Controls.Add($c)
    return $c
}

function Novo-Resultado($Pai) {
    $l = Novo-Texto $Pai ''
    $l.Font = $FonteNeg
    return $l
}

function Deck-Atual {
    if ($script:Estado.Deck) { return $script:Estado.Deck }
    return $null
}

function Exigir-Deck($Rotulo) {
    if (Deck-Atual) { return $true }
    Mostrar $Rotulo 'Primeiro ligue o PC ao Deck (passo "Ligar ao Deck").' 'erro'
    return $false
}

# ------------------------------------------------------------------------------------------------ janela
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Assistente Deck Commander'
$form.Font = $Fonte
$form.AutoScaleDimensions = New-Object System.Drawing.SizeF(96, 96)
$form.AutoScaleMode = 'Dpi'
$form.ClientSize = New-Object System.Drawing.Size(900, 620)
$form.MinimumSize = New-Object System.Drawing.Size(820, 560)
$form.StartPosition = 'CenterScreen'
$form.BackColor = $CorFundo

$lateral = New-Object System.Windows.Forms.FlowLayoutPanel
$lateral.Dock = 'Left'; $lateral.Width = 210; $lateral.BackColor = $CorLateral
$lateral.FlowDirection = 'TopDown'; $lateral.WrapContents = $false
$lateral.Padding = New-Object System.Windows.Forms.Padding(14, 20, 8, 8)

$rodape = New-Object System.Windows.Forms.Panel
$rodape.Dock = 'Bottom'; $rodape.Height = 58; $rodape.BackColor = [System.Drawing.Color]::FromArgb(244, 245, 248)

$script:Conteudo = New-Object System.Windows.Forms.Panel
$script:Conteudo.Dock = 'Fill'; $script:Conteudo.BackColor = $CorFundo

$form.Controls.Add($script:Conteudo)
$form.Controls.Add($rodape)
$form.Controls.Add($lateral)

$script:Progresso = New-Object System.Windows.Forms.ProgressBar
$script:Progresso.Style = 'Marquee'; $script:Progresso.MarqueeAnimationSpeed = 30
$script:Progresso.Size = New-Object System.Drawing.Size(120, 14); $script:Progresso.Location = New-Object System.Drawing.Point(16, 22)
$script:Progresso.Visible = $false
$script:LblTrabalho = New-Object System.Windows.Forms.Label
$script:LblTrabalho.AutoSize = $true; $script:LblTrabalho.Location = New-Object System.Drawing.Point(144, 19); $script:LblTrabalho.ForeColor = $CorCinza
$btnVoltar = New-Object System.Windows.Forms.Button
$btnVoltar.Text = '< Voltar'; $btnVoltar.Size = New-Object System.Drawing.Size(100, 34); $btnVoltar.Anchor = 'Top,Right'
$btnAvancar = New-Object System.Windows.Forms.Button
$btnAvancar.Text = 'Avançar >'; $btnAvancar.Size = New-Object System.Drawing.Size(110, 34); $btnAvancar.Anchor = 'Top,Right'
$btnVoltar.Location = New-Object System.Drawing.Point(($form.ClientSize.Width - 240), 12)
$btnAvancar.Location = New-Object System.Drawing.Point(($form.ClientSize.Width - 130), 12)
$rodape.Controls.AddRange(@($script:Progresso, $script:LblTrabalho, $btnVoltar, $btnAvancar))

$script:Paginas = New-Object System.Collections.ArrayList
$script:Indices = New-Object System.Collections.ArrayList
$script:AoMostrar = @{}
$script:Atual = 0

function Registrar-Pagina($Pagina, [string]$NomeLateral, [scriptblock]$AoMostrar) {
    $i = $script:Paginas.Add($Pagina)
    $l = New-Object System.Windows.Forms.Label
    $l.Text = "$($i + 1). $NomeLateral"; $l.AutoSize = $true; $l.Font = $Fonte
    $l.ForeColor = [System.Drawing.Color]::FromArgb(170, 178, 195); $l.Cursor = 'Hand'
    $l.Margin = New-Object System.Windows.Forms.Padding(0, 6, 0, 6); $l.Tag = $i
    $l.Add_Click({ param($s, $e) Ir-Para ([int]$s.Tag) })
    $lateral.Controls.Add($l)
    [void]$script:Indices.Add($l)
    if ($AoMostrar) { $script:AoMostrar[$i] = $AoMostrar }
}

function Ir-Para([int]$i) {
    if ($i -lt 0 -or $i -ge $script:Paginas.Count) { return }
    for ($k = 0; $k -lt $script:Paginas.Count; $k++) {
        $script:Paginas[$k].Visible = ($k -eq $i)
        $script:Indices[$k].ForeColor = if ($k -eq $i) { [System.Drawing.Color]::White } elseif ($k -lt $i) { $CorAtual } else { [System.Drawing.Color]::FromArgb(170, 178, 195) }
        $script:Indices[$k].Font = if ($k -eq $i) { $FonteNeg } else { $Fonte }
    }
    $script:Atual = $i
    $btnVoltar.Enabled = ($i -gt 0)
    $btnAvancar.Text = if ($i -eq $script:Paginas.Count - 1) { 'Concluir' } else { 'Avançar >' }
    if ($script:AoMostrar.ContainsKey($i)) { & $script:AoMostrar[$i] }
}

$btnVoltar.Add_Click({ Ir-Para ($script:Atual - 1) })
$btnAvancar.Add_Click({ if ($script:Atual -eq $script:Paginas.Count - 1) { $form.Close() } else { Ir-Para ($script:Atual + 1) } })

# ================================================================================================ 0. boas-vindas
$p0 = Nova-Pagina 'Bem-vindo' 'Este assistente prepara este PC para conversar com o seu Steam Deck. São 5 passos curtos; cada um mostra na hora se deu certo. Pode pular o que não quiser e voltar quando quiser.'
Novo-Subtitulo $p0 'Antes de começar' | Out-Null
[void](Novo-Texto $p0 '• No Deck, o Deck Commander já instalado (Parte 1 do tutorial).')
[void](Novo-Texto $p0 '• No Deck, o SSH ligado. No Konsole do Deck: sudo systemctl enable --now sshd')
[void](Novo-Texto $p0 '• O Deck e o PC ligados na mesma rede (mesmo Wi-Fi/roteador).')
$lblReq = Novo-Resultado $p0
$req = Test-Requisitos
if ($req.Ssh -and $req.SshKeygen) { Mostrar $lblReq 'Este PC tem o SSH do Windows ✓' 'ok' }
else { Mostrar $lblReq 'Falta o "Cliente OpenSSH" do Windows. Instale em Configurações > Sistema > Recursos opcionais > Cliente OpenSSH e abra o assistente de novo.' 'erro' }
Registrar-Pagina $p0 'Bem-vindo' $null

# ================================================================================================ 1. ligar ao Deck
$p1 = Nova-Pagina 'Ligar ao Deck' 'O PC fala com o Deck por SSH, com uma chave só deste PC. A senha do Deck é pedida UMA vez, numa janela preta separada; o assistente não vê nem guarda a senha.'
[void](Novo-Texto $p1 'IP do Deck (no Deck: Configurações > Internet > sua rede, ou deixe o assistente procurar):')
$l1 = Nova-Linha $p1
$txtDeck = Nova-Caixa $l1 220 (Get-HostDoEndereco $script:Estado.Deck)
$btnProcurar = Novo-Botao $l1 'Procurar' {
    Mostrar $lblDeck 'Procurando o Deck na rede (leva alguns segundos)…'
    $lstAchados.Items.Clear()
    Iniciar-Trabalho 'procurando o Deck' { Find-DeckNaRede } @() {
        param($r, $erro)
        $itens = @($r | Where-Object { $_ })
        if ($erro) { Mostrar $lblDeck "Não consegui procurar: $erro" 'erro'; return }
        if (-not $itens.Count) { Mostrar $lblDeck 'Não achei nenhum aparelho com SSH ligado. Confira o SSH no Deck e digite o IP à mão.' 'erro'; return }
        foreach ($a in $itens) { [void]$lstAchados.Items.Add("$($a.Ip)   ($($a.Como))") }
        $txtDeck.Text = $itens[0].Ip
        $lstAchados.Visible = $true
        Mostrar $lblDeck "Achei $($itens.Count) aparelho(s) com SSH. Coloquei o primeiro; se não for o Deck, clique em outro da lista." 'ok'
    }
}
$btnLigar = Novo-Botao $l1 'Ligar ao Deck' {
    $d = ConvertTo-DeckEndereco $txtDeck.Text
    if (-not $d) { Mostrar $lblDeck 'Digite o IP do Deck (ex.: 192.168.0.50).' 'erro'; return }
    Mostrar $lblDeck "Ligando a $d… se abrir uma janela preta pedindo senha, digite a senha do Deck lá."
    Iniciar-Trabalho 'ligando ao Deck' { param($d) Connect-Deck -Deck $d } @($d) {
        param($r, $erro)
        if ($erro) { Mostrar $lblDeck "Erro: $erro" 'erro'; return }
        $txtPassos.Text = ($r.Passos -join "`r`n")
        if ($r.Ok) { $script:Estado.Deck = (Read-DeckSalvo -Arquivo $script:Caminhos.DeckTxt); $script:Estado.DeckOk = $true; Mostrar $lblDeck 'Conectado ✓' 'ok' }
        else { $script:Estado.DeckOk = $false; Mostrar $lblDeck 'Não conectou. Veja abaixo o que aconteceu.' 'erro' }
    }
}
[void](Novo-Botao $l1 'Testar' {
    $d = ConvertTo-DeckEndereco $txtDeck.Text
    if (-not $d) { Mostrar $lblDeck 'Digite o IP do Deck.' 'erro'; return }
    Iniciar-Trabalho 'testando a conexão' { param($d) Test-ConexaoDeck -Deck $d } @($d) {
        param($r, $erro)
        if ($erro) { Mostrar $lblDeck "Erro: $erro" 'erro'; return }
        if ($r.Conectou) {
            $script:Estado.DeckOk = $true
            if (-not $script:Estado.Deck) { $script:Estado.Deck = ConvertTo-DeckEndereco $txtDeck.Text }
            Mostrar $lblDeck $(if ($r.Projeto) { 'Conectado ✓' } else { 'Conectado ✓, mas o Deck Commander não está no Deck (~/deck-commander).' }) 'ok'
        } else { $script:Estado.DeckOk = $false; Mostrar $lblDeck $r.Mensagem 'erro' }
    }
})
$lstAchados = New-Object System.Windows.Forms.ListBox
$lstAchados.Width = 360; $lstAchados.Height = 80; $lstAchados.Visible = $false
$lstAchados.Add_SelectedIndexChanged({ if ($lstAchados.SelectedItem) { $txtDeck.Text = ([string]$lstAchados.SelectedItem).Split(' ')[0] } })
$p1.Controls.Add($lstAchados)
$lblDeck = Novo-Resultado $p1
$txtPassos = New-Object System.Windows.Forms.TextBox
$txtPassos.Multiline = $true; $txtPassos.ReadOnly = $true; $txtPassos.Width = 600; $txtPassos.Height = 110
$txtPassos.ScrollBars = 'Vertical'; $txtPassos.BackColor = $CorFundo
$p1.Controls.Add($txtPassos)
if ($script:Estado.Deck) { Mostrar $lblDeck "Endereço salvo: $($script:Estado.Deck). Clique em Testar para conferir." }
Registrar-Pagina $p1 'Ligar ao Deck' $null

# ================================================================================================ 2. emuladores
$p2 = Nova-Pagina 'Emuladores no PC' 'Para jogar no PC os jogos que vêm do Deck, o PC precisa dos emuladores (versão Windows oficial), cada um numa pasta dentro desta:'
$l2 = Nova-Linha $p2
$txtEmu = Nova-Caixa $l2 320 'D:\Emuladores'
[void](Novo-Botao $l2 'Escolher…' {
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Pasta onde ficam (ou vão ficar) os emuladores'
    if (Test-Path -LiteralPath $txtEmu.Text) { $dlg.SelectedPath = $txtEmu.Text }
    if ($dlg.ShowDialog($form) -eq 'OK') { $txtEmu.Text = $dlg.SelectedPath; Verificar-Emuladores }
})
[void](Novo-Botao $l2 'Verificar' { Verificar-Emuladores })
$lblEmu = Novo-Resultado $p2
$listaEmu = New-Object System.Windows.Forms.TableLayoutPanel
$listaEmu.AutoSize = $true; $listaEmu.ColumnCount = 3
$p2.Controls.Add($listaEmu)
[void](Novo-Texto $p2 'Dica: depois de extrair, deixe o emulador no "modo portátil" (tudo dentro da pasta dele). Como fazer em cada um está na Parte 4.1 do tutorial.')

function Verificar-Emuladores {
    $pasta = $txtEmu.Text.Trim()
    Iniciar-Trabalho 'olhando os emuladores' { param($p) [pscustomobject]@{ Pasta = $p; Itens = @(Get-EmuladoresNaPasta -Pasta $p) } } @($pasta) {
        param($r, $erro)
        if ($erro) { Mostrar $lblEmu "Erro: $erro" 'erro'; return }
        $pasta = $r.Pasta
        $itens = @($r.Itens)
        $script:Estado.Emuladores = $itens
        $listaEmu.SuspendLayout(); $listaEmu.Controls.Clear(); $listaEmu.RowCount = 0
        foreach ($e in $itens) {
            $a = New-Object System.Windows.Forms.Label
            $a.AutoSize = $true; $a.Font = $FonteNeg; $a.Margin = New-Object System.Windows.Forms.Padding(0, 8, 10, 4)
            $a.Text = $(if ($e.Encontrado) { '✓' } else { '✗' }) + " $($e.Nome) ($($e.Console))"
            $a.ForeColor = $(if ($e.Encontrado) { $CorOk } else { $CorErro })
            $b = New-Object System.Windows.Forms.Label
            $b.AutoSize = $true; $b.Margin = New-Object System.Windows.Forms.Padding(0, 8, 10, 4); $b.ForeColor = $CorCinza
            $b.MaximumSize = New-Object System.Drawing.Size(330, 0)
            $b.Text = $(if ($e.Encontrado) { $e.Exe } else { 'não encontrado' })
            $listaEmu.Controls.Add($a); $listaEmu.Controls.Add($b)
            if (-not $e.Encontrado) {
                $btn = New-Object System.Windows.Forms.Button
                $btn.Text = 'Abrir página oficial'; $btn.AutoSize = $true; $btn.Tag = $e.Pagina
                $btn.Add_Click({ param($s, $ev) Start-Process ([string]$s.Tag) })
                $listaEmu.Controls.Add($btn)
            } else { $listaEmu.Controls.Add((New-Object System.Windows.Forms.Label)) }
        }
        $listaEmu.ResumeLayout()
        $n = @($itens | Where-Object { $_.Encontrado }).Count
        if (-not (Test-Path -LiteralPath $pasta)) { Mostrar $lblEmu "A pasta $pasta ainda não existe. Crie e extraia os emuladores nela." 'erro' }
        elseif ($n -eq $itens.Count) { Mostrar $lblEmu "Todos os $n emuladores estão aqui ✓" 'ok' }
        else { Mostrar $lblEmu "$n de $($itens.Count) emuladores encontrados. Os que faltam: baixe pela página oficial e extraia na pasta." 'info' }
    }
}
Registrar-Pagina $p2 'Emuladores' { if (-not $script:Estado.Emuladores) { Verificar-Emuladores } }

# ================================================================================================ 3. transferências
$p3 = Nova-Pagina 'Transferir jogos do Deck para o PC' 'Com isto ligado, o PC olha a cada 5 minutos se você pediu algum jogo no Telegram (/transferir → "Enviar pro PC") e copia tudo: jogo, saves e configuração. Nada é apagado no Deck.'
$l3 = Nova-Linha $p3
[void](Novo-Botao $l3 'Ativar' {
    Mostrar $lblTransf 'Ativando…'
    $s = Join-Path $aqui 'transferir-fila.ps1'
    Iniciar-Trabalho 'ativando as transferências' { param($s) Invoke-ScriptPc -Script $s -Argumentos @('-Instalar') -TimeoutS 60 } @($s) {
        param($r, $erro)
        if ($erro) { Mostrar $lblTransf "Erro: $erro" 'erro'; return }
        if ($r.Ok) { Mostrar $lblTransf 'Ativado ✓ O PC vai buscar os pedidos a cada 5 minutos e quando você entrar no Windows.' 'ok' }
        else { Mostrar $lblTransf ('Não consegui ativar: ' + (($r.Erro + ' ' + $r.Saida).Trim())) 'erro' }
    }
})
[void](Novo-Botao $l3 'Ver fila e histórico' { Atualizar-Fila })
$lblTransf = Novo-Resultado $p3
$lvFila = New-Object System.Windows.Forms.ListView
$lvFila.View = 'Details'; $lvFila.FullRowSelect = $true; $lvFila.Width = 600; $lvFila.Height = 150
[void]$lvFila.Columns.Add('Jogo', 270); [void]$lvFila.Columns.Add('Situação', 130); [void]$lvFila.Columns.Add('Pedido em', 100)
$p3.Controls.Add($lvFila)

function Atualizar-Fila {
    if (-not (Exigir-Deck $lblTransf)) { return }
    Iniciar-Trabalho 'lendo a fila do Deck' {
        param($d)
        $h = Invoke-DeckSsh -Deck $d -Comando (New-ComandoRemoto historico)
        [pscustomobject]@{ Ok = $h.Ok; Itens = $(if ($h.Ok) { ConvertFrom-FilaJson $h.Saida } else { @() }); Msg = (Get-MensagemSsh $h) }
    } @((Deck-Atual)) {
        param($r, $erro)
        if ($erro) { Mostrar $lblTransf "Erro: $erro" 'erro'; return }
        if (-not $r.Ok) { Mostrar $lblTransf $r.Msg 'erro'; return }
        $lvFila.Items.Clear()
        $itens = @($r.Itens | Where-Object { $_ })
        [array]::Reverse($itens)
        foreach ($e in $itens) {
            $li = New-Object System.Windows.Forms.ListViewItem([string]$e.Titulo)
            [void]$li.SubItems.Add((Format-StatusFila $e.Status)); [void]$li.SubItems.Add([string]$e.Pedido)
            $li.ToolTipText = [string]$e.Nota
            [void]$lvFila.Items.Add($li)
        }
        $ativos = @($itens | Where-Object { $_.Status -in 'na fila', 'copiando' }).Count
        if (-not $itens.Count) { Mostrar $lblTransf 'Nenhum pedido ainda. Peça um jogo no Telegram com /transferir, ou use "Copiar agora" abaixo.' 'ok' }
        else { Mostrar $lblTransf "$ativos pedido(s) em andamento; mostrando os últimos $($itens.Count)." 'ok' }
    }
}

Novo-Subtitulo $p3 'Copiar um jogo agora' | Out-Null
[void](Novo-Texto $p3 'Escolha um jogo do Deck. A cópia abre numa janela preta, onde dá para acompanhar; pode fechar o assistente.')
$l3b = Nova-Linha $p3
[void](Novo-Botao $l3b 'Carregar jogos do Deck' {
    if (-not (Exigir-Deck $lblCopiar)) { return }
    Iniciar-Trabalho 'lendo os jogos do Deck' {
        param($d)
        $r = Invoke-DeckSsh -Deck $d -Comando (New-ComandoRemoto lista) -TimeoutS 60
        [pscustomobject]@{ Ok = $r.Ok; Jogos = $(if ($r.Ok) { ConvertFrom-ListaJogos $r.Saida } else { @() }); Msg = (Get-MensagemSsh $r) }
    } @((Deck-Atual)) {
        param($r, $erro)
        if ($erro) { Mostrar $lblCopiar "Erro: $erro" 'erro'; return }
        if (-not $r.Ok) { Mostrar $lblCopiar $r.Msg 'erro'; return }
        $script:Estado.Jogos = @($r.Jogos | Where-Object { $_ })
        $cbJogos.Items.Clear()
        foreach ($j in $script:Estado.Jogos) { [void]$cbJogos.Items.Add("$($j.Titulo)  [$($j.Console)]") }
        Mostrar $lblCopiar "$($script:Estado.Jogos.Count) jogos no Deck. Escolha um na lista." 'ok'
    }
})
$cbJogos = New-Object System.Windows.Forms.ComboBox
$cbJogos.DropDownStyle = 'DropDownList'; $cbJogos.Width = 330; $cbJogos.Margin = New-Object System.Windows.Forms.Padding(0, 4, 8, 2)
$l3b.Controls.Add($cbJogos)
[void](Novo-Botao $l3b 'Copiar agora' {
    if ($cbJogos.SelectedIndex -lt 0) { Mostrar $lblCopiar 'Escolha um jogo primeiro (clique em "Carregar jogos do Deck").' 'erro'; return }
    $j = $script:Estado.Jogos[$cbJogos.SelectedIndex]
    $bat = Join-Path $aqui 'transferir-do-deck.bat'
    Start-Process -FilePath $bat -ArgumentList (Join-ArgsWindows @('-Jogo', $j.Id, '-Emuladores', $txtEmu.Text.Trim(), '-SemEmuladorLinux'))
    Mostrar $lblCopiar "Cópia de ""$($j.Titulo)"" começou na janela preta. Os jogos vão para D:\DeckCommander\Jogos." 'ok'
})
$lblCopiar = Novo-Resultado $p3
Registrar-Pagina $p3 'Transferências' $null

# ================================================================================================ 4. jogar o PC no Deck
$p4 = Nova-Pagina 'Jogar os jogos do PC no Deck' 'O PC roda o jogo e manda a imagem para o Deck (aba "Computador"). Precisa do Sunshine no PC e do Moonlight no Deck.'
Novo-Subtitulo $p4 '1) Sunshine' | Out-Null
$lblSun = Novo-Resultado $p4
$l4a = Nova-Linha $p4
$btnSunBaixar = Novo-Botao $l4a 'Abrir página do Sunshine' { Start-Process 'https://github.com/LizardByte/Sunshine/releases' }
[void](Novo-Botao $l4a 'Abrir painel para parear' { Start-Process 'https://localhost:47990' })
[void](Novo-Texto $p4 'Parear: no Deck abra o Moonlight e clique no PC; aparece um PIN. No painel do Sunshine (navegador do PC), vá em PIN e digite esse número. Se o navegador avisar "não seguro", é normal: é o próprio PC.')
Novo-Subtitulo $p4 '2) Biblioteca automática' | Out-Null
$l4b = Nova-Linha $p4
$btnBib = Novo-Botao $l4b 'Ativar biblioteca' {
    Mostrar $lblBib 'O Windows vai pedir permissão (clique Sim)…'
    $s = Join-Path $aqui 'biblioteca-pc.ps1'
    Iniciar-Trabalho 'ativando a biblioteca' { param($s) Invoke-ScriptPc -Script $s -Argumentos @('-Instalar') -TimeoutS 600 } @($s) {
        param($r, $erro)
        if ($erro) { Mostrar $lblBib "Erro: $erro" 'erro'; return }
        $t = Get-TarefasDeckCommander
        if ($t.Biblioteca) { Mostrar $lblBib 'Biblioteca ativada ✓ Os jogos do PC entram no Sunshine sozinhos (todo dia e quando o PC liga).' 'ok' }
        else { Mostrar $lblBib 'Não ativou (a permissão foi negada?). Clique de novo e escolha Sim.' 'erro' }
    }
}
[void](Novo-Botao $l4b 'Ver jogos achados' {
    $s = Join-Path $aqui 'biblioteca-pc.ps1'
    Iniciar-Trabalho 'procurando jogos no PC' {
        param($s)
        $r = Invoke-ScriptPc -Script $s -Argumentos @('-Simular') -TimeoutS 180
        [pscustomobject]@{ Ok = $r.Ok; Jogos = (ConvertFrom-SaidaBiblioteca $r.Saida); Erro = $r.Erro }
    } @($s) {
        param($r, $erro)
        if ($erro) { Mostrar $lblBib "Erro: $erro" 'erro'; return }
        $lstBib.Items.Clear()
        foreach ($j in @($r.Jogos | Where-Object { $_ })) { [void]$lstBib.Items.Add("$($j.Nome)   ($($j.Loja))") }
        if ($lstBib.Items.Count) { Mostrar $lblBib "$($lstBib.Items.Count) jogos achados no PC." 'ok' }
        else { Mostrar $lblBib ('Nenhum jogo achado. ' + $r.Erro) 'erro' }
    }
})
$lblBib = Novo-Resultado $p4
$lstBib = New-Object System.Windows.Forms.ListBox
$lstBib.Width = 600; $lstBib.Height = 90
$p4.Controls.Add($lstBib)

Novo-Subtitulo $p4 '3) Dizer ao Deck onde está este PC' | Out-Null
[void](Novo-Texto $p4 'Detectado automaticamente da placa de rede que está em uso. Corrija se precisar.')
$grade = New-Object System.Windows.Forms.TableLayoutPanel
$grade.AutoSize = $true; $grade.ColumnCount = 2
$p4.Controls.Add($grade)
$campos = [ordered]@{}
foreach ($par in @(@('host_casa', 'IP do PC em casa'), @('rede_casa', 'Rede de casa (começo do IP)'), @('mac', 'MAC (para acordar o PC)'), @('host_tailscale', 'IP Tailscale (fora de casa)'))) {
    $r = New-Object System.Windows.Forms.Label
    $r.Text = $par[1]; $r.AutoSize = $true; $r.Margin = New-Object System.Windows.Forms.Padding(0, 8, 12, 2)
    $c = New-Object System.Windows.Forms.TextBox
    $c.Width = 220
    $grade.Controls.Add($r); $grade.Controls.Add($c)
    $campos[$par[0]] = $c
}
$lblRede = Novo-Texto $p4 ''
$lblRede.ForeColor = $CorCinza
$l4c = Nova-Linha $p4
[void](Novo-Botao $l4c 'Gravar no Deck' {
    if (-not (Exigir-Deck $lblPc)) { return }
    $cfg = [ordered]@{}
    foreach ($k in $campos.Keys) { $cfg[$k] = $campos[$k].Text.Trim() }
    try { $cmd = New-ComandoConfigPc -Config $cfg } catch { Mostrar $lblPc $_.Exception.Message 'erro'; return }
    Iniciar-Trabalho 'gravando no Deck' { param($d, $c) $r = Invoke-DeckSsh -Deck $d -Comando $c; [pscustomobject]@{ Ok = $r.Ok; Msg = (Get-MensagemSsh $r) } } @((Deck-Atual), $cmd) {
        param($r, $erro)
        if ($erro) { Mostrar $lblPc "Erro: $erro" 'erro'; return }
        if ($r.Ok) { $script:Estado.ConfigPcGravada = $true; Mostrar $lblPc 'Gravado no Deck ✓' 'ok' } else { Mostrar $lblPc $r.Msg 'erro' }
    }
})
[void](Novo-Botao $l4c 'Testar' {
    if (-not (Exigir-Deck $lblPc)) { return }
    Iniciar-Trabalho 'perguntando ao Deck' { param($d) Invoke-DeckSsh -Deck $d -Comando (New-ComandoRemoto pcstatus) -TimeoutS 90 } @((Deck-Atual)) {
        param($r, $erro)
        if ($erro) { Mostrar $lblPc "Erro: $erro" 'erro'; return }
        $txtPc.Text = (([string]$r.Saida).Trim() -replace "(?<!`r)`n", "`r`n")
        if ($r.Ok) { Mostrar $lblPc 'O Deck respondeu (veja abaixo).' 'ok' } else { Mostrar $lblPc (Get-MensagemSsh $r) 'erro' }
    }
})
$lblPc = Novo-Resultado $p4
$txtPc = New-Object System.Windows.Forms.TextBox
$txtPc.Multiline = $true; $txtPc.ReadOnly = $true; $txtPc.Width = 600; $txtPc.Height = 100; $txtPc.ScrollBars = 'Vertical'; $txtPc.BackColor = $CorFundo
$p4.Controls.Add($txtPc)
[void](Novo-Texto $p4 'Para o PC acordar e dormir sozinho, veja a Parte 5.5 do tutorial (Wake-on-LAN na BIOS e suspensão do Windows).')

Registrar-Pagina $p4 'Jogar o PC no Deck' {
    Iniciar-Trabalho 'olhando Sunshine e rede' {
        [pscustomobject]@{ Sun = Get-SunshineEstado; Rede = Get-RedeAtiva; Ts = Get-IpTailscale; Tar = Get-TarefasDeckCommander }
    } @() {
        param($r, $erro)
        if ($erro) { Mostrar $lblSun "Erro: $erro" 'erro'; return }
        if ($r.Sun.Instalado) {
            Mostrar $lblSun $(if ($r.Sun.Rodando) { 'Sunshine instalado e rodando ✓' } else { 'Sunshine instalado, mas parado. Reinicie o PC ou abra o Sunshine.' }) $(if ($r.Sun.Rodando) { 'ok' } else { 'erro' })
            $btnSunBaixar.Visible = $false; $btnBib.Enabled = $true
        } else {
            Mostrar $lblSun 'Sunshine não está instalado. Baixe o instalador .exe do Windows na página oficial e instale.' 'erro'
            $btnBib.Enabled = $false
        }
        if ($r.Tar.Biblioteca -and -not $lblBib.Text) { Mostrar $lblBib 'Biblioteca automática já está ativa ✓' 'ok' }
        if ($r.Rede) {
            if (-not $campos['host_casa'].Text) { $campos['host_casa'].Text = $r.Rede.Ip }
            if (-not $campos['rede_casa'].Text) { $campos['rede_casa'].Text = $r.Rede.RedeCasa }
            if (-not $campos['mac'].Text) { $campos['mac'].Text = $r.Rede.Mac }
            $lblRede.Text = "Placa em uso: $($r.Rede.Adaptador) ($($r.Rede.Descricao))."
        } else { $lblRede.Text = 'Não consegui detectar a rede; preencha à mão (no PC, ipconfig /all mostra o IP e o "Endereço Físico").' }
        if ($r.Ts -and -not $campos['host_tailscale'].Text) { $campos['host_tailscale'].Text = $r.Ts }
    }
}

# ================================================================================================ 5. IA do PC
$p5 = Nova-Pagina 'IA do PC (opcional)' 'Se este PC tem o Ollama, a tradução dos jogos no Deck pode usar a placa de vídeo do PC (bem mais rápida). O PC abre um "túnel" seguro até o Deck; nada fica aberto na rede.'
$lblOllama = Novo-Resultado $p5
$l5 = Nova-Linha $p5
$btnOllamaSite = Novo-Botao $l5 'Abrir site do Ollama' { Start-Process 'https://ollama.com' }
$btnTunel = Novo-Botao $l5 'Ligar a IA do PC ao Deck' {
    if (-not (Exigir-Deck $lblTunel)) { return }
    $s = Join-Path $aqui 'instalar-tunel-ia.ps1'
    Iniciar-Trabalho 'ligando a IA ao Deck' { param($s, $d) Invoke-ScriptPc -Script $s -Argumentos @('-Deck', $d) -TimeoutS 60 } @($s, (Deck-Atual)) {
        param($r, $erro)
        if ($erro) { Mostrar $lblTunel "Erro: $erro" 'erro'; return }
        if ($r.Ok) { Mostrar $lblTunel 'Ligado ✓ A IA do PC fica disponível para o Deck sempre que o PC estiver ligado.' 'ok' }
        else { Mostrar $lblTunel ('Não consegui ligar: ' + (($r.Erro + ' ' + $r.Saida).Trim())) 'erro' }
    }
}
[void](Novo-Texto $p5 'Depois de instalar o Ollama, baixe o modelo uma vez (PowerShell): ollama pull qwen2.5:7b')
$lblTunel = Novo-Resultado $p5
Registrar-Pagina $p5 'IA do PC' {
    Iniciar-Trabalho 'procurando o Ollama' { [pscustomobject]@{ O = Get-OllamaEstado; T = Get-TarefasDeckCommander } } @() {
        param($r, $erro)
        if ($erro) { Mostrar $lblOllama "Erro: $erro" 'erro'; return }
        if ($r.O.Instalado) {
            Mostrar $lblOllama $(if ($r.O.Rodando) { 'Ollama instalado e rodando ✓' } else { 'Ollama instalado (abra o Ollama para ele rodar).' }) 'ok'
            $btnOllamaSite.Visible = $false; $btnTunel.Enabled = $true
        } else { Mostrar $lblOllama 'Ollama não está instalado neste PC. É opcional.' 'info'; $btnTunel.Enabled = $false }
        if ($r.T.IA -and -not $lblTunel.Text) { Mostrar $lblTunel 'A IA do PC já está ligada ao Deck ✓' 'ok' }
    }
}

# ================================================================================================ 6. resumo
$p6 = Nova-Pagina 'Resumo' 'O que ficou pronto neste PC:'
$txtResumo = New-Object System.Windows.Forms.Label
$txtResumo.AutoSize = $true; $txtResumo.Font = New-Object System.Drawing.Font('Segoe UI', 11)
$txtResumo.MaximumSize = New-Object System.Drawing.Size(600, 0)
$p6.Controls.Add($txtResumo)
[void](Novo-Texto $p6 'Pode abrir o assistente de novo a qualquer hora para conferir ou mudar algo. Teste final: no Telegram, /diagnostico e /pc status.')
Registrar-Pagina $p6 'Resumo' {
    $txtResumo.Text = 'Conferindo…'
    $deck = Deck-Atual
    $pasta = $txtEmu.Text.Trim()
    Iniciar-Trabalho 'montando o resumo' {
        param($d, $pasta)
        [pscustomobject]@{
            Deck = $d; Pasta = $pasta
            Conn = $(if ($d) { Test-ConexaoDeck -Deck $d } else { $null })
            Emu  = @(Get-EmuladoresNaPasta -Pasta $pasta)
            Tar  = Get-TarefasDeckCommander
            Sun  = Get-SunshineEstado
            Oll  = Get-OllamaEstado
        }
    } @($deck, $pasta) {
        param($r, $erro)
        if ($erro) { $txtResumo.Text = "Erro: $erro"; return }
        $deck = $r.Deck; $pasta = $r.Pasta
        $s = { param($b) if ($b) { '✓' } else { '✗' } }
        $n = @($r.Emu | Where-Object { $_.Encontrado }).Count
        $linhas = @(
            "$(& $s ($r.Conn -and $r.Conn.Conectou))  Ligado ao Deck" + $(if ($deck) { " ($deck)" } else { ' (não configurado)' })
            "$(& $s ($n -eq @($r.Emu).Count))  Emuladores: $n de $(@($r.Emu).Count) em $pasta"
            "$(& $s $r.Tar.Transferencias)  Transferências automáticas (Deck → PC)"
            "$(& $s $r.Sun.Instalado)  Sunshine instalado" + $(if ($r.Sun.Instalado -and -not $r.Sun.Rodando) { ' (parado)' } else { '' })
            "$(& $s $r.Tar.Biblioteca)  Biblioteca automática de jogos do PC"
            "$(& $s $script:Estado.ConfigPcGravada)  Endereço do PC gravado no Deck (nesta sessão)"
            "$(& $s $r.Tar.IA)  IA do PC ligada ao Deck (opcional)" + $(if (-not $r.Oll.Instalado) { ' – sem Ollama' } else { '' })
        )
        $txtResumo.Text = ($linhas -join "`r`n`r`n")
    }
}

# ------------------------------------------------------------------------------------------------ rodar
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 150
$timer.Add_Tick({ Verificar-Trabalhos })
$timer.Start()
$form.Add_FormClosing({ $timer.Stop() })
Ir-Para 0
[void]$form.ShowDialog()
foreach ($t in @($script:Trabalhos)) { try { $t.Ps.Stop(); $t.Ps.Dispose() } catch { } }
