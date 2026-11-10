<#
  Deck Commander - fecha no PC o jogo que estava sendo transmitido para o Steam Deck.

  Chamado pelo Sunshine (prep-cmd "undo" de cada jogo gerado por biblioteca-pc.ps1) quando o jogo
  termina no Moonlight. Fecha so os processos cujo executavel mora dentro da pasta do jogo.
  Recusa pastas rasas (ex.: "C:\Program Files") para nunca fechar outra coisa por engano.
#>
param([Parameter(Mandatory = $true)][string]$Pasta)

try {
    $p = [IO.Path]::GetFullPath($Pasta.Trim().Trim('"')).TrimEnd('\', '/')
} catch { exit 0 }
if (($p -split '\\').Count -lt 3 -or -not (Test-Path -LiteralPath $p -PathType Container)) { exit 0 }

$alvo = $p + '\'
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($alvo, [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch { } }
exit 0
