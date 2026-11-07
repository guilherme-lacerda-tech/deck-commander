// Deck Commander — plugin do Decky (JS puro, sem build).
// Cria atalhos ao vivo com a API interna do Steam (a mesma do "Adicionar jogo não-Steam"), aplica as
// capas, mantém as coleções por console/loja (o TabMaster acompanha coleções ao vivo) e se autocorrige:
// se um atalho que ele criou sumir (ex.: reinício antes de o Steam gravar), ele recria sozinho.
// Se VOCÊ remover um atalho dele pelo Steam (estava lá nesta sessão e sumiu), isso é respeitado: não volta.
// Só remove atalhos criados por ele, e só quando pedido (/remover no bot).
const manifest = {"name":"Deck Commander"};
const conn = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!conn) {
    throw new Error('[Deck Commander] loader API indisponível');
}
let api;
try {
    api = conn.connect(2, manifest.name);
}
catch {
    api = conn.connect(1, manifest.name);
}
const call = api.call;
const toaster = api.toaster;
const definePlugin = (fn) => (...args) => fn(...args);
const h = SP_REACT.createElement;

// ELibraryAssetType do Steam: 0 capa vertical, 1 fundo (hero), 2 logo, 3 capa horizontal
const ASSET = { p: 0, hero: 1, logo: 2, wide: 3 };
const unquote = (s) => (s || "").replace(/^"(.*)"$/, "$1");
const CYCLE_MS = 10000;
const STARTUP_GRACE_MS = 45000; // o Steam ainda carrega a biblioteca logo depois de ligar

let busy = false;
let timer = null;
let loadedAt = Date.now();
let lastLog = [];
// Trava contra duplicação: game_id -> AppID criado nesta sessão. Só impede criar de novo enquanto aquele
// atalho AINDA existe (jogo removido e baixado de novo na mesma sessão volta normalmente).
const addedThisSession = new Map();
const seenThisSession = new Set();  // AppIDs vistos existindo nesta sessão (sumiu depois = remoção do usuário)

function note(msg) {
    lastLog = [new Date().toLocaleTimeString() + " " + msg, ...lastLog].slice(0, 8);
}

// Pronto = biblioteca carregada (há apps na coleção "todos") e passou a carência de inicialização.
function steamReady() {
    try {
        const all = collectionStore.allAppsCollection || collectionStore.allGamesCollection;
        return Date.now() - loadedAt > STARTUP_GRACE_MS && all && all.allApps && all.allApps.length > 0;
    } catch (e) {
        return false;
    }
}

const exists = (appid) => !!(appid && appStore.GetAppOverviewByAppID(appid));

async function addOne(it) {
    const appid = await SteamClient.Apps.AddShortcut(it.name, unquote(it.exe), unquote(it.start_dir), it.launch_options);
    if (typeof appid !== "number" || !appid) {
        throw new Error("o Steam não devolveu o AppID");
    }
    // garante nome/caminho/opções exatos (o AddShortcut pode derivar o nome do executável)
    SteamClient.Apps.SetShortcutName(appid, it.name);
    SteamClient.Apps.SetShortcutExe(appid, it.exe);
    SteamClient.Apps.SetShortcutStartDir(appid, it.start_dir);
    SteamClient.Apps.SetAppLaunchOptions(appid, it.launch_options);
    for (const [kind, path] of Object.entries(it.art || {})) {
        try {
            const img = await call("read_art", path);
            if (img && ASSET[kind] !== undefined) {
                await SteamClient.Apps.SetCustomArtworkForApp(appid, img.data, img.ext, ASSET[kind]);
            }
        } catch (e) {
            note("capa falhou: " + it.name);
        }
    }
    return appid;
}

async function processQueue() {
    const items = (await call("get_pending")) || [];
    for (const it of items) {
        const prev = addedThisSession.get(it.game_id);
        if (prev && exists(prev)) { // já criado (o registro é que não chegou ao backend): só registra de novo
            try { await call("report", it.game_id, prev, ""); } catch (e) { /* tenta no próximo ciclo */ }
            continue;
        }
        try {
            const appid = await addOne(it);
            addedThisSession.set(it.game_id, appid);
            seenThisSession.add(appid);
            await call("report", it.game_id, appid, "");
            await remember(it);
            note("adicionado: " + it.name);
            toaster.toast({ title: "Deck Commander", body: it.name + " adicionado à biblioteca" });
        } catch (e) {
            await call("report", it.game_id, 0, String(e));
            note("erro: " + it.name + " — " + e);
        }
    }
}

