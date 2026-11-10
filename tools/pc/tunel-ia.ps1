# Deck Commander - empresta a IA do PC (Ollama + placa de video) para o Steam Deck traduzir mais rapido.
# Abre um tunel SSH reverso: no Deck, http://127.0.0.1:11435 = Ollama deste PC (127.0.0.1:11434).
# Nada e aberto na rede/firewall do PC: quem conecta e o PC. Se cair (Deck dormindo, fora de casa), tenta de novo.
# Instalar como tarefa ao entrar no Windows:  powershell -ExecutionPolicy Bypass -File instalar-tunel-ia.ps1 -Deck deck@IP-DO-DECK
# O Deck usado fica guardado em %USERPROFILE%\.deck-commander-pc.txt (nada fixo no codigo).
param(
    [string]$Deck = "",
    [string]$Key = "$env:USERPROFILE\.ssh\deck_commander_ed25519"
)
$cfg = Join-Path $env:USERPROFILE ".deck-commander-pc.txt"
if (-not $Deck -and (Test-Path $cfg)) { $Deck = (Get-Content $cfg -TotalCount 1).Trim() }
if (-not $Deck) { $Deck = "deck@steamdeck.local" }
$logDir = Join-Path $env:LOCALAPPDATA "DeckCommander"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "tunel-ia.log"
function Log($m) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 1MB) { Move-Item -Force $log "$log.old" }
    Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m)
}
Log "inicio (pid $PID) -> $Deck"
try {
    while ($true) {
        & ssh -i $Key -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
            -o ExitOnForwardFailure=yes -o ConnectTimeout=15 -N -R 127.0.0.1:11435:127.0.0.1:11434 $Deck
        Log "ssh saiu com codigo $LASTEXITCODE; nova tentativa em 60 s"
        Start-Sleep -Seconds 60
    }
} finally {
    Log "script encerrado (pid $PID)"
}
