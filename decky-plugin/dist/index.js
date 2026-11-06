// Deck Commander — plugin do Decky (JS puro, sem build).
// Cria atalhos ao vivo com a API interna do Steam (a mesma que o "Adicionar jogo não-Steam" usa),
// aplica as capas e avisa na tela. Nunca remove nem altera atalhos que não estão na fila do Deck Commander.
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

let busy = false;
let timer = null;
let lastLog = [];

function note(msg) {
    lastLog = [new Date().toLocaleTimeString() + " " + msg, ...lastLog].slice(0, 6);
}

async function addOne(it) {
    let appid = await SteamClient.Apps.AddShortcut(it.name, unquote(it.exe), unquote(it.start_dir), it.launch_options);
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
    if (busy) return;
    busy = true;
    try {
        const items = (await call("get_pending")) || [];
        for (const it of items) {
            try {
                const appid = await addOne(it);
                await call("report", it.game_id, appid, "");
                note("adicionado: " + it.name);
                toaster.toast({ title: "Deck Commander", body: it.name + " adicionado à biblioteca" });
            } catch (e) {
                await call("report", it.game_id, 0, String(e));
                note("erro: " + it.name + " — " + e);
            }
        }
    } catch (e) {
        note("erro na fila: " + e);
    } finally {
        busy = false;
    }
}

function Panel() {
    const [st, setSt] = SP_REACT.useState(null);
    const refresh = async () => setSt(await call("get_status"));
    SP_REACT.useEffect(() => { refresh(); }, []);
    const row = (t) => h("div", { style: { padding: "4px 0", fontSize: "13px" } }, t);
    return h("div", { style: { padding: "8px 16px" } },
        row(st ? ("Na fila: " + st.pending + " · adicionados: " + st.added) : "carregando…"),
        st && st.errors.length ? row("Com erro: " + st.errors.join(", ")) : null,
        h("button", {
            className: "DialogButton",
            style: { marginTop: "8px" },
            onClick: async () => { await processQueue(); await refresh(); },
        }, "Verificar agora"),
        ...lastLog.map(row));
}

var index = definePlugin(() => {
    timer = setInterval(processQueue, 10000);
    setTimeout(processQueue, 3000);
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
