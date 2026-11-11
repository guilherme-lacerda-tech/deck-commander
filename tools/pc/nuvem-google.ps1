# Deck Commander — liga os saves do Deck ao seu Google Drive (uma vez só).
#   powershell -ExecutionPolicy Bypass -File tools\pc\nuvem-google.ps1
# 1. baixa o rclone oficial para Windows (confere o sha256 publicado em downloads.rclone.org);
# 2. abre o navegador do PC para você entrar no Google e autorizar (o Google não deixa fazer isso por QR no Deck);
#    o acesso é "drive.file": o rclone só enxerga a pasta DeckCommander que ele mesmo cria — o resto do seu Drive não;
# 3. manda o acesso para o Deck (ssh), que passa a espelhar os saves de hora em hora (/nuvem no Telegram).
param(
    [string]$Deck = '',
    [string]$Chave = (Join-Path $env:USERPROFILE '.ssh\deck_commander_ed25519')
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding $false   # texto para o ssh em UTF-8
if (-not $Deck) {
    $arqDeck = Join-Path $env:USERPROFILE '.deck-commander\deck.txt'
    $Deck = if (Test-Path $arqDeck) { (Get-Content $arqDeck -TotalCount 1).Trim() } else { 'deck@steamdeck' }
}
$versao = 'v1.76.0'
$sha = '8b4fd2737ade4e70c057ef4a49deb7cffe94b0fb9d7587c189d149823f21a1dc'   # rclone-v1.76.0-windows-amd64.zip
$pasta = Join-Path $env:LOCALAPPDATA 'DeckCommander\rclone'
$exe = Join-Path $pasta 'rclone.exe'
if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force $pasta | Out-Null
    $zip = Join-Path $env:TEMP "rclone-$versao.zip"
    Write-Host "Baixando o rclone oficial ($versao)..."
    Invoke-WebRequest "https://downloads.rclone.org/$versao/rclone-$versao-windows-amd64.zip" -OutFile $zip -UseBasicParsing
    if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $sha) { throw 'O arquivo baixado do rclone não confere (sha256). Não instalei.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $m = $z.Entries | Where-Object { $_.FullName -like '*/rclone.exe' } | Select-Object -First 1
        [IO.Compression.ZipFileExtensions]::ExtractToFile($m, $exe, $true)
    } finally { $z.Dispose() }
    Remove-Item $zip -ErrorAction SilentlyContinue
}
$conf = Join-Path $pasta 'rclone.conf'
Write-Host 'Vou abrir o navegador: entre na sua conta Google e toque em Permitir.'
& $exe config create gdrive drive scope=drive.file --config $conf | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'O Google não autorizou (tente de novo).' }
$token = (& $exe config dump --config $conf | ConvertFrom-Json).gdrive.token
if (-not $token) { throw 'Não achei o acesso do Google no rclone.' }
$token | & ssh.exe -i $Chave -o BatchMode=yes -o ConnectTimeout=8 $Deck 'cd ~/deck-commander && python3 -m dc.nuvem configurar'
if ($LASTEXITCODE -ne 0) { throw 'Não consegui mandar o acesso para o Deck (ele está ligado e na mesma rede?).' }
Write-Host 'Pronto: o Deck vai espelhar os saves no Google Drive (pasta DeckCommander) de hora em hora.' -ForegroundColor Green
