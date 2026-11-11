"""Transferência PC -> Deck (dc/receber.py): emulador no Deck, plano oficial, área, conferência, instalação, fila."""
import hashlib
import json
from pathlib import Path

import pytest

from dc import receber as R
from dc import transferir as T

TAB = json.loads((Path(__file__).resolve().parents[1] / "config/emuladores-oficiais.json").read_text("utf-8"))["emuladores"]
SEM_FLATPAK = lambda app_id: None  # noqa: E731


def _w(p: Path, data=b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return p


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _area(home: Path, gid: str, arquivos: dict, emulador="duckstation", console="psx", regras=None, teste=None, **extra):
    """Monta a área de recebimento como o PC deixaria: {destino: (bytes, categoria)}."""
    area = R.area_de(gid, home, teste)
    itens = []
    for destino, (dados, cat) in arquivos.items():
        rel = destino.replace("{JOGOS}", "JOGOS", 1).replace("{EMU}", "EMU", 1)
        _w(area / "arquivos" / rel, dados)
        itens.append({"rel": rel, "destino": destino, "sha256": _sha(dados), "tamanho": len(dados), "categoria": cat,
                      "reescrever": cat.startswith("config")})
    man = {"versao": 1, "direcao": "pc->deck", "game_id": gid, "titulo": "Jogo Teste", "console": console,
           "emulador": emulador, "emulador_pc": {"versao": "v1.0"}, "reescrever": regras or [], "arquivos": itens,
           "avisos": [], **extra}
    _w(area / "manifesto.json", json.dumps(man))
    return area, man


# ------------------------------------------------------------------ tabela oficial ------
def test_tabela_cobre_os_emuladores_pedidos():
    for emu in ("lichii", "ryujinx", "pcsx2", "duckstation", "ppsspp", "xenia", "retroarch", "dolphin", "cemu", "rpcs3",
                "azahar", "melonds", "xemu", "flycast"):
        e = TAB[emu]
        assert e["pagina"].startswith("https://") and e["windows"] and e["linux"]
        assert e["windows"].get("asset") or e["windows"].get("url") or e["windows"].get("manual")
    assert R.emu_do_console("switch2", TAB) == "lichii"
    assert R.emu_do_console("gba", TAB) == "retroarch"
    assert R.emu_do_console("xyz", TAB) is None


def test_tabela_le_arquivo_com_bom(tmp_path, monkeypatch):
    _w(tmp_path / "t.json", "\ufeff" + json.dumps({"emuladores": {"x": {"nome": "X"}}}))
    monkeypatch.setenv("DC_EMU_TABELA", str(tmp_path / "t.json"))
    assert R.tabela(tmp_path)["x"]["nome"] == "X"


# ------------------------------------------------------------------ emulador no Deck ----
def test_detecta_appimage_pasta_e_flatpak(tmp_path):
    _w(tmp_path / "Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage")
    _w(tmp_path / "Downloads/publish/Ryujinx")
    d = R.emulador_no_deck("lichii", tmp_path, TAB, SEM_FLATPAK)
    assert d["instalado"] and d["tipo"] == "appimage"
    assert R.emulador_no_deck("ryujinx", tmp_path, TAB, SEM_FLATPAK)["tipo"] == "pasta"
    assert not R.emulador_no_deck("pcsx2", tmp_path, TAB, SEM_FLATPAK)["instalado"]
    f = R.emulador_no_deck("pcsx2", tmp_path, TAB, lambda i: "v2.6.3" if i == "net.pcsx2.PCSX2" else None)
    assert f["tipo"] == "flatpak" and f["versao"] == "v2.6.3"
    assert len(R.detectar_todos(tmp_path, TAB, SEM_FLATPAK)) == len(TAB)


# ------------------------------------------------------------------ plano oficial -------
REL = {"tag_name": "build-83", "assets": [
    {"name": "lichii-linux-x86_64-pgo.AppImage", "browser_download_url": "https://github.com/x/releases/download/build-83/a",
     "size": 10, "digest": "sha256:" + "ab" * 32},
    {"name": "lichii-windows-x86_64-pgo.zip", "browser_download_url": "https://x/w", "size": 5, "digest": None}]}


def test_plano_appimage_mesma_versao_com_sha(tmp_path):
    urls = []
    p = R.plano_instalacao("lichii", "build-83", tmp_path, TAB, get=lambda u: urls.append(u) or REL)
    assert urls == ["https://api.github.com/repos/zortos293/Lichii/releases/tags/build-83"]
    assert p["acao"] == "appimage" and p["mesma_versao"] and p["sha256"] == "ab" * 32
    assert p["destino"].endswith("Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage".replace("/", "\\")) or \
        p["destino"].endswith("Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage")
    assert "mesma versão do PC" in R.texto_plano(p) and "página oficial" in R.texto_plano(p)


def test_plano_versao_sumiu_cai_na_mais_recente(tmp_path):
    def get(u):
        if "/tags/" in u:
            raise OSError("404")
        return REL
    p = R.plano_instalacao("lichii", "build-1", tmp_path, TAB, get=get)
    assert p["versao"] == "build-83" and not p["mesma_versao"]


def test_plano_flatpak_e_sem_asset(tmp_path):
    p = R.plano_instalacao("pcsx2", None, tmp_path, TAB, get=lambda u: pytest.fail("Flathub não consulta API"))
    assert p["acao"] == "flatpak" and p["id"] == "net.pcsx2.PCSX2" and "flatpak install" in p["comando"]
    p = R.plano_instalacao("duckstation", None, tmp_path, TAB, get=lambda u: {"tag_name": "latest", "assets": []})
    assert p["acao"] == "nenhum" and "não tem o arquivo Linux" in p["motivo"]
    assert R.plano_instalacao("nada", None, tmp_path, TAB)["acao"] == "nenhum"


def test_instalar_emulador_simulado_e_flatpak_sem_rede(tmp_path):
    p = R.plano_instalacao("lichii", "build-83", tmp_path, TAB, get=lambda u: REL)
    assert R.instalar_emulador(p, simular=True).startswith("[simulação]")
    assert not Path(p["destino"]).exists()
    chamadas = []

    class Ok:
        returncode, stdout, stderr = 0, "", ""
    msg = R.instalar_emulador({"acao": "flatpak", "id": "net.pcsx2.PCSX2", "nome": "PCSX2"},
                              run=lambda a, **k: chamadas.append(a) or Ok())
    assert chamadas == [[R.FLATPAK, "install", "--user", "-y", "flathub", "net.pcsx2.PCSX2"]] and "instalado" in msg


def test_instalar_appimage_confere_sha_e_nao_sobrescreve(tmp_path, monkeypatch):
    conteudo = b"appimage-oficial"

    def baixar(url, dest, sha):
        assert sha == _sha(conteudo)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(conteudo)
    monkeypatch.setattr(R, "_baixar", baixar)
    plano = {"acao": "appimage", "nome": "Lichii", "versao": "build-83", "url": "u", "sha256": _sha(conteudo),
             "destino": str(tmp_path / "Emulation/Lichii/l.AppImage")}
    assert "instalado" in R.instalar_emulador(plano)
    assert "já existe" in R.instalar_emulador(plano)


# ------------------------------------------------------------------ mapeamento ----------
def test_caminho_deck_e_sub_do_lichii(tmp_path):
    base, sub = R.dados_emulador("lichii", tmp_path, TAB)
    assert base == tmp_path / ".local/share/eden" and sub == {"config": tmp_path / ".config/eden"}
    roms = tmp_path / "Emulation/roms"
    assert R.caminho_deck("{EMU}/config/qt-config.ini", roms, base, sub) == tmp_path / ".config/eden/qt-config.ini"
    assert R.caminho_deck("{EMU}/nand/user/save/x", roms, base, sub) == base / "nand/user/save/x"
    assert R.caminho_deck("{JOGOS}/psx/J/a.bin", roms, base, sub) == roms / "psx/J/a.bin"
    with pytest.raises(ValueError):
        R.caminho_deck("{JOGOS}/../../.bashrc", roms, base, sub)
    with pytest.raises(ValueError):
        R.caminho_deck("{OUTRO}/x", roms, base, sub)


def test_dados_prefere_pasta_existente_ou_flatpak(tmp_path):
    (tmp_path / ".config/Ryujinx").mkdir(parents=True)
    assert R.dados_emulador("ryujinx", tmp_path, TAB)[0] == tmp_path / ".config/Ryujinx"
    assert R.dados_emulador("pcsx2", tmp_path / "v", TAB)[0] == tmp_path / "v/.var/app/net.pcsx2.PCSX2/config/PCSX2"


def test_reescreve_caminhos_do_windows(tmp_path):
    base, sub = R.dados_emulador("lichii", tmp_path, TAB)
    roms = tmp_path / "Emulation/roms"
    regras = [{"de": "D:/Emuladores/Lichii/user", "para": "{EMU}"}, {"de": "D:/DeckCommander/Jogos", "para": "{JOGOS}"}]
    ini = ("nand_directory=D:/Emuladores/Lichii/user/nand\nPaths\\gamedirs\\4\\path=D:/DeckCommander/Jogos/switch2/Jogo X\n"
           "cfg=d:\\Emuladores\\Lichii\\user\\config\nnada=C:/outro\n")
    out = R.reescrever(ini, regras, roms, base, sub)
    assert f"nand_directory={(base / 'nand').as_posix()}" in out
    assert f"path={(roms / 'switch2/Jogo X').as_posix()}" in out
    assert f"cfg={(tmp_path / '.config/eden').as_posix()}" in out
    assert "nada=C:/outro" in out
    js = '{"game_dirs": ["D:\\\\DeckCommander\\\\Jogos\\\\switch"]}'
    assert json.loads(R.reescrever(js, regras, roms, base, sub))["game_dirs"] == [(roms / "switch").as_posix()]


# ------------------------------------------------------------------ receber -------------
def _regras_duck():
    return [{"de": "D:/Emuladores/DuckStation", "para": "{EMU}"}, {"de": "D:/DeckCommander/Jogos", "para": "{JOGOS}"}]


def test_receber_instala_com_backup_e_mantem_config_global(tmp_path, monkeypatch):
    home = tmp_path
    _w(home / "Applications/DuckStation-x64.AppImage")  # o Deck já tem o emulador
    duck = home / ".local/share/duckstation"
    _w(duck / "settings.ini", "[Main]\nDoDeck=1\n")
    _w(duck / "memcards/Jogo Teste_1.mcd", b"save antigo do deck")
    area, man = _area(home, "psx-jogo-teste", {
        "{JOGOS}/psx/Jogo Teste/jogo.cue": (b'FILE "jogo.bin" BINARY\n', "jogo"),
        "{JOGOS}/psx/Jogo Teste/jogo.bin": (b"\x00" * 100, "jogo"),
        "{EMU}/settings.ini": (b"[BIOS]\nSearchDirectory = D:/Emuladores/DuckStation/bios\n", "config-global"),
        "{EMU}/gamesettings/SLUS-99999.ini": (b"[GPU]\nPath=D:/DeckCommander/Jogos/psx/Jogo Teste\n", "config-jogo"),
        "{EMU}/memcards/Jogo Teste_1.mcd": (b"save novo do pc", "save"),
        "{EMU}/bios/scph1001.bin": (b"B" * 10, "keys"),
    }, regras=_regras_duck())
    chamou = []
    monkeypatch.setattr(R, "_biblioteca", lambda: chamou.append(1) or "na biblioteca: Jogo Teste")
    r = R.receber("psx-jogo-teste", home, flatpak=SEM_FLATPAK)
    assert not r.get("erro"), r
    assert (home / "Emulation/roms/psx/Jogo Teste/jogo.bin").read_bytes() == b"\x00" * 100
    assert (duck / "memcards/Jogo Teste_1.mcd").read_bytes() == b"save novo do pc"
    assert (duck / "settings.ini").read_text() == "[Main]\nDoDeck=1\n"  # config global do Deck mantida
    assert any("settings.ini" in x for x in r["mantidos"])
    gs = (duck / "gamesettings/SLUS-99999.ini").read_text()
    assert f"Path={(home / 'Emulation/roms/psx/Jogo Teste').as_posix()}" in gs
    bks = list(duck.glob("_backup-deck-commander/*-psx-jogo-teste/memcards/Jogo Teste_1.mcd"))
    assert len(bks) == 1 and bks[0].read_bytes() == b"save antigo do deck"
    assert r["backups"] == 1 and chamou == [1] and "biblioteca" in R.texto_relatorio(r)
    # de novo: tudo igual, nada muda
    r2 = R.receber("psx-jogo-teste", home, flatpak=SEM_FLATPAK)
    assert r2["instalados"] == 0 and r2["backups"] == 0


def test_receber_config_global_com_opcao(tmp_path, monkeypatch):
    _w(tmp_path / "Applications/DuckStation-x64.AppImage")
    _w(tmp_path / ".local/share/duckstation/settings.ini", "deck")
    _area(tmp_path, "psx-j", {"{EMU}/settings.ini": (b"pc", "config-global")})
    r = R.receber("psx-j", tmp_path, config_global=True, biblioteca=False, flatpak=SEM_FLATPAK)
    assert (tmp_path / ".local/share/duckstation/settings.ini").read_text() == "pc" and r["backups"] == 1


def test_receber_recusa_area_com_hash_errado(tmp_path):
    area, man = _area(tmp_path, "psx-j", {"{JOGOS}/psx/J/a.bin": (b"abc", "jogo")})
    (area / "arquivos/JOGOS/psx/J/a.bin").write_bytes(b"abd")
    r = R.receber("psx-j", tmp_path, biblioteca=False, flatpak=SEM_FLATPAK)
    assert "não conferem" in r["erro"] and r["ruins"][0]["motivo"] == "sha256 diferente"
    assert not (tmp_path / "Emulation/roms/psx/J/a.bin").exists()


def test_receber_modo_teste_nao_toca_pastas_reais_nem_instala_emulador(tmp_path, monkeypatch):
    home = tmp_path / "home"
    teste = home / "dc-teste-receber"
    _area(home, "switch2-j", {"{JOGOS}/switch2/J/base/exefs/main": (b"m", "jogo"),
                              "{EMU}/config/custom/0100.ini": (b"x=1", "config-jogo"),
                              "{EMU}/nand/user/save/0/U/0100/s.bin": (b"s", "save")},
          emulador="lichii", console="switch2", teste=teste)
    monkeypatch.setattr(R, "_baixar", lambda *a: pytest.fail("não pode baixar no teste"))
    monkeypatch.setattr(R, "_biblioteca", lambda: pytest.fail("não pode mexer na biblioteca no teste"))
    r = R.receber("switch2-j", home, destino_teste=teste, flatpak=SEM_FLATPAK, get=lambda u: REL)
    assert r["teste"] and not r.get("erro")
    assert (teste / "home/Emulation/roms/switch2/J/base/exefs/main").exists()
    assert (teste / "home/.config/eden/custom/0100.ini").exists()
    assert (teste / "home/.local/share/eden/nand/user/save/0/U/0100/s.bin").exists()
    assert not (home / "Emulation").exists() and not (home / ".config").exists()
    assert r["emulador_instalacao"].startswith("[simulação]") and "build-83" in r["emulador_instalacao"]
    assert "NÃO entrou na biblioteca" in r["biblioteca"]


def test_receber_ryujinx_nao_mistura_indice_de_saves(tmp_path):
    ryu = tmp_path / ".config/Ryujinx"
    _w(ryu / "bis/system/save/8000000000000000/0/imkvdb.arc", b"indice do deck")
    _w(tmp_path / "Downloads/publish/Ryujinx")
    _area(tmp_path, "switch-j", {"{EMU}/bis/system/save/8000000000000000/0/imkvdb.arc": (b"indice do pc", "config-global"),
                                 "{EMU}/bis/user/save/0000000000000004/0/s": (b"s", "save"),
                                 "{EMU}/games/0100/Config.json": (b"{}", "config-jogo")},
          emulador="ryujinx", console="switch")
    r = R.receber("switch-j", tmp_path, biblioteca=False, flatpak=SEM_FLATPAK)
    assert (ryu / "bis/system/save/8000000000000000/0/imkvdb.arc").read_bytes() == b"indice do deck"
    assert not (ryu / "bis/user/save/0000000000000004").exists()
    assert (ryu / "games/0100/Config.json").exists() and len(r["pulados"]) == 2


def test_receber_valida_manifesto(tmp_path):
    area = R.area_de("x", tmp_path)
    _w(area / "manifesto.json", json.dumps({"direcao": "deck->pc", "game_id": "x", "arquivos": []}))
    with pytest.raises(ValueError):
        R.receber("x", tmp_path)


def test_main_recusa_destino_teste_perigoso(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    assert R.main(["receber", "x", "--destino-teste", str(tmp_path / "Emulation/roms")]) == 2
    assert R.main(["receber", "../x"]) == 2
    assert R.main([]) == 2


def test_main_conferir_e_receber_por_linha_de_comando(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    monkeypatch.setattr(R, "flatpak_info", SEM_FLATPAK)
    teste = tmp_path / "dc-teste-receber"
    _area(tmp_path, "psx-j", {"{JOGOS}/psx/J/a.bin": (b"abc", "jogo")}, teste=teste, emulador="")
    assert T.main(["conferir", "psx-j", "--destino-teste", str(teste)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert T.main(["receber", "psx-j", "--destino-teste", str(teste)]) == 0
    assert "[TESTE]" in capsys.readouterr().out
    assert (teste / "home/Emulation/roms/psx/J/a.bin").read_bytes() == b"abc"


# ------------------------------------------------------------------ pedido pelo Deck ----
LISTA = {"em": "2026-11-10", "emuladores_pc": {"duckstation": {"versao": None}},
         "jogos": [{"id": "psx-hercules", "titulo": "Hercules", "console": "psx", "emulador": "duckstation",
                    "tamanho": 391_000_000, "arquivos": 3, "resumo": {"jogo": {"arquivos": 2, "bytes": 390_000_000}}},
                   {"id": "switch2-dkb", "titulo": "Donkey Kong Bananza", "console": "switch2", "emulador": "lichii",
                    "tamanho": 19e9, "arquivos": 166443, "resumo": {}}]}


class FakeBot:
    def __init__(self):
        self.next_buttons = None
        self.cfg = {"notify_chat": 7}
        self.enviados = []

    def send(self, chat, txt):
        self.enviados.append((chat, txt))


def _lista(tmp_path, monkeypatch, d=LISTA):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    _w(R.jogos_pc_path(tmp_path), json.dumps(d))
    monkeypatch.setattr(R, "flatpak_info", SEM_FLATPAK)
    monkeypatch.setattr(T, "_acordar_pc", lambda bot: " Acordei o PC.")


def test_trazer_lista_resumo_e_fila(tmp_path, monkeypatch):
    _lista(tmp_path, monkeypatch)
    bot = FakeBot()
    assert "Hercules" in R.comando_trazer(bot, []) and "psx-hercules" in R.comando_trazer(bot, ["lista"])
    assert "Não achei" in R.comando_trazer(bot, ["zelda"])
    r = R.comando_trazer(bot, ["hercules"])
    assert "0.39 GB" in r and "vai ser instalado no Deck" in r and "DuckStation" in r
    assert bot.next_buttons == [("Trazer pro Deck", "/trazer psx-hercules enviar")]
    r = R.comando_trazer(bot, ["psx-hercules", "enviar"])
    assert "na fila para vir do PC" in r and "Acordei" in r
    fila = T.ler_fila()
    assert fila[0]["direcao"] == "pc->deck" and fila[0]["game_id"] == "psx-hercules"
    R.comando_trazer(bot, ["psx-hercules", "enviar"])
    assert len(T.ler_fila()) == 1  # não duplica
    T.enfileirar("psx-hercules", "Hercules")  # o mesmo id no outro sentido é outro pedido
    assert len(T.ler_fila()) == 2
    assert "Hercules: na fila" in R.comando_trazer(bot, ["fila"])
    T.marcar(fila[0]["id"], "pronto", "ok")
    T.notificar(bot)
    assert bot.enviados and "Do PC para o Deck" in bot.enviados[0][1]


def test_trazer_sem_lista(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    assert "Ainda não tenho a lista" in R.comando_trazer(FakeBot(), [])


def test_trazer_emulador_ja_no_deck(tmp_path, monkeypatch):
    _lista(tmp_path, monkeypatch)
    _w(tmp_path / "Applications/DuckStation-x64.AppImage")
    r = R.texto_jogo_pc(LISTA["jogos"][0], tmp_path, flatpak=SEM_FLATPAK)
    assert "emulador no Deck" in r and "vai ser instalado" not in r


def test_aviso_emulador_do_lado_do_pc(tmp_path, monkeypatch):
    _lista(tmp_path, monkeypatch)
    assert R.texto_emulador_lado_pc("duckstation", None) is None  # o PC tem
    t = R.texto_emulador_lado_pc("lichii", "build-83")
    assert "vai ser instalado no PC" in t and "build-83" in t and "github.com/zortos293/Lichii" in t
    assert "página oficial" in R.texto_emulador_lado_pc("dolphin", None)
    monkeypatch.setenv("DC_ROOT", str(tmp_path / "sem-lista"))
    assert R.texto_emulador_lado_pc("lichii", None) is None  # sem lista do PC: não sei, não afirmo


def test_enfileirar_direcao_invalida(tmp_path):
    with pytest.raises(ValueError):
        T.enfileirar("x", "X", tmp_path, direcao="para-lua")


def test_bot_roteia_trazer(tmp_path, monkeypatch):
    from dc import bot
    from dc.paths import get_paths
    x = bot.Bot(get_paths(tmp_path).ensure(), "T")
    x.cfg["allowed"] = [1]
    monkeypatch.setattr(R, "comando_trazer", lambda b, args: "ok " + " ".join(args))
    assert x.handle(1, 1, "/trazer hercules") == "ok hercules"
    assert "/trazer" in bot.HELP
