# Testes da transferência nos dois sentidos (só funções; sem rede e sem Deck). Pester 3.4/4.x:
#     Invoke-Pester tools\pc\transferencia.Tests.ps1
Import-Module (Join-Path $PSScriptRoot 'transferencia-funcoes.psm1') -Force -DisableNameChecking
$Tab = Get-TabelaEmuladores

function Novo-Arq([string]$p, $conteudo = 'x') {
    New-Item -ItemType Directory -Force (Split-Path $p) | Out-Null
    if ($conteudo -is [byte[]]) { [IO.File]::WriteAllBytes($p, $conteudo) } else { [IO.File]::WriteAllText($p, $conteudo, (New-Object Text.UTF8Encoding $false)) }
    return $p
}

Describe 'Sintaxe' {
    foreach ($f in 'transferencia-funcoes.psm1', 'enviar-para-deck.ps1', 'emulador-oficial.ps1', 'transferir-do-deck.ps1', 'transferir-fila.ps1') {
        It "$f não tem erro de sintaxe e tem BOM (acentos no PowerShell 5.1)" {
            $tok = $null; $err = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $f), [ref]$tok, [ref]$err)
            $err.Count | Should Be 0
            $b = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $f))
            ($b[0..2] -join ',') | Should Be '239,187,191'
        }
    }
}

Describe 'Tabela oficial' {
    It 'cobre os 14 emuladores com origem Windows e Linux' {
        foreach ($e in 'lichii', 'ryujinx', 'pcsx2', 'duckstation', 'ppsspp', 'xenia', 'retroarch', 'dolphin', 'cemu', 'rpcs3', 'azahar', 'melonds', 'xemu', 'flycast') {
            $Tab.ContainsKey($e) | Should Be $true
            $Tab[$e].pagina | Should Match '^https://'
        }
    }
    It 'console -> emulador' {
        Get-EmuDoConsole 'switch2' $Tab | Should Be 'lichii'
        Get-EmuDoConsole 'psx' $Tab | Should Be 'duckstation'
        Get-EmuDoConsole 'snes' $Tab | Should Be 'retroarch'
        Get-EmuDoConsole 'nada' $Tab | Should BeNullOrEmpty
    }
}

