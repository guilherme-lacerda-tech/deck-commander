# Testes do Assistente do PC (só as funções; a janela não é aberta). Pester 3.4/4.x:
#     Invoke-Pester tools\pc\assistente.Tests.ps1
Import-Module (Join-Path $PSScriptRoot 'assistente-funcoes.psm1') -Force -DisableNameChecking

Describe 'Sintaxe' {
    foreach ($f in 'assistente.ps1', 'assistente-funcoes.psm1') {
        It "$f não tem erro de sintaxe e tem BOM (acentos no PowerShell 5.1)" {
            $tok = $null; $err = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $f), [ref]$tok, [ref]$err)
            $err.Count | Should Be 0
            $b = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $f))
            ($b[0..2] -join ',') | Should Be '239,187,191'
        }
    }
}

Describe 'Endereço do Deck' {
    It 'IP vira deck@IP' { ConvertTo-DeckEndereco ' 192.168.0.50 ' | Should Be 'deck@192.168.0.50' }
    It 'mantém usuário@host' { ConvertTo-DeckEndereco 'deck@steamdeck' | Should Be 'deck@steamdeck' }
    It 'recusa lixo e injeção' {
        ConvertTo-DeckEndereco '' | Should BeNullOrEmpty
        ConvertTo-DeckEndereco '1.2.3.4; rm -rf ~' | Should BeNullOrEmpty
        ConvertTo-DeckEndereco 'a b@c' | Should BeNullOrEmpty
    }
    It 'host do endereço' { Get-HostDoEndereco 'deck@10.0.0.7' | Should Be '10.0.0.7' }
    It 'grava e lê deck.txt' {
        $arq = Join-Path $TestDrive 'cfg\deck.txt'
        Save-DeckEndereco -Deck '192.168.1.9' -Arquivo $arq | Should Be 'deck@192.168.1.9'
        Read-DeckSalvo -Arquivo $arq | Should Be 'deck@192.168.1.9'
        Read-DeckSalvo -Arquivo (Join-Path $TestDrive 'nao-existe.txt') | Should BeNullOrEmpty
    }
}

