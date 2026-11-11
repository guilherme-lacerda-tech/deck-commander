# Jogar os jogos do PC num Fire TV Stick (em outra casa)

O Fire Stick vira uma "tela" para o seu PC, do mesmo jeito que o Steam Deck: o jogo roda no PC de casa e a imagem vai
para a TV pela internet. O Deck Commander não roda no Fire Stick — quem faz o trabalho é o Moonlight (no Fire) e o
Sunshine (no PC), os mesmos que o Deck já usa.

## O que você precisa
- O PC de casa com o Sunshine (já configurado) e a **Tailscale**.
- O Fire TV Stick com internet e um **controle Bluetooth** (Xbox, PlayStation ou o próprio do Deck não serve aqui).
- Para acordar o PC de longe: o "porteiro" de casa (Fire TV de casa) ligado na tomada.

## Passo a passo (uma vez)
1. **Tailscale no Fire:** na Amazon Appstore do Fire, instale **Tailscale** e entre com a MESMA conta do PC.
   (Se não aparecer na loja: Configurações → Minha Fire TV → Opções do desenvolvedor → Apps de fontes desconhecidas →
   ligue para o app **Downloader**; no Downloader, abra o endereço oficial `tailscale.com/download/android`.)
2. **Moonlight no Fire:** na Appstore, instale **Moonlight Game Streaming** (oficial, gratuito).
3. **Parear:** abra o Moonlight. Se o PC não aparecer sozinho, toque em **+** e digite o **IP da Tailscale do PC**
   (aparece no painel do Deck → PC → "IP da Tailscale"). O Moonlight mostra um **PIN de 4 números**.
4. **Digite o PIN no Sunshine:** no PC, abra `https://localhost:47990` → **PIN** → digite os 4 números.
   Longe de casa e sem acesso ao PC? Peça para alguém em casa, ou faça este passo antes de sair.
5. **Controle:** pareie o controle Bluetooth no Fire (Configurações → Controles e dispositivos Bluetooth).

## Jogando
1. Acorde o PC: no Telegram, `/pc acordar` (ou no painel do Deck → PC → Acordar PC).
2. Espere ~1 minuto, abra o Moonlight no Fire e escolha o jogo (a mesma lista da aba "Computador" do Deck).
3. Ao terminar, saia pelo menu do Moonlight (segure **Start + Select + L1 + R1** no controle → Sair do app). O PC volta
   a dormir sozinho alguns minutos depois.

## Dicas
- Internet da outra casa fraca? No Moonlight → Configurações: 720p, 30 fps, taxa 5–10 Mbps.
- Atraso nos controles: ligue o Fire no **cabo/5 GHz** e use o controle por Bluetooth perto da TV.