Describe 'Ids e formatos' {
    It 'slug sem acento' { ConvertTo-Slug 'Pokémon: Edição [SLUS-00529]' | Should Be 'pokemon-edicao-slus-00529' }
    It 'title id do main.npdm' {
        $b = New-Object byte[] 0x200
        [Text.Encoding]::ASCII.GetBytes('META').CopyTo($b, 0)
        [BitConverter]::GetBytes([uint32]0x100).CopyTo($b, 0x70)
        [Text.Encoding]::ASCII.GetBytes('ACI0').CopyTo($b, 0x100)
        [BitConverter]::GetBytes([uint64]0x040074A01BF12000).CopyTo($b, 0x110)
        Get-TidNpdm (Novo-Arq "$TestDrive\npdm\main.npdm" $b) | Should Be '040074A01BF12000'
        Get-TidNpdm (Novo-Arq "$TestDrive\npdm\ruim.npdm" 'nada') | Should BeNullOrEmpty
    }
    It 'índice de saves do Ryujinx (imkvdb.arc)' {
        $ms = New-Object IO.MemoryStream; $w = New-Object IO.BinaryWriter($ms)
        $w.Write([Text.Encoding]::ASCII.GetBytes('IMKV')); $w.Write([uint32]0); $w.Write([uint32]1)
        $w.Write([Text.Encoding]::ASCII.GetBytes('IMEN')); $w.Write([uint32]0x40); $w.Write([uint32]0x40)
        $k = New-Object byte[] 0x40; [BitConverter]::GetBytes([uint64]0x0100F43008C44000).CopyTo($k, 0); $k[0x20] = 1; $w.Write($k)
        $v = New-Object byte[] 0x40; [BitConverter]::GetBytes([uint64]4).CopyTo($v, 0); $w.Write($v); $w.Flush()
        $e = @(Read-Imkvdb (Novo-Arq "$TestDrive\ryu\imkvdb.arc" $ms.ToArray()))
        $e.Count | Should Be 1
        $e[0].SaveDataId | Should Be '0000000000000004'
        $e[0].ProgramId | Should Be ([uint64]0x0100F43008C44000)
    }
    It 'serial do PS1 pelo nome ou pelo SYSTEM.CNF' {
        Get-SerialDisco '[SLUS-00529] Hercules' @() | Should Be 'SLUS-00529'
        $bin = Novo-Arq "$TestDrive\ps\j.bin" ("lixo BOOT = cdrom:\SCUS_941.63;1 lixo")
        Get-SerialDisco 'Jogo' @($bin) | Should Be 'SCUS-94163'
    }
    It 'arquivos citados pelo .cue' {
        $cue = Novo-Arq "$TestDrive\cue\j.cue" "FILE `"j (Track 1).bin`" BINARY`n  TRACK 01 MODE2/2352`n"
        @(Get-RefsDisco $cue)[0] | Should Be "$TestDrive\cue\j (Track 1).bin"
    }
}

Describe 'Emulador do PC' {
    It 'acha portátil e a versão registrada; ausente = $null' {
        $E = "$TestDrive\Emus"
        Novo-Arq "$E\Lichii\lichii.exe" | Out-Null
        Novo-Arq "$E\Ryujinx\publish\Ryujinx.exe" | Out-Null
        Novo-Arq "$E\_downloads\downloads.json" '[{"nome":"Lichii","url":"https://github.com/zortos293/Lichii/releases/download/build-83/l.zip"}]' | Out-Null
        $x = Find-EmuladorPC 'lichii' $E $Tab
        $x.Dados | Should Be "$E\Lichii\user"
        $x.Versao | Should Be 'build-83'
        (Find-EmuladorPC 'ryujinx' $E $Tab).Dados | Should Be "$E\Ryujinx\publish\portable"
        Find-EmuladorPC 'pcsx2' $E $Tab | Should BeNullOrEmpty
        @((Get-EmuladoresPC $E $Tab).Keys) -join ',' | Should Be 'lichii,ryujinx'
    }
}

Describe 'Versão oficial (API simulada)' {
    $rel = [pscustomobject]@{ tag_name = 'build-83'; assets = @(
        [pscustomobject]@{ name = 'lichii-linux-x86_64-pgo.AppImage'; browser_download_url = 'https://x/a'; size = 10; digest = ('sha256:' + ('ab' * 32)) },
        [pscustomobject]@{ name = 'lichii-windows-x86_64-pgo.zip'; browser_download_url = 'https://x/w.zip'; size = 5; digest = ('sha256:' + ('cd' * 32)) }) }
    $get = { param($u) if ($u -match 'releases\?per_page') { return ,@($rel) } ; if ($u -match '/tags/build-1$') { throw '404' }; return $rel }.GetNewClosure()
    It 'acha a mesma build pelo sha256 do AppImage do Deck' {
        Find-VersaoPorDigest $Tab['lichii'].fonte ('AB' * 32) -Linux -Get $get | Should Be 'build-83'
        Find-VersaoPorDigest $Tab['lichii'].fonte ('00' * 32) -Linux -Get $get | Should BeNullOrEmpty
    }
    It 'plano Windows: arquivo, sha256 publicado e pasta portátil' {
        $p = Get-PlanoEmuladorPC -Emu 'lichii' -Sha256Linux ('ab' * 32) -Tab $Tab -Emuladores 'X:\Emus' -Get $get
        $p.Acao | Should Be 'baixar'
        $p.Versao | Should Be 'build-83'
        $p.Mesma | Should Be $true
        $p.Arquivo | Should Be 'lichii-windows-x86_64-pgo.zip'
        $p.Sha256 | Should Be ('cd' * 32)
        $p.Pasta | Should Be 'X:\Emus\Lichii'
        Format-PlanoEmulador $p | Should Match 'vai ser instalado no PC .*build-83.*mesma versão do Deck.*página oficial'
    }
    It 'versão que sumiu cai na mais recente; Dolphin é manual' {
        (Get-PlanoEmuladorPC -Emu 'lichii' -Versao 'build-1' -Tab $Tab -Emuladores 'X:\E' -Get $get).Mesma | Should Be $false
        (Get-PlanoEmuladorPC -Emu 'dolphin' -Tab $Tab -Emuladores 'X:\E' -Get $get).Acao | Should Be 'manual'
        (Get-PlanoEmuladorPC -Emu 'nada' -Tab $Tab -Emuladores 'X:\E' -Get $get).Acao | Should Be 'nenhum'
    }
    It 'RetroArch usa a URL oficial do buildbot com a versão da release' {
        $g2 = { param($u) [pscustomobject]@{ tag_name = 'v1.22.2'; assets = @() } }
        (Get-PlanoEmuladorPC -Emu 'retroarch' -Tab $Tab -Emuladores 'X:\E' -Get $g2).Url | Should Be 'https://buildbot.libretro.com/stable/1.22.2/windows/x86_64/RetroArch.7z'
    }
    It 'simulação não baixa nem cria pasta' {
        $p = Get-PlanoEmuladorPC -Emu 'lichii' -Tab $Tab -Emuladores "$TestDrive\Sim" -Get $get
        Install-EmuladorPC -Plano $p -Emuladores "$TestDrive\Sim" -Tab $Tab -Simular | Should Match '^\[simulação\]'
        Test-Path "$TestDrive\Sim" | Should Be $false
    }
    It 'não sobrescreve pasta de emulador que já existe' {
        Novo-Arq "$TestDrive\Ocupado\Lichii\outro.txt" | Out-Null
        $p = Get-PlanoEmuladorPC -Emu 'lichii' -Tab $Tab -Emuladores "$TestDrive\Ocupado" -Get $get
        { Install-EmuladorPC -Plano $p -Emuladores "$TestDrive\Ocupado" -Tab $Tab } | Should Throw
    }
}

Describe 'Jogos do PC e manifesto' {
    $J = "$TestDrive\Jogos"; $E = "$TestDrive\E"
    Novo-Arq "$J\psx\Hercules [SLUS-00529]\Hercules.cue" "FILE `"Hercules.bin`" BINARY`n" | Out-Null
    Novo-Arq "$J\psx\Hercules [SLUS-00529]\Hercules.bin" 'dados do disco' | Out-Null
    Novo-Arq "$J\switch2\Jogo X\base\exefs\main" 'm' | Out-Null
    Novo-Arq "$J\switch2\Jogo X\updates\romfs\a" 'u' | Out-Null
    Novo-Arq "$E\DuckStation\duckstation-qt-x64-ReleaseLTCG.exe" | Out-Null
    Novo-Arq "$E\DuckStation\settings.ini" "[BIOS]`nSearchDirectory = D:/Emuladores/DuckStation/bios`n[GameList]`nRecursivePaths = $("$TestDrive".Replace('\','/'))/Roms`n" | Out-Null
    Novo-Arq "$E\DuckStation\memcards\Hercules [SLUS-00529]_1.mcd" 'save' | Out-Null
    Novo-Arq "$E\DuckStation\memcards\Outro Jogo_1.mcd" 'save de outro' | Out-Null
    Novo-Arq "$E\DuckStation\bios\scph1001.bin" ([byte[]](New-Object byte[] 524288)) | Out-Null
    Novo-Arq "$TestDrive\Roms\Spyro.cue" "FILE `"Spyro.bin`" BINARY`n" | Out-Null
    Novo-Arq "$TestDrive\Roms\Spyro.bin" 'spyro' | Out-Null
    $jogos = @(Get-JogosPC -Jogos $J -Emuladores $E -Tab $Tab)

    It 'lista jogos da pasta Jogos e da pasta de ROM do emulador (sem o .bin citado pelo .cue)' {
        ($jogos | ForEach-Object { $_.Id }) -join ',' | Should Be 'psx-hercules-slus-00529,switch2-jogo-x,psx-spyro'
        ($jogos | Where-Object { $_.Id -eq 'psx-spyro' }).Origem | Should Be 'emulador'
    }
    It 'manifesto: jogo + dados do DuckStation do jogo (não leva save de outro jogo), com sha256' {
        $m = Get-ManifestoPC ($jogos[0]) $Tab $E $J -ComHash
        $m.emulador | Should Be 'duckstation'
        $m.serial | Should Be 'SLUS-00529'
        $d = @($m.arquivos | ForEach-Object { $_.destino })
        $d -contains '{JOGOS}/psx/Hercules [SLUS-00529]/Hercules.bin' | Should Be $true
        $d -contains '{EMU}/memcards/Hercules [SLUS-00529]_1.mcd' | Should Be $true
        $d -contains '{EMU}/memcards/Outro Jogo_1.mcd' | Should Be $false
        $d -contains '{EMU}/bios/scph1001.bin' | Should Be $true
        $bin = $m.arquivos | Where-Object { $_.destino -like '*Hercules.bin' }
        $bin.rel | Should Be 'JOGOS/psx/Hercules [SLUS-00529]/Hercules.bin'
        $bin.sha256 | Should Be ((Get-FileHash -Algorithm SHA256 -LiteralPath "$J\psx\Hercules [SLUS-00529]\Hercules.bin").Hash.ToLower())
        ($m.arquivos | Where-Object { $_.destino -eq '{EMU}/settings.ini' }).reescrever | Should Be $true
        $m.reescrever[0].para | Should Be '{EMU}'
        $m.direcao | Should Be 'pc->deck'
    }
    It 'Switch 2: update na categoria certa' {
        $m = Get-ManifestoPC ($jogos[1]) $Tab $E $J
        ($m.arquivos | Where-Object { $_.destino -eq '{JOGOS}/switch2/Jogo X/updates/romfs/a' }).categoria | Should Be 'update'
        $m.avisos.Count | Should Be 1   # o Lichii não está no PC: vai só o jogo
    }
    It 'lista para o Deck e assinatura' {
        $l = ConvertTo-ListaPublicada $jogos $Tab $E $J
        @($l.jogos).Count | Should Be 3
        $l.emuladores_pc.Contains('duckstation') | Should Be $true
        $a1 = Get-AssinaturaJogos $jogos $E $Tab
        Get-AssinaturaJogos $jogos $E $Tab | Should Be $a1
    }
}

Describe 'Envio e conferência' {
    $arqs = @([pscustomobject]@{ rel = 'JOGOS/psx/J/a.bin'; tamanho = 100; origem = 'C:\J\a.bin'; sha256 = ('aa' * 32) },
              [pscustomobject]@{ rel = 'JOGOS/psx/J/b.bin'; tamanho = 50; origem = 'C:\J\b.bin'; sha256 = ('bb' * 32) },
              [pscustomobject]@{ rel = 'EMU/settings.ini'; tamanho = 10; origem = 'C:\E\settings.ini'; sha256 = ('cc' * 32) })
    It 'put do que falta, reput do que está pela metade, nada do que tem o tamanho certo' {
        $rem = Read-TamanhosRemotos "40`tJOGOS/psx/J/a.bin`n50`tJOGOS/psx/J/b.bin`n"
        $l = New-LoteSftpPut -Arquivos $arqs -Remotos $rem -AreaRemota '.local/share/deck-commander/receber/psx-j'
        $l.Quantos | Should Be 2
        $l.Texto | Should Match '-reput "C:/J/a.bin" ".local/share/deck-commander/receber/psx-j/arquivos/JOGOS/psx/J/a.bin"'
        $l.Texto | Should Match '-put "C:/E/settings.ini"'
        $l.Texto | Should Not Match 'b\.bin'
    }
    It 'SHA256SUMS no formato do sha256sum' {
        (Format-Sha256Sums $arqs[0..0]) | Should Be ("$('aa' * 32)  JOGOS/psx/J/a.bin`n")
    }
    It 'lê as falhas do sha256sum -c (com nome entre aspas do coreutils novo)' {
        $f = @(Read-FalhasSha256Sum ("JOGOS/x/a.bin: FAILED`n'JOGOS/psx/Teste DC [X]/t.cue': FAILED`nEMU/c: FAILED open or read`nsha256sum: WARNING: 1 computed checksum did NOT match"))
        $f -join '|' | Should Be 'JOGOS/x/a.bin|JOGOS/psx/Teste DC [X]/t.cue|EMU/c'
        @(Read-FalhasSha256Sum 'sha256sum: ../SHA256SUMS: 1 line is improperly formatted').Count | Should Be 1
        @(Read-FalhasSha256Sum '').Count | Should Be 0
    }
    It 'área no Deck: normal e de teste (recusa caminho perigoso)' {
        Get-AreaRemota 'psx-j' '' | Should Be '.local/share/deck-commander/receber/psx-j'
        Get-AreaRemota 'psx-j' '~/dc-teste-receber' | Should Be 'dc-teste-receber/area/psx-j'
        { Get-AreaRemota 'psx-j' '~/../etc' } | Should Throw
        { Get-AreaRemota 'psx-j' '/etc' } | Should Throw
        { Get-AreaRemota 'psx-j' '~/a b' } | Should Throw
    }
}