Describe 'Linha de comando' {
    It 'sem aspas quando não precisa' { Join-ArgsWindows @('-i', 'C:\x\chave') | Should Be '-i C:\x\chave' }
    It 'aspas em espaço e vazio' { Join-ArgsWindows @('-N', '', 'C:\Meus Docs\a') | Should Be '-N "" "C:\Meus Docs\a"' }
    It 'escapa aspas e barras finais' { Join-ArgsWindows @('a "b"', 'C:\pasta com espaco\') | Should Be '"a \"b\"" "C:\pasta com espaco\\"' }
    It 'args do ssh usam a chave, BatchMode e o Deck por último' {
        $a = Get-SshArgs -Deck 'deck@1.2.3.4' -Chave 'C:\k'
        $a[0] | Should Be '-i'; $a[1] | Should Be 'C:\k'
        ($a -contains 'BatchMode=yes') | Should Be $true
        $a[-1] | Should Be 'deck@1.2.3.4'
    }
    It 'comandos remotos sem aspas duplas (o PowerShell 5.1 as estraga)' {
        foreach ($c in 'teste', 'fila', 'historico', 'lista', 'pcstatus') { (New-ComandoRemoto $c) | Should Not Match '"' }
        (New-ComandoAutorizarChave) | Should Not Match '"'
    }
    It 'fila e lista chamam o dc.transferir' {
        New-ComandoRemoto fila | Should Be 'cd ~/deck-commander && python3 -m dc.transferir fila-json'
        New-ComandoRemoto lista | Should Be 'cd ~/deck-commander && python3 -m dc.transferir lista'
        New-ComandoRemoto pcstatus | Should Be 'cd ~/deck-commander && python3 -m dc x pc status'
    }
}

Describe 'Config do PC no Deck' {
    It 'monta um config por valor preenchido, na ordem' {
        $c = New-ComandoConfigPc -Config ([ordered]@{ host_casa = '192.168.0.20'; rede_casa = '192.168.0.'; mac = 'AA-BB-CC-DD-EE-FF'; host_tailscale = '' })
        $c | Should Be "cd ~/deck-commander && python3 -m dc x pc config host_casa '192.168.0.20' && python3 -m dc x pc config rede_casa '192.168.0.' && python3 -m dc x pc config mac 'AA-BB-CC-DD-EE-FF'"
    }
    It 'recusa valor perigoso' { { New-ComandoConfigPc -Config @{ host_casa = "1.2.3.4'; rm -rf ~" } } | Should Throw }
    It 'recusa chave desconhecida' { { New-ComandoConfigPc -Config @{ codigo = 'x' } } | Should Throw }
    It 'recusa tudo vazio' { { New-ComandoConfigPc -Config @{ host_casa = ' ' } } | Should Throw }
}

Describe 'Janela da senha' {
    It 'script da autorização é PowerShell válido e não contém senha' {
        $s = New-ScriptAutorizacao -Deck 'deck@1.2.3.4' -ChavePub "C:\Users\O'Brien\.ssh\k.pub"
        $tok = $null; $err = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($s, [ref]$tok, [ref]$err)
        $err.Count | Should Be 0
        $s | Should Match "O''Brien"
        $s | Should Match 'deck@1.2.3.4'
        $s | Should Not Match 'password\s*='
    }
    It 'codificado volta igual' {
        $b = ConvertTo-ComandoCodificado 'Write-Host olá'
        [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($b)) | Should Be 'Write-Host olá'
    }
}

Describe 'Emuladores numa pasta' {
    It 'acha os que existem (inclusive em subpasta) e marca os que faltam' {
        $e = Join-Path $TestDrive 'Emus'
        New-Item -ItemType Directory -Force "$e\Ryujinx\publish", "$e\PCSX2", "$e\Lichii" | Out-Null
        Set-Content "$e\Ryujinx\publish\Ryujinx.exe" 'x'
        Set-Content "$e\PCSX2\pcsx2-qt.exe" 'x'
        Set-Content "$e\PCSX2\updater.exe" 'x'
        Set-Content "$e\Lichii\eden-cli.exe" 'x'
        $r = Get-EmuladoresNaPasta -Pasta $e
        @($r).Count | Should Be 6
        ($r | Where-Object Nome -eq 'Ryujinx').Exe | Should Be "$e\Ryujinx\publish\Ryujinx.exe"
        ($r | Where-Object Nome -eq 'PCSX2').Exe | Should Be "$e\PCSX2\pcsx2-qt.exe"
        ($r | Where-Object Nome -eq 'Lichii').Encontrado | Should Be $false   # eden-cli.exe não é o emulador
        ($r | Where-Object Nome -eq 'Xenia').Encontrado | Should Be $false
        ($r | Where-Object Nome -eq 'Xenia').Pagina | Should Match '^https://'
    }
    It 'pasta inexistente: nada encontrado, sem erro' {
        @(Get-EmuladoresNaPasta -Pasta (Join-Path $TestDrive 'nada') | Where-Object Encontrado).Count | Should Be 0
    }
}

Describe 'Rede' {
    It 'rede de casa pelo prefixo' {
        ConvertTo-RedeCasa -Ip '192.168.0.20' -Prefixo 24 | Should Be '192.168.0.'
        ConvertTo-RedeCasa -Ip '10.1.2.3' -Prefixo 16 | Should Be '10.1.'
        ConvertTo-RedeCasa -Ip '10.1.2.3' -Prefixo 8 | Should Be '10.'
    }
    It 'escolhe a placa física da rota de menor métrica, pulando VPN e placa desligada' {
        $rotas = @(
            [pscustomobject]@{ ifIndex = 5; RouteMetric = 0; InterfaceMetric = 5; NextHop = '100.100.100.100' }    # Tailscale
            [pscustomobject]@{ ifIndex = 9; RouteMetric = 0; InterfaceMetric = 1; NextHop = '192.168.9.1' }        # desligada
            [pscustomobject]@{ ifIndex = 12; RouteMetric = 0; InterfaceMetric = 35; NextHop = '192.168.0.1' }      # Wi-Fi
        )
        $end = @(
            [pscustomobject]@{ ifIndex = 5; IPAddress = '100.64.1.2'; PrefixLength = 32 }
            [pscustomobject]@{ ifIndex = 12; IPAddress = '169.254.3.3'; PrefixLength = 16 }
            [pscustomobject]@{ ifIndex = 12; IPAddress = '192.168.0.20'; PrefixLength = 24 }
        )
        $ads = @(
            [pscustomobject]@{ ifIndex = 5; Name = 'Tailscale'; InterfaceDescription = 'Tailscale Tunnel'; Status = 'Up'; MacAddress = '' }
            [pscustomobject]@{ ifIndex = 9; Name = 'Ethernet'; InterfaceDescription = 'Realtek'; Status = 'Disconnected'; MacAddress = '11-11-11-11-11-11' }
            [pscustomobject]@{ ifIndex = 12; Name = 'Wi-Fi'; InterfaceDescription = 'Intel Wi-Fi 6'; Status = 'Up'; MacAddress = 'aa-bb-cc-dd-ee-ff' }
        )
        $r = Select-RedeAtiva -Rotas $rotas -Enderecos $end -Adaptadores $ads
        $r.Adaptador | Should Be 'Wi-Fi'
        $r.Ip | Should Be '192.168.0.20'
        $r.RedeCasa | Should Be '192.168.0.'
        $r.Mac | Should Be 'AA-BB-CC-DD-EE-FF'
        $r.Gateway | Should Be '192.168.0.1'
    }
    It 'sem rota: nada' { Select-RedeAtiva -Rotas @() -Enderecos @() -Adaptadores @() | Should BeNullOrEmpty }
    It 'vizinhos da /24 sem o próprio IP' {
        $v = @(Get-IpsDaSubrede '192.168.0.20')
        $v.Count | Should Be 253
        ($v -contains '192.168.0.20') | Should Be $false
        $v[0] | Should Be '192.168.0.1'; $v[-1] | Should Be '192.168.0.254'
    }
}

Describe 'Respostas do Deck' {
    It 'fila vazia' { @(ConvertFrom-FilaJson '[]').Count | Should Be 0; @(ConvertFrom-FilaJson '').Count | Should Be 0 }
    It 'fila com pedido' {
        $j = '[{"id":"ps2-x-1","game_id":"ps2-x","titulo":"Ragnarök","status":"pronto","pedido":"2026-11-10T12:00:00+00:00","nota":"linha 1\nfim ok\n"}]'
        $r = @(ConvertFrom-FilaJson $j)
        $r.Count | Should Be 1
        $r[0].Titulo | Should Be 'Ragnarök'
        $r[0].Nota | Should Be 'fim ok'
        $r[0].Pedido | Should Match '^\d\d/11 \d\d:\d\d$'
    }
    It 'lista de jogos (TSV)' {
        $r = @(ConvertFrom-ListaJogos "pc-2xko`t2XKO`tpc`nps2-black`tBlack (BR)`tps2`n`n")
        $r.Count | Should Be 2
        $r[1].Id | Should Be 'ps2-black'; $r[1].Titulo | Should Be 'Black (BR)'; $r[1].Console | Should Be 'ps2'
    }
    It 'jogos da biblioteca (-Simular)' {
        $t = "Jogos encontrados no PC: 2`n  [Riot] 2XKO`n      lancar: x`n  [Steam] Cyberpunk 2077`n      pasta: y"
        $r = @(ConvertFrom-SaidaBiblioteca $t)
        $r.Count | Should Be 2
        $r[1].Loja | Should Be 'Steam'; $r[1].Nome | Should Be 'Cyberpunk 2077'
    }
    It 'status em palavras simples' { Format-StatusFila 'na fila' | Should Be 'Esperando o PC' }
    It 'erros do ssh em palavras simples' {
        Get-MensagemSsh ([pscustomobject]@{ Ok = $false; Codigo = 255; Erro = 'ssh: connect to host 1.2.3.4 port 22: Connection timed out'; Saida = ''; Estourou = $false }) | Should Match 'ligado, na mesma rede'
        Get-MensagemSsh ([pscustomobject]@{ Ok = $false; Codigo = 255; Erro = 'deck@1.2.3.4: Permission denied (publickey,password).'; Saida = ''; Estourou = $false }) | Should Match 'recusou a chave'
        Get-MensagemSsh ([pscustomobject]@{ Ok = $false; Codigo = 1; Erro = ''; Saida = ''; Estourou = $true }) | Should Match 'demorou'
    }
}
