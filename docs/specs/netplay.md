Arquivo: dc/netplay.py — "Jogar com o irmão": jogo em rede do RetroArch entre dois Steam Decks pela Tailscale
(sem abrir porta no roteador). Python 3.11, só biblioteca padrão, type hints, docstrings curtas em português.
Chamadas externas pelo parâmetro `run` (subprocess.run). Tudo que grava estado recebe a pasta `estado: Path`.

Como funciona: quem convida vira o anfitrião (abre o jogo com --host); o outro Deck recebe um convite (arquivo) e,
ao aceitar, abre o MESMO jogo com --connect <IP Tailscale do anfitrião>. Os dois abrem pelo atalho normal do
Steam; o lançador (dc/launch.py) consulta este módulo e acrescenta os argumentos.

PORTA = 55435
VALIDADE = 300  # segundos que um pedido de abrir em rede vale

1) def ip_tailscale(run=subprocess.run) -> str | None
   run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10); devolve a 1ª linha se for um IPv4
   (regex \d+\.\d+\.\d+\.\d+), senão None. FileNotFoundError -> None.

2) def pedir(estado: Path, game_id: str, papel: str, ip: str | None = None, agora: float | None = None) -> None
   papel "host" ou "cliente" (cliente exige ip, senão ValueError). Grava estado/"netplay-pedido.json" com
   {"game_id", "papel", "ip", "quando": agora ou time.time()}.

3) def argumentos(estado: Path, game_id: str, agora: float | None = None) -> list[str]
   Lê o pedido; se for do mesmo game_id e tiver menos de VALIDADE segundos, APAGA o arquivo (vale uma vez) e devolve:
   host -> ["--host", "--port", str(PORTA)]; cliente -> ["--connect", ip, "--port", str(PORTA)].
   Qualquer outro caso (sem arquivo, outro jogo, vencido, JSON ruim) -> [] (e apaga se vencido).

4) def aplicar_no_comando(cmd: list[str], extra: list[str]) -> list[str]
   Só mexe se for RetroArch (algum item do cmd contém "org.libretro.RetroArch" ou termina em "retroarch"): insere
   `extra` logo ANTES do último item (a ROM). Senão devolve cmd igual.

5) def convite(estado: Path, de: str, game_id: str, titulo: str, ip: str, agora: float | None = None) -> None
   Grava estado/"netplay-convite.json" {"de", "game_id", "titulo", "ip", "quando"} (é o que o OUTRO Deck recebe).
   def convite_pendente(estado: Path, agora: float | None = None) -> dict | None : o convite se tiver menos de
   VALIDADE segundos, senão None (e apaga o vencido).
   def aceitar(estado: Path) -> dict : lê o convite, chama pedir(papel="cliente", ip=convite["ip"]), apaga o convite
   e devolve o convite; ValueError("nenhum convite") se não houver.

6) def comando_convidar_remoto(alvo: str, chave: str, de: str, game_id: str, titulo: str, ip: str) -> list[str]
   Comando ssh para criar o convite no Deck do par:
   ["ssh", "-i", chave, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", alvo,
    "cd ~/deck-commander && python3 -m dc.netplay receber " + shlex.quote(json.dumps({...})) ]
   (o JSON tem de, game_id, titulo, ip). E def main(argv) com o subcomando "receber <json>" que chama convite(...)
   com a pasta de estado padrão (Path.home()/".local/state/deck-commander") e imprime "ok".

Exemplo de teste (precisa passar):
   pedir(e, "snes-mario", "host", agora=1000); argumentos(e, "snes-mario", agora=1100) == ["--host", "--port", "55435"]
   e chamar de novo devolve [] (vale uma vez); pedir cliente com ip "100.64.0.2" em t=1000 e argumentos em t=2000
   devolve [] (vencido); aplicar_no_comando(["/usr/bin/flatpak","run","org.libretro.RetroArch","-L","x.so","/r.sfc"],
   ["--host"]) termina com ["--host", "/r.sfc"]; com cmd do DuckStation devolve igual.
