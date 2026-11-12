#!/usr/bin/env python3
"""Cria/atualiza as coleções do Steam agora (mesma lógica do plugin) e aponta as abas do TabMaster
para elas. Só acrescenta jogos às coleções; nunca remove."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cef_eval import ws_eval  # noqa: E402

from dc import tabs, vdf  # noqa: E402
from dc.paths import get_paths  # noqa: E402

paths = get_paths()
from dc.steam import shortcuts_path  # noqa: E402

sc = shortcuts_path()
lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
spec = tabs.write_collections(paths.data, vdf.read_shortcuts(sc), lm)
js = """(async (spec) => {
  const ids = {}, added = {};
  for (const [name, appids] of Object.entries(spec)) {
    let col = collectionStore.GetUserCollectionsByName(name)[0];
    if (!col) { col = collectionStore.NewUnsavedCollection(name, undefined, []); await col.Save();
                col = collectionStore.GetUserCollectionsByName(name)[0] || col; }
    const missing = appids.filter(a => !col.apps.has(a)).map(a => appStore.GetAppOverviewByAppID(a)).filter(Boolean);
    if (missing.length) { col.AsDragDropCollection().AddApps(missing); await col.Save(); }
    ids[name] = col.id; added[name] = [missing.length, col.apps.size];
  }
  return {ids, added};
})(%s)""" % json.dumps(spec)
res = ws_eval(js)
(paths.data / "collection-ids.json").write_text(json.dumps(res["ids"], ensure_ascii=False, indent=1), "utf-8")
for name, (n, total) in res["added"].items():
    print(f"{name}: +{n} (total {total})")
print(tabs.apply(vdf.read_shortcuts(sc), lm, sc.parents[1].name, data_dir=paths.data) or "abas já atualizadas")
