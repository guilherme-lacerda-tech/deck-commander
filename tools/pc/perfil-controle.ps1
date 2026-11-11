param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Salvar", "Aplicar", "Restaurar", "Estado")]
    [string]$Acao,
    
    [ValidateSet("Lichii", "Ryujinx", "PCSX2", "DuckStation", "Todos")]
    [string]$Emulador = "Todos",
    
    [string]$Emuladores = "D:\Emuladores",
    
    [string]$Perfis = "$env:ProgramData\DeckCommander\perfis-controle"
)
New-Item -ItemType Directory -Force -Path $Perfis -ErrorAction SilentlyContinue | Out-Null  # 1ª vez: cria a pasta

# Funções auxiliares
function Ler-Secoes-Ini {
    param([string]$Arquivo, [array]$Secoes)
    
    $conteudo = Get-Content -Path $Arquivo -Encoding UTF8
    $secoesEncontradas = @{}
    
    foreach ($secao in $Secoes) {
        $inicio = $null
        $fim = $null
        
        for ($i = 0; $i -lt $conteudo.Length; $i++) {
            if ($conteudo[$i] -match "^\[$secao\]$") {
                $inicio = $i
            } elseif ($inicio -ne $null -and $i -gt $inicio -and $conteudo[$i] -match "^\[.*\]$") {
                $fim = $i - 1
                break
            } elseif ($i -eq $conteudo.Length - 1) {
                $fim = $i
            }
        }
        
        if ($inicio -ne $null) {
            $secoesEncontradas[$secao] = $conteudo[$inicio..$fim]
        }
    }
    
    return $secoesEncontradas
}

function Trocar-Secoes-Ini {
    param([string]$Arquivo, [hashtable]$SecoesNovas)
    
    $conteudoOriginal = Get-Content -Path $Arquivo -Encoding UTF8
    $conteudoModificado = @()
    $i = 0
    
    while ($i -lt $conteudoOriginal.Length) {
        $linha = $conteudoOriginal[$i]
        
        if ($linha -match "^\[(.*)\]$") {
            $secaoAtual = $matches[1]
            
            if ($SecoesNovas.ContainsKey($secaoAtual)) {
                $conteudoModificado += $SecoesNovas[$secaoAtual]
                do {
                    $i++
                    if ($i -lt $conteudoOriginal.Length) {
                        $linha = $conteudoOriginal[$i]
                    } else {
                        break
                    }
                } while ($linha -notmatch "^\[.*\]$" -and $i -lt $conteudoOriginal.Length)
                $i--
            } else {
                $conteudoModificado += $linha
            }
        } else {
            $conteudoModificado += $linha
        }
        
        $i++
    }
    
    $tempFile = "$Arquivo.tmp"
    $conteudoModificado | Out-File -FilePath $tempFile -Encoding UTF8
    Move-Item -Path $tempFile -Destination $Arquivo -Force
}

function Ler-Linhas-Prefixo {
    param([string]$Arquivo, [string[]]$Prefixos)
    
    $linhas = Get-Content -Path $Arquivo -Encoding UTF8
    $linhasFiltradas = @()
    
    foreach ($linha in $linhas) {
        foreach ($prefixo in $Prefixos) {
            if ($linha.StartsWith($prefixo)) {
                $linhasFiltradas += $linha
                break
            }
        }
    }
    
    return $linhasFiltradas
}

function Trocar-Linhas-Prefixo {
    param([string]$Arquivo, [string[]]$LinhasNovas)
    
    $conteudoOriginal = Get-Content -Path $Arquivo -Encoding UTF8
    $conteudoModificado = @()
    $i = 0
    
    while ($i -lt $conteudoOriginal.Length) {
        $linha = $conteudoOriginal[$i]
        
        if ($linha.StartsWith("player_0_") -or $linha.StartsWith("player_1_")) {
            $novaLinha = $LinhasNovas[0]
            $linhasNovas = $LinhasNovas | Select-Object -Skip 1
            $conteudoModificado += $novaLinha
        } else {
            $conteudoModificado += $linha
        }
        
        $i++
    }
    
    $tempFile = "$Arquivo.tmp"
    $conteudoModificado | Out-File -FilePath $tempFile -Encoding UTF8
    Move-Item -Path $tempFile -Destination $Arquivo -Force
}

function Ler-InputConfig {
    param([string]$Arquivo)
    
    $conteudo = Get-Content -Path $Arquivo -Raw -Encoding UTF8
    $json = $conteudo | ConvertFrom-Json
    
    return $json.input_config
}

function Trocar-InputConfig {
    param([string]$Arquivo, [array]$NovoInputConfig)
    
    $conteudoOriginal = Get-Content -Path $Arquivo -Raw -Encoding UTF8
    $json = $conteudoOriginal | ConvertFrom-Json
    
    $json.input_config = $NovoInputConfig
    
    $tempFile = "$Arquivo.tmp"
    $json | ConvertTo-Json | Out-File -FilePath $tempFile -Encoding UTF8
    Move-Item -Path $tempFile -Destination $Arquivo -Force
}

