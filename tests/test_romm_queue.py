import json
from contextlib import closing

from dc import romm_queue
from dc.paths import get_paths
from dc.romm_client import RommClient, RommError


def test_indisponibilidade_retomada_e_publicacao_durante_scan(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "cliente").ensure()
    root = tmp_path / "roms"
    root.mkdir()
    jogo = root / "homebrew.nes"
    jogo.write_bytes(b"original")
    fora = tmp_path / "fora.nes"
    fora.write_bytes(b"outro")
    (p.config / "romm.json").write_text(json.dumps({"url": "http://localhost:8080", "roms_root": str(root)}))
    (p.secrets / "romm-token").write_text("teste")
    assert not romm_queue.published(p, [fora])
    assert romm_queue.published(p, [jogo])
    respostas = iter([503, "primeira", "segunda"])
    def iniciar(self):
        result = next(respostas)
        if result == 503:
            raise RommError("sem worker", result)
        return {"task_id": result}
    monkeypatch.setattr(RommClient, "iniciar_scan", iniciar)
    monkeypatch.setattr(RommClient, "consultar_tarefa", lambda self, id: {"task_id": id, "status": "finished"})
    def estado():
        with closing(romm_queue._db(p)) as db:
            return dict(db.execute("SELECT * FROM scan").fetchone())
    romm_queue.tick(p, 10)
    assert estado()["error"] == "sem worker" and estado()["completed"] == 0
    romm_queue.tick(p, 14)
    assert estado()["task"] is None
    romm_queue.tick(p, 15)
    assert estado()["task"] == "primeira"
    traduzido = root / "homebrew (PT-BR).nes"
    traduzido.write_bytes(b"traduzido")
    romm_queue.published(p, [traduzido])
    romm_queue.tick(p, 20)
    assert estado()["completed"] == 1 and estado()["requested"] == 2
    romm_queue.tick(p, 21)
    assert estado()["task"] == "segunda"
    romm_queue.tick(p, 26)
    assert estado()["completed"] == 2 and estado()["error"] is None
