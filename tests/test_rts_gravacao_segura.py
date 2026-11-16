"""Gravação segura do RomTranslate (defeitos achados em 14/11/2026 num jogo de NES que travou depois do Start).
Tudo aqui é sintético: uma ROM falsa montada no teste, com menu de opções em sequência, falas e terminadores 0x00."""
from pathlib import Path

from dc.traducao.rts import _rom_bytes, ajustar, codec_de, espaco_original, fragmento

# Menu em sequência, como muitos jogos guardam: [cabeçalho de 2 bytes][texto][0x00][cabeçalho][texto][0x00]...
MENU = b"\x22\x8aStart New Game\x00\x22\xcaLoad Saved Game\x00\x22\xeaGame Options\x00\xff"
FALAS = b"\x91\x83Thanks for playing!\x00\x91\x83the world is safe now.\x00\xd7al level is here!\x00"
BASE = 0x110


def rom_falsa() -> bytes:
    corpo = bytearray(b"\xff" * 0x400)
    dados = MENU + FALAS
    corpo[BASE:BASE + len(dados)] = dados
    return bytes(corpo)


def entrada(rom: bytes, texto: str) -> dict:
    off = rom.index(texto.encode())
    return {"id": f"scan-{off:08x}", "offset": off, "sourceText": texto, "maxBytes": None, "encoding": "ascii",
            "originalBytes": texto.encode().hex()}


def gravar_como_romtranslate(rom: bytes, e: dict, traducao: str) -> bytes:
    """O que o RomTranslate faz (conferido no Deck com uma ROM falsa): escreve a tradução no lugar e completa o
    resto do espaço original com 0x00."""
    b = bytearray(rom)
    n = len(bytes.fromhex(e["originalBytes"]))
    t = traducao.encode("ascii")
    b[e["offset"]:e["offset"] + n] = t + b"\x00" * (n - len(t))
    return bytes(b)


def ler_menu(rom: bytes) -> list[str]:
    """Como o jogo lê o menu: pula o cabeçalho de 2 bytes, lê até o 0x00, e a próxima opção começa logo depois."""
    i, opcoes = BASE, []
    while rom[i] == 0x22:
        fim = rom.index(b"\x00", i + 2)
        opcoes.append(rom[i + 2:fim].decode("ascii", "replace"))
        i = fim + 1
    return opcoes


def test_rom_falsa_menu_original():
    assert ler_menu(rom_falsa()) == ["Start New Game", "Load Saved Game", "Game Options"]


def test_defeito_antigo_zeros_a_mais_quebram_o_menu():
    """Reproduz a falha: tradução curta completada com 0x00 deixa o menu sem as opções seguintes."""
    rom = rom_falsa()
    rom2 = gravar_como_romtranslate(rom, entrada(rom, "Start New Game"), "Jogo novo")
    assert ler_menu(rom2) != ["Jogo novo", "Load Saved Game", "Game Options"]


def test_traducao_curta_completada_com_espacos_mantem_o_menu():
    rom = rom_falsa()
    for orig, pt in [("Start New Game", "Jogo novo"), ("Load Saved Game", "Carregar jogo"), ("Game Options", "Opcoes")]:
        e = entrada(rom, orig)
        t = ajustar(pt, espaco_original(e, "ascii"), "ascii")
        assert t is not None and len(t) == len(orig)
        rom = gravar_como_romtranslate(rom, e, t)
    assert [o.rstrip() for o in ler_menu(rom)] == ["Jogo novo", "Carregar jogo", "Opcoes"]
    assert len(rom) == len(rom_falsa())


def test_terminador_nunca_e_apagado():
    rom = rom_falsa()
    e = entrada(rom, "Game Options")
    assert ajustar("Opcoes do jogo", espaco_original(e, "ascii"), "ascii") is None  # não cabe: fica o original
    t = ajustar("Opcoes", espaco_original(e, "ascii"), "ascii")
    rom2 = gravar_como_romtranslate(rom, e, t)
    fim = e["offset"] + len("Game Options")
    assert rom2[fim] == 0 and rom2[fim + 1:] == rom[fim + 1:]


def test_maxbytes_vazio_ou_maior_nao_libera_espaco_alem_da_frase():
    e = {"sourceText": "Game Options", "originalBytes": b"Game Options".hex(), "maxBytes": None}
    assert espaco_original(e, "ascii") == 12
    e["maxBytes"] = 40
    assert espaco_original(e, "ascii") == 12
    e["maxBytes"] = 10
    assert espaco_original(e, "ascii") == 10
    assert espaco_original({"sourceText": "Oi"}, "ascii") == 2


def test_traducao_com_zero_tab_ou_quebra_e_recusada():
    for t in ["Oi\x00x", "Oi\tx", "Oi\nx"]:
        assert ajustar(t, 10, "ascii") is None


def test_utf16_completa_com_espaco_de_dois_bytes():
    t = ajustar("Sim", 10, "utf-16-le")
    assert t == "Sim  " and len(t.encode("utf-16-le")) == 10
    assert ajustar("Sim", 9, "utf-16-le") is None
    assert codec_de("utf16_le") == "utf-16-le" and codec_de("ascii") == "ascii" and codec_de("") == "ascii"


def test_pedaco_de_frase_e_recusado():
    rom = rom_falsa()
    assert fragmento(entrada(rom, "the world is safe now."), rom)  # continuação de linha (minúscula)
    assert fragmento(entrada(rom, "al level is here!"), rom)  # começo comprimido em \xd7
    assert not fragmento(entrada(rom, "Thanks for playing!"), rom)
    assert not fragmento(entrada(rom, "Start New Game"), rom)


def test_pedaco_cortado_no_meio_da_palavra_pelo_byte_anterior():
    rom = rom_falsa()
    cortado = {"sourceText": "Ame Options", "offset": rom.index(b"ame Options")}
    assert fragmento(cortado, rom)  # o byte anterior é "G": a palavra foi cortada
    inteiro = {"sourceText": "Saved Game", "offset": rom.index(b"Saved Game")}
    assert not fragmento(inteiro, rom)  # antes vem espaço


def test_disco_nao_le_bytes(tmp_path: Path):
    iso = tmp_path / "jogo.iso"
    iso.write_bytes(b"x" * 10)
    nes = tmp_path / "jogo.nes"
    nes.write_bytes(b"NES\x1a")
    assert _rom_bytes(iso) is None and _rom_bytes(nes) == b"NES\x1a"