# Funções principais
function Salvar-Perfil {
    param([string]$Emulador)
    
    try {
        switch ($Emulador) {
            "Lichii" {
                $arquivo = "$Emuladores\Lichii\user\config\qt-config.ini"
                if (Test-Path $arquivo) {
                    $linhas = Ler-Linhas-Prefixo -Arquivo $arquivo -Prefixos @("player_0_", "player_1_")
                    $destino = "$Perfis\Lichii.stream.txt"
                    $linhas | Out-File -FilePath $destino -Encoding UTF8
                }
            }
            "Ryujinx" {
                $arquivo = "$Emuladores\Ryujinx\publish\portable\Config.json"
                if (Test-Path $arquivo) {
                    $inputConfig = Ler-InputConfig -Arquivo $arquivo
                    $destino = "$Perfis\Ryujinx.stream.txt"
                    $inputConfig | ConvertTo-Json | Out-File -FilePath $destino -Encoding UTF8
                }
            }
            "PCSX2" {
                $arquivo = "$Emuladores\PCSX2\inis\PCSX2.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $arquivo -Secoes @("Pad1", "Pad2")
                    $destino = "$Perfis\PCSX2.stream.txt"
                    $secoes["Pad1"] | Out-File -FilePath $destino -Encoding UTF8
                    $secoes["Pad2"] | Out-File -FilePath $destino -Encoding UTF8 -Append
                }
            }
            "DuckStation" {
                $arquivo = "$Emuladores\DuckStation\settings.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $arquivo -Secoes @("Pad1", "Pad2")
                    $destino = "$Perfis\DuckStation.stream.txt"
                    $secoes["Pad1"] | Out-File -FilePath $destino -Encoding UTF8
                    $secoes["Pad2"] | Out-File -FilePath $destino -Encoding UTF8 -Append
                }
            }
        }
    } catch {
        Write-Warning "Erro ao salvar perfil para ${Emulador}: $_"
    }
}

function Aplicar-Perfil {
    param([string]$Emulador)
    
    try {
        $mesaFile = "$Perfis\$Emulador.mesa.txt"
        $streamFile = "$Perfis\$Emulador.stream.txt"
        
        if (-not (Test-Path $streamFile)) {
            Write-Warning "Nenhum perfil de stream encontrado para $Emulador."
            return
        }
        
        if (-not (Test-Path $mesaFile)) {
            switch ($Emulador) {
                "Lichii" {
                    $arquivo = "$Emuladores\Lichii\user\config\qt-config.ini"
                    if (Test-Path $arquivo) {
                        $linhas = Ler-Linhas-Prefixo -Arquivo $arquivo -Prefixos @("player_0_", "player_1_")
                        $linhas | Out-File -FilePath $mesaFile -Encoding UTF8
                    }
                }
                "Ryujinx" {
                    $arquivo = "$Emuladores\Ryujinx\publish\portable\Config.json"
                    if (Test-Path $arquivo) {
                        $inputConfig = Ler-InputConfig -Arquivo $arquivo
                        $inputConfig | ConvertTo-Json | Out-File -FilePath $mesaFile -Encoding UTF8
                    }
                }
                "PCSX2" {
                    $arquivo = "$Emuladores\PCSX2\inis\PCSX2.ini"
                    if (Test-Path $arquivo) {
                        $secoes = Ler-Secoes-Ini -Arquivo $arquivo -Secoes @("Pad1", "Pad2")
                        $secoes["Pad1"] | Out-File -FilePath $mesaFile -Encoding UTF8
                        $secoes["Pad2"] | Out-File -FilePath $mesaFile -Encoding UTF8 -Append
                    }
                }
                "DuckStation" {
                    $arquivo = "$Emuladores\DuckStation\settings.ini"
                    if (Test-Path $arquivo) {
                        $secoes = Ler-Secoes-Ini -Arquivo $arquivo -Secoes @("Pad1", "Pad2")
                        $secoes["Pad1"] | Out-File -FilePath $mesaFile -Encoding UTF8
                        $secoes["Pad2"] | Out-File -FilePath $mesaFile -Encoding UTF8 -Append
                    }
                }
            }
        }
        
        switch ($Emulador) {
            "Lichii" {
                $arquivo = "$Emuladores\Lichii\user\config\qt-config.ini"
                if (Test-Path $arquivo) {
                    $linhas = Get-Content -Path $streamFile -Encoding UTF8
                    Trocar-Linhas-Prefixo -Arquivo $arquivo -LinhasNovas $linhas
                }
            }
            "Ryujinx" {
                $arquivo = "$Emuladores\Ryujinx\publish\portable\Config.json"
                if (Test-Path $arquivo) {
                    $inputConfig = Get-Content -Path $streamFile -Raw -Encoding UTF8 | ConvertFrom-Json
                    Trocar-InputConfig -Arquivo $arquivo -NovoInputConfig $inputConfig.input_config
                }
            }
            "PCSX2" {
                $arquivo = "$Emuladores\PCSX2\inis\PCSX2.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $streamFile -Secoes @("Pad1", "Pad2")
                    Trocar-Secoes-Ini -Arquivo $arquivo -SecoesNovas $secoes
                }
            }
            "DuckStation" {
                $arquivo = "$Emuladores\DuckStation\settings.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $streamFile -Secoes @("Pad1", "Pad2")
                    Trocar-Secoes-Ini -Arquivo $arquivo -SecoesNovas $secoes
                }
            }
        }
        
        Write-Output "Perfil de stream aplicado para $Emulador."
    } catch {
        Write-Warning "Erro ao aplicar perfil para ${Emulador}: $_"
    }
}

