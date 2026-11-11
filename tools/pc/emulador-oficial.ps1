# Deck Commander - emulador Windows OFICIAL no PC (o mesmo que a transferência Deck -> PC usa quando falta).
#
# Uso:  emulador-oficial.ps1 -Detectar                          o que já está em D:\Emuladores (e o que baixaria)
#       emulador-oficial.ps1 -Emulador lichii -Simular          mostra versão, arquivo, URL e sha256 da página oficial
#       emulador-oficial.ps1 -Emulador lichii -Versao build-83  baixa (confere o sha256 publicado), extrai em modo
#                                                               portátil em D:\Emuladores\<pasta> e registra em
#                                                               D:\Emuladores\_downloads\downloads.json
# Origens oficiais: config\emuladores-oficiais.json. Nunca sobrescreve uma pasta de emulador que já existe.
param(
    [string]$Emulador,
    [string]$Versao,
    [string]$Sha256Linux,   # sha256 do AppImage do Deck: acha a mesma build
    [switch]$Simular,
    [switch]$Detectar,
    [string]$Emuladores = 'D:\Emuladores'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'transferencia-funcoes.psm1') -Force -DisableNameChecking
$tab = Get-TabelaEmuladores
if ($Detectar) {
    $pc = Get-EmuladoresPC $Emuladores $tab
    foreach ($k in ($tab.Keys | Sort-Object)) {
        if ($pc.Contains($k)) { Write-Host ("{0,-12} SIM  {1}  dados: {2}{3}" -f $k, $pc[$k].Exe, $pc[$k].Dados, $(if ($pc[$k].Versao) { "  ($($pc[$k].Versao))" } else { '' })) -ForegroundColor Green }
        else { Write-Host ("{0,-12} não  -> [simulação] {1}" -f $k, (Format-PlanoEmulador (Get-PlanoEmuladorPC -Emu $k -Tab $tab -Emuladores $Emuladores))) -ForegroundColor Yellow }
    }
    exit 0
}
if (-not $Emulador -or -not $tab.ContainsKey($Emulador)) { throw "Use -Emulador com um destes: $(($tab.Keys | Sort-Object) -join ', ')" }
$x = Find-EmuladorPC $Emulador $Emuladores $tab
if ($x) { Write-Host "Já está no PC: $($x.Exe)" -ForegroundColor Green; exit 0 }
$plano = Get-PlanoEmuladorPC -Emu $Emulador -Versao $Versao -Sha256Linux $Sha256Linux -Tab $tab -Emuladores $Emuladores
Write-Host (Install-EmuladorPC -Plano $plano -Emuladores $Emuladores -Tab $tab -Simular:$Simular)