// Autocorreção: atalho criado por nós que não existe mais no Steam é recriado (uma vez por ciclo).
// guarda o item para a autocorreção (backend novo); com backend antigo apenas ignora
async function remember(it) {
    try { await call("remember_item", it.game_id, it); } catch (e) { /* backend antigo */ }
}

async function reconcile() {
    let done;
    try { done = (await call("get_done")) || {}; } catch (e) { return; } // backend antigo: sem autocorreção
    for (const [gid, v] of Object.entries(done)) {
        if (!v.appid || !v.item) continue;
        if (exists(v.appid)) { seenThisSession.add(v.appid); continue; }
        if (seenThisSession.has(v.appid)) { // existia há pouco e sumiu: o usuário removeu pelo Steam
            try { await call("mark_removed", gid); note("removido por você: " + v.item.name); } catch (e) { /* backend antigo */ }
            continue;
        }
        try {
            if (addedThisSession.has("re:" + gid)) continue; // recria no máximo 1x por sessão
            addedThisSession.set("re:" + gid, 0);
            const appid = await addOne(v.item);
            addedThisSession.set(gid, appid);
            seenThisSession.add(appid);
            await call("report", gid, appid, "");
            note("recriado: " + v.item.name);
        } catch (e) {
            note("falha ao recriar " + gid + ": " + e);
        }
    }
}

// Remoções pedidas pelo /remover (só atalhos criados pelo Deck Commander: exe = dc-launch).
async function processRemovals() {
    let list;
    try { list = (await call("get_removals")) || []; } catch (e) { return; } // backend antigo
    for (const r of list) {
        const ov = appStore.GetAppOverviewByAppID(r.appid);
        try {
            if (ov) SteamClient.Apps.RemoveShortcut(r.appid);
            seenThisSession.delete(r.appid);
            await call("removal_done", r.game_id, r.appid);
            note("removido: " + (ov ? ov.display_name : r.game_id));
            if (ov) toaster.toast({ title: "Deck Commander", body: ov.display_name + " removido da biblioteca" });
        } catch (e) {
            note("falha ao remover " + r.game_id + ": " + e);
        }
    }
}

// Coleções do Steam por console/loja. Só ACRESCENTA jogos; nunca remove nada de coleção nenhuma.
async function syncCollections() {
    const spec = (await call("get_collections")) || {};
    const ids = {};
    for (const [name, appids] of Object.entries(spec)) {
        let col = collectionStore.GetUserCollectionsByName(name)[0];
        if (!col) {
            col = collectionStore.NewUnsavedCollection(name, undefined, []);
            await col.Save();
            col = collectionStore.GetUserCollectionsByName(name)[0] || col;
            note("coleção criada: " + name);
        }
        const missing = appids.filter((a) => !col.apps.has(a)).map((a) => appStore.GetAppOverviewByAppID(a)).filter(Boolean);
        if (missing.length) {
            col.AsDragDropCollection().AddApps(missing);
            await col.Save();
            note(name + ": +" + missing.length);
        }
        ids[name] = col.id;
    }
    await call("set_collection_ids", ids);
}

async function cycle(force) {
    if (busy || (!force && !steamReady())) return;
    busy = true;
    for (const [label, fn] of [["remoções", processRemovals], ["fila", processQueue], ["autocorreção", reconcile], ["coleções", syncCollections]]) {
        try {
            await fn();
        } catch (e) {
            note("erro (" + label + "): " + e);
        }
    }
    busy = false;
}

function Panel() {
    const [st, setSt] = SP_REACT.useState(null);
    const refresh = async () => setSt(await call("get_status"));
    SP_REACT.useEffect(() => { refresh(); }, []);
    const row = (t) => h("div", { style: { padding: "4px 0", fontSize: "13px" } }, t);
    return h("div", { style: { padding: "8px 16px" } },
        row(st ? ("Na fila: " + st.pending + " · na biblioteca: " + st.added) : "carregando…"),
        st && st.errors.length ? row("Com erro: " + st.errors.join(", ")) : null,
        row(steamReady() ? "Steam pronto" : "aguardando o Steam terminar de carregar…"),
        h("button", {
            className: "DialogButton",
            style: { marginTop: "8px" },
            onClick: async () => { await cycle(true); await refresh(); },
        }, "Verificar agora"),
        ...lastLog.map(row));
}

var index = definePlugin(() => {
    loadedAt = Date.now();
    timer = setInterval(() => cycle(false), CYCLE_MS);
    return {
        name: "Deck Commander",
        titleView: h("div", null, "Deck Commander"),
        content: h(Panel, null),
        icon: h("span", { style: { fontSize: "18px" } }, "🎮"),
        onDismount() {
            clearInterval(timer);
        },
    };
});

export { index as default };