function Restaurar-Perfil {
    param([string]$Emulador)
    
    try {
        $mesaFile = "$Perfis\$Emulador.mesa.txt"
        
        if (-not (Test-Path $mesaFile)) {
            Write-Warning "Nenhum perfil de mesa encontrado para $Emulador."
            return
        }
        
        switch ($Emulador) {
            "Lichii" {
                $arquivo = "$Emuladores\Lichii\user\config\qt-config.ini"
                if (Test-Path $arquivo) {
                    $linhas = Get-Content -Path $mesaFile -Encoding UTF8
                    Trocar-Linhas-Prefixo -Arquivo $arquivo -LinhasNovas $linhas
                }
            }
            "Ryujinx" {
                $arquivo = "$Emuladores\Ryujinx\publish\portable\Config.json"
                if (Test-Path $arquivo) {
                    $inputConfig = Get-Content -Path $mesaFile -Raw -Encoding UTF8 | ConvertFrom-Json
                    Trocar-InputConfig -Arquivo $arquivo -NovoInputConfig $inputConfig.input_config
                }
            }
            "PCSX2" {
                $arquivo = "$Emuladores\PCSX2\inis\PCSX2.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $mesaFile -Secoes @("Pad1", "Pad2")
                    Trocar-Secoes-Ini -Arquivo $arquivo -SecoesNovas $secoes
                }
            }
            "DuckStation" {
                $arquivo = "$Emuladores\DuckStation\settings.ini"
                if (Test-Path $arquivo) {
                    $secoes = Ler-Secoes-Ini -Arquivo $mesaFile -Secoes @("Pad1", "Pad2")
                    Trocar-Secoes-Ini -Arquivo $arquivo -SecoesNovas $secoes
                }
            }
        }
        
        Remove-Item -Path $mesaFile -Force
        Write-Output "Perfil restaurado para $Emulador."
    } catch {
        Write-Warning "Erro ao restaurar perfil para ${Emulador}: $_"
    }
}

function Estado-Perfis {
    $emuladores = @("Lichii", "Ryujinx", "PCSX2", "DuckStation")
    
    foreach ($emu in $emuladores) {
        $streamFile = "$Perfis\$emu.stream.txt"
        $mesaFile = "$Perfis\$emu.mesa.txt"
        
        $temStream = Test-Path $streamFile
        $temMesa = Test-Path $mesaFile
        
        Write-Output "[$emu] Stream: $(if ($temStream) { 'Sim' } else { 'Não' }), Mesa: $(if ($temMesa) { 'Sim' } else { 'Não' })"
    }
}

# Execução principal
switch ($Acao) {
    "Salvar" {
        if ($Emulador -eq "Todos") {
            $emuladores = @("Lichii", "Ryujinx", "PCSX2", "DuckStation")
            foreach ($emu in $emuladores) {
                Salvar-Perfil -Emulador $emu
            }
        } else {
            Salvar-Perfil -Emulador $Emulador
        }
    }
    "Aplicar" {
        if ($Emulador -eq "Todos") {
            $emuladores = @("Lichii", "Ryujinx", "PCSX2", "DuckStation")
            foreach ($emu in $emuladores) {
                Aplicar-Perfil -Emulador $emu
            }
        } else {
            Aplicar-Perfil -Emulador $Emulador
        }
    }
    "Restaurar" {
        if ($Emulador -eq "Todos") {
            $emuladores = @("Lichii", "Ryujinx", "PCSX2", "DuckStation")
            foreach ($emu in $emuladores) {
                Restaurar-Perfil -Emulador $emu
            }
        } else {
            Restaurar-Perfil -Emulador $Emulador
        }
    }
    "Estado" {
        Estado-Perfis
    }
}
