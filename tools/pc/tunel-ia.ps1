# Deck Commander — empresta a IA do PC (Ollama + placa de vídeo) para o Steam Deck traduzir mais rápido.
# Abre um túnel SSH reverso: no Deck, http://127.0.0.1:11435 = Ollama deste PC (127.0.0.1:11434).
# Nada é aberto na rede/firewall do PC: quem conecta é o PC. Se cair (Deck dormindo, fora de casa), tenta de novo.
# Instalar como tarefa ao entrar no Windows:  powershell -ExecutionPolicy Bypass -File instalar-tunel-ia.ps1
param(
    [string]$Deck = "deck@192.168.100.24",
    [string]$Key = "$env:USERPROFILE\.ssh\deck_commander_ed25519"
)
while ($true) {
    & ssh -i $Key -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes -o ConnectTimeout=15 -N -R 127.0.0.1:11435:127.0.0.1:11434 $Deck
    Start-Sleep -Seconds 60
}
