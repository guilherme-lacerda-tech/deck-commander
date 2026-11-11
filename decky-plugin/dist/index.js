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

// "Gerenciar → Remover jogo não Steam" no menu do jogo: pergunta NA TELA, como o "Desinstalar" do Steam, se
// apaga os arquivos também (vão para a quarentena por 30 dias). O bot não pergunta de novo pelo Telegram.
async function perguntarApagar(gid, nome) {
    const W = window.DFL || {};
    if (!W.showModal || !W.ConfirmModal) return;  // sem os componentes: o bot pergunta pelo Telegram
    let plano;
    try { plano = await painel("remover", { gid }); } catch (e) { return; }
    if (!plano || !plano.ok) return;
    try { await painel("removido_perguntado", { gid }); } catch (e) { /* o bot pergunta */ }
    W.showModal(SP_REACT.createElement(W.ConfirmModal, {
        strTitle: "Desinstalar " + nome + "?",
        strDescription: "Você tirou o jogo da biblioteca. Quer apagar os arquivos também e liberar o espaço?\n\n"
            + plano.texto.replace(/^Remover[^\n]*\n/, "").replace(/• atalho sai do Steam \(ao vivo\)\n?/, ""),
        strOKButtonText: "Apagar os arquivos",
        strCancelButtonText: "Manter os arquivos",
        onOK: async () => {
            const r = await painel("remover", { gid, confirmar: true });
            toaster.toast({ title: "Deck Commander", body: r && r.ok ? nome + " desinstalado (30 dias na quarentena)"
                : "Não deu para apagar: " + ((r && r.erro) || "erro") });
        },
    }));
}

async function reconcile() {
    let done;
    try { done = (await call("get_done")) || {}; } catch (e) { return; } // backend antigo: sem autocorreção
    for (const [gid, v] of Object.entries(done)) {
        if (!v.appid || !v.item) continue;
        if (exists(v.appid)) { seenThisSession.add(v.appid); continue; }
        if (seenThisSession.has(v.appid)) { // existia há pouco e sumiu: o usuário removeu pelo Steam
            try { await call("mark_removed", gid); note("removido por você: " + v.item.name); } catch (e) { /* backend antigo */ }
            perguntarApagar(gid, v.item.name);
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

// Jogo que não abriu (o Steam não mostra o motivo): o dc-launch deixa a explicação e ela vira aviso na tela.
async function showLaunchError() {
    let msg;
    try { msg = await call("get_launch_error"); } catch (e) { return; } // backend antigo
    if (msg) {
        toaster.toast({ title: "Deck Commander — o jogo não abriu", body: msg, duration: 8000 });
        note("não abriu: " + msg);
    }
}

// Remoções pedidas pelo /remover (só atalhos criados pelo Deck Commander: exe = dc-launch).
async function processRemovals() {
    let list;
    try { list = (await call("get_removals")) || []; } catch (e) { return; } // backend antigo
    for (const r of list) {
        const id = Number(r.appid) >>> 0;  // o AppID pode ter sido guardado com sinal (negativo): normaliza
        let ov = appStore.GetAppOverviewByAppID(id);
        if (!ov && r.name) ov = appStore.allApps.find((a) => a.display_name === r.name && a.app_type === 1073741824) || null;
        try {
            if (!ov) { note("não achei o atalho de " + r.game_id + " para remover (fica na fila)"); continue; }
            SteamClient.Apps.RemoveShortcut(ov.appid);
            seenThisSession.delete(ov.appid);
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
    const exact = new Set(spec.__exato__ || []);  // coleções que espelham a lista exatamente (ex.: "Em português")
    const ids = {};
    for (const [name, appids] of Object.entries(spec)) {
        if (name.startsWith("__")) continue;
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
        if (exact.has(name)) {
            const want = new Set(appids);
            const extra = [...col.apps.keys()].filter((a) => !want.has(a)).map((a) => appStore.GetAppOverviewByAppID(a)).filter(Boolean);
            if (extra.length) {
                col.AsDragDropCollection().RemoveApps(extra);
                await col.Save();
                note(name + ": -" + extra.length);
            }
        }
        ids[name] = col.id;
    }
    await call("set_collection_ids", ids);
}

async function cycle(force) {
    if (busy || (!force && !steamReady())) return;
    busy = true;
    for (const [label, fn] of [["avisos", showLaunchError], ["remoções", processRemovals], ["fila", processQueue], ["autocorreção", reconcile], ["coleções", syncCollections]]) {
        try {
            await fn();
        } catch (e) {
            note("erro (" + label + "): " + e);
        }
    }
    busy = false;
}

function runningAppId() {
    // jogo aberto agora (o painel do Deck abre por cima do jogo)
    try {
        const r = (window.DFL && window.DFL.Router) || (window.DeckyPluginLoader && window.DeckyPluginLoader.router);
        const a = r && r.MainRunningApp;
        if (a && a.appid) return a.appid;
    } catch (e) { /* sem jogo aberto */ }
    try {
        const apps = window.SteamUIStore && window.SteamUIStore.RunningApps;
        if (apps && apps.length) return apps[0].appid;
    } catch (e) { /* idem */ }
    return null;
}

const NOMES = { bateria: "🔋 Bateria", equilibrado: "⚖️ Equilibrado", qualidade: "✨ Qualidade" };
const NIVEL = (n) => (n === 1 ? "nativo" : n + "x");

function Btn(props) {
    return h("button", {
        className: "DialogButton",
        style: Object.assign({ margin: "2px", padding: "4px 8px", minWidth: "0", fontSize: "12px",
            outline: props.on ? "2px solid #1a9fff" : "none" }, props.style || {}),
        onClick: props.onClick,
    }, props.children);
}

function DesempenhoPanel() {
    const [g, setG] = SP_REACT.useState(null);
    const [adv, setAdv] = SP_REACT.useState(false);
    const [msg, setMsg] = SP_REACT.useState("");
    const load = async () => setG(await call("panel", runningAppId()));
    SP_REACT.useEffect(() => { load(); }, []);
    const act = async (fn, ...args) => { setMsg(await call(fn, ...args) || ""); await load(); };
    const row = (t, s) => h("div", { style: Object.assign({ padding: "3px 0", fontSize: "12px" }, s || {}) }, t);
    if (!g) return row("carregando…");
    if (!g.game_id) return row("Abra um jogo (ou jogue um) para ajustar a qualidade dele aqui.");
    const out = [h("div", { style: { fontWeight: "bold", fontSize: "13px", padding: "4px 0" } }, g.title || g.game_id)];
    if (!g.supported) {
        out.push(row("Este console ainda não tem ajuste de qualidade (roda na resolução do emulador)."));
    } else {
        const fase = { subindo: "calibrando: sobe um nível a cada medição lisa", fixo: "calibrado",
            manual: "manual (você escolheu)" }[g.auto_fase] || "calibra na primeira abertura";
        out.push(row("Qualidade: " + (g.override ? NIVEL(g.override) : "padrão") + " — " + fase +
            (g.trava_em ? " · travou em " + NIVEL(g.trava_em) : "")));
        out.push(h("div", null,
            h(Btn, { on: g.auto, onClick: () => act("set_auto", g.game_id) }, "🤖 Automático"),
            h(Btn, { onClick: () => act("calibrate", g.game_id) }, "Calibrar agora")));
    }
    if (g.history && g.history.length) {
        out.push(row("Últimas partidas:", { marginTop: "6px", fontWeight: "bold" }));
        g.history.forEach((t) => out.push(row(t, { whiteSpace: "pre-wrap", opacity: 0.9 })));
    } else {
        out.push(row("Ainda sem medição deste jogo.", { opacity: 0.8 }));
    }
    out.push(h(Btn, { style: { marginTop: "6px" }, onClick: () => setAdv(!adv) }, adv ? "Fechar avançado" : "Avançado…"));
    if (adv) {
        if (g.supported) {
            out.push(row("Fixar manualmente (desliga o automático deste jogo):"));
            out.push(h("div", null, ...g.presets.map((p) => h(Btn, { key: p, on: !g.auto && g.game_preset === p,
                onClick: () => act("set_game_preset", g.game_id, p) }, NOMES[p]))));
            out.push(row("Resolução exata deste jogo:"));
            out.push(h("div", null, ...g.levels.map((n) => h(Btn, { key: n, on: g.override === n,
                onClick: () => act("set_game_level", g.game_id, n) }, NIVEL(n)))));
            out.push(row("Padrão de TODOS os jogos deste console:"));
            out.push(h("div", null, ...g.presets.map((p) => h(Btn, { key: p, on: g.console_preset === p,
                onClick: () => act("set_console_preset", g.console, p) }, NOMES[p]))));
        }
        out.push(h(Btn, { on: g.measure, onClick: () => act("set_measure", !g.measure) },
            g.measure ? "Medir desempenho: ligado" : "Medir desempenho: desligado"));
    }
    if (msg) out.push(row(msg, { color: "#8bc34a" }));
    return h("div", null, ...out);
}

// Situação dos atalhos criados pelo plugin + desempenho do jogo aberto (tela "Biblioteca e desempenho").
function AtalhosPanel() {
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
        ...lastLog.map(row),
        h("div", { style: { borderTop: "1px solid #ffffff30", marginTop: "10px", paddingTop: "6px" } },
            h("div", { style: { fontWeight: "bold", fontSize: "14px" } }, "Desempenho e qualidade"),
            h(DesempenhoPanel, null)));
}

// ================================================================================================
// Interface completa (usável só com o controle): cada tela chama dc/painel.py pelo backend (main.py).
// ================================================================================================
const D = window.DFL || {};
const TEM_DFL = !!(D.PanelSection && D.PanelSectionRow && D.ButtonItem && D.ToggleField && D.TextField && D.DropdownItem);

async function painel(acao, args) {
    try {
        return (await call("painel", acao, args || {})) || { ok: false, erro: "sem resposta do plugin" };
    } catch (e) {
        return { ok: false, erro: "o plugin não respondeu (" + e + ")" };
    }
}

const Sec = (title, ...kids) => h(D.PanelSection, { title }, ...kids.flat(2).filter(Boolean));
const Row = (child, key) => h(D.PanelSectionRow, { key }, child);
// Texto: também é uma "parada" do direcional (Focusable). Sem isso a seta pula de botão em botão e o texto entre
// eles nunca entra na tela. Quebra palavra/caminho comprido em vez de cortar.
const ESTILO_TXT = { fontSize: "13px", whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word",
    padding: "4px 2px", lineHeight: "1.4" };
const Txt = (t, style, key) => Row(D.Focusable
    ? h(D.Focusable, { style: Object.assign({}, ESTILO_TXT, style || {}), onActivate: () => {} }, t)
    : h("div", { style: Object.assign({}, ESTILO_TXT, style || {}) }, t), key);
const Bt = (label, onClick, opts, key) => Row(h(D.ButtonItem, Object.assign({ layout: "below", onClick }, opts || {}), label), key);
const Toggle = (label, checked, onChange, description) => Row(h(D.ToggleField, { label, checked: !!checked, onChange, description }));
const Campo = (label, value, onChange, opts) => Row(h(D.TextField, Object.assign({ label, value: value || "",
    onChange: (e) => onChange(e.target.value) }, opts || {})));
const Lista = (label, opcoes, sel, onChange) => Row(h(D.DropdownItem, { label, rgOptions: opcoes, selectedOption: sel,
    strDefaultLabel: "Escolha…", onChange: (o) => onChange(o.data) }));
// Barra de progresso própria: o texto aparece inteiro (a do Steam corta com "…")
const Barra = (pct, texto, resto, key) => {
    const tem = pct !== null && pct !== undefined;
    const linhas = [h("div", { key: "t", style: { fontWeight: "bold" } }, texto + (tem ? " — " + pct + "%" : ""))];
    if (tem) linhas.push(h("div", { key: "b", style: { height: "6px", background: "#ffffff22", borderRadius: "3px",
        margin: "4px 0" } }, h("div", { style: { width: Math.max(0, Math.min(100, pct)) + "%", height: "100%",
        background: "#1a9fff", borderRadius: "3px" } })));
    if (resto) linhas.push(h("div", { key: "r", style: { opacity: 0.8 } }, resto));
    return Txt(linhas, null, key);
};
const Qr = (src) => src ? Row(h("img", { src, style: { width: "220px", height: "220px", display: "block",
    margin: "6px auto", imageRendering: "pixelated", background: "#fff" } })) : null;
const Msg = (m) => m ? Txt(m.erro ? "⚠️ " + m.erro : m.texto, { color: m.erro ? "#ff8a80" : "#8bc34a" }) : null;
const Carregando = (d) => !d ? Txt("carregando…") : (!d.ok ? Txt("⚠️ " + d.erro, { color: "#ff8a80" }) : null);

function confirmar(titulo, texto, okTxt, onOK) {
    if (!D.showModal || !D.ConfirmModal) { onOK(); return; }
    D.showModal(h(D.ConfirmModal, { strTitle: titulo, strDescription: texto, strOKButtonText: okTxt || "Confirmar",
        strCancelButtonText: "Cancelar", onOK }));
}

// Dados de uma ação (recarrega a cada `cada` ms enquanto a tela está aberta)
function useDados(acao, args, cada) {
    const [d, setD] = SP_REACT.useState(null);
    const vivo = SP_REACT.useRef(true);
    const carregar = async () => { const r = await painel(acao, args); if (vivo.current) setD(r); return r; };
    SP_REACT.useEffect(() => {
        vivo.current = true;
        carregar();
        const t = cada ? setInterval(carregar, cada) : null;
        return () => { vivo.current = false; if (t) clearInterval(t); };
    }, []);
    return [d, carregar];
}

// Executa uma ação com mensagem de resultado; trava os botões enquanto roda
function useAcao(recarregar) {
    const [msg, setMsg] = SP_REACT.useState(null);
    const [ocupado, setOcupado] = SP_REACT.useState(false);
    const fazer = async (acao, args) => {
        setOcupado(true);
        setMsg({ texto: "aguarde…" });
        const r = await painel(acao, args);
        setOcupado(false);
        setMsg(r.ok ? { texto: r.texto || "feito ✅" } : { erro: r.erro });
        if (recarregar) await recarregar();
        return r;
    };
    return [msg, ocupado, fazer, setMsg];
}

const semAcento = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const filtrar = (jogos, busca) => {
    const q = semAcento(busca).split(/\s+/).filter(Boolean);
    return jogos.filter((j) => { const t = semAcento(j.titulo + " " + j.console); return q.every((w) => t.includes(w)); });
};
const opcoesJogos = (jogos) => jogos.slice(0, 150).map((j) => ({ data: j.gid, label: j.titulo + " (" + j.console + ")" }));

// ---- 1. Início / Status -------------------------------------------------------------------------
function TelaInicio({ ir }) {
    const [d, recarregar] = useDados("status", {}, 10000);
    const [diag, setDiag] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    const menu = Sec("Configurar e usar",
        Bt("💬 Telegram", () => ir("telegram")),
        Bt("⬇️ Downloads", () => ir("downloads")),
        Bt("🈯 Tradução" + (d && d.perguntas ? " (" + d.perguntas + " pergunta" + (d.perguntas > 1 ? "s" : "") + ")" : ""), () => ir("traducao")),
        Bt("🖥️ PC (jogar os jogos do PC)", () => ir("pc")),
        Bt("📦 Transferir jogos (Deck ⇄ PC)", () => ir("transferir")),
        Bt("🎚️ Qualidade e controles", () => ir("qualidade")),
        Bt("🗑️ Desinstalar jogos", () => ir("desinstalar")),
        Bt("🎵 Música", () => ir("musica")),
        Bt("📚 Biblioteca e desempenho", () => ir("atalhos")));
    if (!d || !d.ok) return h("div", null, Sec("Status", Carregando(d)), menu);
    const ativos = d.downloads.filter((x) => !x.concluido);
    let diagRows = null;
    if (diag && diag !== "carregando") {
        diagRows = diag.ok
            ? [Txt(diag.problemas.length ? "Encontrei " + diag.problemas.length + " ponto(s) para ver:"
                : "✅ Tudo certo (" + diag.total + " verificações).", null, "dgt")]
                .concat(diag.problemas.map((p, i) => Txt("• " + p.problema + ": " + p.detalhe + (p.acao ? " → " + p.acao : ""), null, "dg" + i)))
            : Txt("⚠️ " + diag.erro, { color: "#ff8a80" });
    }
    return h("div", null,
        Sec("Status",
            d.safe_mode ? Txt("🛑 Modo seguro LIGADO: downloads e automações parados. " + (d.safe_motivo || ""), { color: "#ffb74d" }) : null,
            d.erro_downloads ? Txt("⚠️ " + d.erro_downloads, { color: "#ffb74d" }) : null,
            ativos.length ? ativos.map((x) => Barra(x.pct, x.nome, x.estado + (x.eta_min ? " · faltam ~" + x.eta_min + " min" : ""), x.hash))
                : Txt("Downloads: nada baixando agora (" + d.downloads.length + " concluído(s))."),
            d.downloads_pausados_energia ? Txt("🔌 Downloads esperando a tomada (" + d.motivo_energia + ")") : null,
            d.traducoes.map((t) => Barra(t.pct, "🈯 " + t.titulo, t.status + (t.eta ? " · " + t.eta : ""), t.op)),
            d.perguntas ? Txt("❓ Tem pergunta de tradução esperando você: abra Tradução.", { color: "#ffb74d" }) : null,
            Txt("💾 Espaço livre: " + d.espaco.map((e) => e.livre_gb + " GB " + e.onde).join(" · ")
                + (d.bateria !== null && d.bateria !== undefined ? "   🔋 " + d.bateria + "%" : "")),
            !diag ? Txt("🩺 O Diagnóstico confere se está tudo funcionando (backup, BIOS, emuladores, controles, "
                + "plugins, biblioteca) e lista o que ainda precisa da sua mão, com o que fazer. Ele só olha: não muda nada.",
                { opacity: 0.85 }, "dgx") : null,
            Bt(diag === "carregando" ? "Verificando… (até 1 min)" : "🩺 Verificar se está tudo certo", async () => {
                setDiag("carregando");
                setDiag(await painel("diagnostico"));
            }, { disabled: diag === "carregando" }),
            diagRows,
            Toggle("Modo seguro", d.safe_mode, (v) => confirmar(v ? "Ligar o modo seguro?" : "Desligar o modo seguro?",
                v ? "Para os downloads e as automações (nada é apagado). Use se algo estiver dando errado."
                  : "Religa os downloads e as automações.", v ? "Ligar" : "Desligar",
                () => fazer("safe_mode", { ligar: v })), "Desliga as automações sem apagar nada"),
            Msg(msg)),
        menu);
}

// ---- 2. Telegram --------------------------------------------------------------------------------
function TelaTelegram() {
    const [d, recarregar] = useDados("telegram");
    const [passo, setPasso] = SP_REACT.useState(null);  // null | {botfather} | {parear}
    const [token, setToken] = SP_REACT.useState("");
    const [msg, ocupado, fazer, setMsg] = useAcao();
    const salvarToken = async () => {
        const t = token;
        setToken("");  // o token não fica guardado na tela
        const r = await fazer("telegram_token", { token: t });
        if (r.ok) { setPasso({ parear: r }); setMsg({ texto: "✅ Bot @" + r.usuario + " configurado." }); recarregar(); }
    };
    const out = [];
    if (!d || !d.ok) out.push(Carregando(d));
    else {
        out.push(Txt(d.configurado ? ("Bot: " + (d.usuario ? "@" + d.usuario + " ✅" : "configurado (sem internet para conferir)"))
            : "Bot: ainda não configurado."));
        out.push(Txt("Celular ligado ao bot: " + (d.pareado ? "sim ✅" : "não") + (d.codigo_aberto ? " · código de pareamento aberto" : "")));
    }
    out.push(Bt(d && d.configurado ? "Configurar outro bot" : "Configurar bot", async () => {
        setMsg(null);
        const r = await painel("telegram_botfather");
        setPasso(r.ok ? { botfather: r } : null);
        if (!r.ok) setMsg({ erro: r.erro });
    }, { disabled: ocupado }));
    if (d && d.configurado) {
        out.push(Bt("Ligar um celular ao bot (QR)", async () => {
            const r = await fazer("telegram_parear");
            if (r.ok) { setPasso({ parear: r }); setMsg(null); }
        }, { disabled: ocupado }));
    }
    if (passo && passo.botfather) {
        out.push(Txt("PASSO 1 de 2 — criar o bot", { fontWeight: "bold" }));
        out.push(Qr(passo.botfather.qr));
        out.push(Txt(passo.botfather.passos));
        out.push(Campo("Token do bot", token, setToken, { bIsPassword: true, description: "Aperte A no campo para abrir o teclado" }));
        out.push(Bt("Salvar token", salvarToken, { disabled: ocupado || token.length < 20 }));
    }
    if (passo && passo.parear) {
        out.push(Txt("PASSO 2 de 2 — ligar o SEU celular", { fontWeight: "bold" }));
        out.push(Qr(passo.parear.qr));
        out.push(Txt(passo.parear.texto));
        out.push(Bt("Já toquei em INICIAR — conferir", async () => { await recarregar(); }));
    }
    out.push(Msg(msg));
    return Sec("Telegram", out);
}

// ---- 3. Downloads -------------------------------------------------------------------------------
function TelaDownloads() {
    const [d, recarregar] = useDados("downloads", {}, 10000);
    const [dups, setDups] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    const procurar = async () => { setDups({ carregando: true }); setDups(await painel("duplicados")); };
    const alvo = (it) => (it.hash ? { hash: it.hash, nome: it.titulo } : { gid: it.gid });
    const remover = async (it) => {
        const plano = await painel("remover", alvo(it));
        if (!plano.ok) { await fazer("remover", alvo(it)); return; }  // mostra o erro
        confirmar("Remover?", plano.texto, "Remover", async () => {
            await fazer("remover", Object.assign({ confirmar: true }, alvo(it)));
            procurar();
        });
    };
    if (!d || !d.ok) return Sec("Downloads", Carregando(d));
    const out = [];
    if (d.erro_downloads) out.push(Txt("⚠️ " + d.erro_downloads, { color: "#ffb74d" }));
    if (!d.downloads.length) out.push(Txt("Nenhum download na lista."));
    d.downloads.forEach((x) => {
        out.push(Barra(x.pct, x.nome, x.estado + (x.eta_min ? " · faltam ~" + x.eta_min + " min" : "")
            + (x.velocidade_kb ? " · " + x.velocidade_kb + " KB/s" : ""), "b" + x.hash));
        if (!x.concluido) out.push(Bt(x.pausado ? "▶ Retomar este" : "⏸ Pausar este",
            () => fazer(x.pausado ? "downloads_retomar" : "downloads_pausar", { hash: x.hash }), { disabled: ocupado }, "a" + x.hash));
    });
    if (d.downloads.some((x) => !x.concluido)) {
        out.push(Bt("⏸ Pausar todos", () => fazer("downloads_pausar"), { disabled: ocupado }));
        out.push(Bt("▶ Retomar todos", () => fazer("downloads_retomar"), { disabled: ocupado }));
    }
    if (d.downloads.some((x) => x.concluido)) out.push(Bt("🧹 Limpar concluídos da lista", () => confirmar(
        "Limpar a lista de downloads?", "Tira da lista os downloads que já terminaram e já estão na biblioteca. "
        + "Os jogos NÃO são apagados.", "Limpar", () => fazer("downloads_limpar")), { disabled: ocupado }, "limpar"));
    out.push(Toggle("Baixar fora da tomada", d.bateria_permitida, (v) => fazer("bateria", { permitir: v }),
        "Abaixo de " + d.bateria_minima + "% sempre pausa"));
    out.push(Msg(msg));
    const rep = [Bt(dups && dups.carregando ? "Procurando…" : "Procurar jogos repetidos", procurar, { disabled: !!(dups && dups.carregando) })];
    if (dups && dups.ok) {
        rep.push(Txt(dups.texto));
        dups.itens.forEach((it, i) => rep.push(Bt("🗑 Remover: " + it.titulo, () => remover(it), { disabled: ocupado }, "r" + i)));
        if (dups.itens.length) rep.push(Txt("Os arquivos ficam 30 dias na quarentena antes de sumir.", { opacity: 0.8 }));
    } else if (dups && dups.erro) rep.push(Txt("⚠️ " + dups.erro, { color: "#ff8a80" }));
    return h("div", null, Sec("Downloads", out), Sec("Repetidos", rep));
}

// ---- 4. Tradução --------------------------------------------------------------------------------
function TelaTraducao() {
    const [d, recarregar] = useDados("traducao", {}, 15000);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    if (!d || !d.ok) return Sec("Tradução", Carregando(d));
    const per = d.perguntas.length ? Sec("Perguntas", d.perguntas.map((p) => [
        Txt("🧩 " + p.texto, null, "t" + p.op),
        Bt("Sim, traduzir", () => fazer("traducao_responder", { op: p.op, sim: true }), { disabled: ocupado }, "s" + p.op),
        Bt("Não", () => fazer("traducao_responder", { op: p.op, sim: false }), { disabled: ocupado }, "n" + p.op)])) : null;
    const tar = Sec("Tarefas", d.tarefas.length ? d.tarefas.map((t) => [
        Txt(t.linha, null, "l" + t.op),
        t.pode_parar ? Bt("⏹ Parar " + t.titulo, () => confirmar("Parar a tradução?", "O que já foi traduzido fica guardado; "
            + "dá para retomar depois de onde parou.", "Parar", () => fazer("traducao_parar", { op: t.op })), { disabled: ocupado }, "p" + t.op) : null,
        t.pode_retomar ? Bt("▶ Retomar " + t.titulo, () => fazer("traducao_retomar", { op: t.op }), { disabled: ocupado }, "r" + t.op) : null,
    ]).concat([Bt("🧹 Limpar histórico", () => confirmar("Limpar o histórico de traduções?",
        "Tira da lista as tarefas que já acabaram (concluídas, falhas, recusadas). As traduções instaladas continuam "
        + "e nada que esteja rodando ou esperando você é tocado.", "Limpar", () => fazer("traducao_limpar")),
        { disabled: ocupado }, "limpar")]) : Txt("Nenhuma tradução ainda."));
    const jogos = Sec("Não traduzidos", d.nao_traduzidos.length
        ? d.nao_traduzidos.map((j) => Bt("Traduzir: " + j.titulo + " (" + j.console + ")", () => fazer("traduzir", { gid: j.gid }),
            { disabled: ocupado }, j.gid))
        : Txt("Nenhum jogo esperando tradução: tudo em português, traduzido, na fila ou sem tradutor automático."));
    return h("div", null,
        Sec("Tradução",
            Toggle("Traduzir sozinho", d.automatica, (v) => fazer("traducao_automatica", { ligar: v }),
                "Jogo novo que não está em português entra na fila"),
            Msg(msg)),
        per, tar, jogos);
}

// ---- 5. PC --------------------------------------------------------------------------------------
function TelaPC() {
    const [d, recarregar] = useDados("pc");
    const [f, setF] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    SP_REACT.useEffect(() => {
        if (d && d.ok && !f) setF({ host_casa: d.host_casa, rede_casa: d.rede_casa, mac: d.mac,
            host_tailscale: d.host_tailscale, porteiro: d.porteiro, codigo: "" });
    }, [d]);
    if (!d || !d.ok || !f) return Sec("PC", Carregando(d));
    const set = (k) => (v) => setF(Object.assign({}, f, { [k]: v }));
    return h("div", null,
        Sec("PC",
            Bt("📡 Testar conexão", () => fazer("pc_testar"), { disabled: ocupado }),
            Bt("⏰ Acordar PC", () => fazer("pc_acordar"), { disabled: ocupado }),
            Bt("📺 Jogar na TV (PC na TV)", () => confirmar("Pôr o PC na TV?", "Acorda o PC e muda a imagem dele para a TV "
                + "(só em casa). Para voltar à mesa, use o botão de energia do PC ou o atalho de sempre.", "Pôr na TV",
                () => fazer("pc_tv")), { disabled: ocupado }),
            Bt("🔄 Sincronizar jogos do PC", () => fazer("pc_sincronizar"), { disabled: ocupado }),
            Msg(msg)),
        Sec("Configuração do PC",
            Campo("IP do PC em casa", f.host_casa, set("host_casa"), { description: "ex.: 192.168.0.10" }),
            Campo("Rede de casa", f.rede_casa, set("rede_casa"), { description: "começo do IP, ex.: 192.168.0." }),
            Campo("MAC do PC", f.mac, set("mac"), { description: "ex.: AA:BB:CC:DD:EE:FF (para acordar em casa)" }),
            Campo("IP da Tailscale", f.host_tailscale, set("host_tailscale"), { description: "para jogar fora de casa (opcional)" }),
            Campo("Porteiro (opcional)", f.porteiro, set("porteiro"), { description: "aparelho que acorda o PC, ex.: http://…/acordar" }),
            Campo("Código do porteiro", f.codigo, set("codigo"), { bIsPassword: true,
                description: d.codigo_definido ? "já definido (deixe vazio para manter)" : "opcional" }),
            Bt("💾 Salvar", () => fazer("pc_salvar", f), { disabled: ocupado })),
        Sec("Jogos do PC (" + d.jogos.length + ")", d.jogos.length ? Txt(d.jogos.map((j) => "• " + j).join("\n"))
            : Txt("Nenhum ainda. Com o PC acordado, toque em Sincronizar.")));
}

// ---- 6. Transferências --------------------------------------------------------------------------
// Um sentido da transferência: busca, escolha, "o que vai junto" (tamanho, emulador do outro lado) e confirmar
function BlocoTransferir({ titulo, jogos, preparar, enviar, botao, pergunta, explica, vazio, recarregar }) {
    const [busca, setBusca] = SP_REACT.useState("");
    const [gid, setGid] = SP_REACT.useState(null);
    const [prep, setPrep] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    const achados = filtrar(jogos, busca);
    const escolher = async (g) => { setGid(g); setPrep({ carregando: true }); setPrep(await painel(preparar, { gid: g })); };
    if (!jogos.length) return Sec(titulo, Txt(vazio));
    return Sec(titulo,
        Campo("Buscar jogo", busca, setBusca, { description: achados.length + " jogo(s)" }),
        Lista("Jogo", opcoesJogos(achados), gid, escolher),
        prep && prep.carregando ? Txt("Vendo o que vai junto…") : null,
        prep && prep.ok ? [Txt("Tamanho: " + prep.tamanho + " em " + prep.arquivos + " arquivos", { fontWeight: "bold" }, "pt"),
            Txt(prep.resumo, { opacity: 0.9 }, "pr"),
            Bt(botao, () => confirmar(pergunta.replace("{jogo}", prep.titulo), explica, "Confirmar",
                () => fazer(enviar, { gid })), { disabled: ocupado }, "pe")] : null,
        prep && prep.erro ? Txt("⚠️ " + prep.erro, { color: "#ff8a80" }) : null,
        Msg(msg));
}

function TelaTransferir() {
    const [d, recarregar] = useDados("transferir", {}, 20000);
    if (!d || !d.ok) return Sec("Transferir jogos", Carregando(d));
    return h("div", null,
        h(BlocoTransferir, { key: "dp", titulo: "Do Deck para o PC", jogos: d.jogos, preparar: "transferir_preparar",
            enviar: "transferir_enviar", botao: "📦 Enviar pro PC", pergunta: "Enviar {jogo} para o PC?",
            explica: "O PC acorda, busca e copia sozinho (confere cada arquivo; instala o emulador no PC se faltar; nada é apagado no Deck).",
            vazio: "Nenhum jogo na biblioteca do Deck.", recarregar }),
        h(BlocoTransferir, { key: "pd", titulo: "Do PC para o Deck", jogos: d.jogos_pc || [], preparar: "trazer_preparar",
            enviar: "trazer_enviar", botao: "📥 Trazer pro Deck", pergunta: "Trazer {jogo} do PC?",
            explica: "O PC acorda e envia sozinho (confere cada arquivo; instala o emulador no Deck se faltar; backup do que já existir; nada é apagado no PC).",
            vazio: "A lista de jogos do PC ainda não chegou (ela vem quando o PC liga).", recarregar }),
        Sec("Fila", d.fila.length ? d.fila.map((e, i) => Txt("• " + (e.direcao === "pc->deck" ? "📥 " : "📦 ") + e.titulo
            + ": " + e.status, null, "f" + i)) : Txt("Nenhuma transferência pedida.")));
}

// ---- 7. Qualidade e controles -------------------------------------------------------------------
function TelaQualidade() {
    const [d, recarregar] = useDados("qualidade");
    const [busca, setBusca] = SP_REACT.useState("");
    const [gid, setGid] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    if (!d || !d.ok) return Sec("Qualidade", Carregando(d));
    const achados = filtrar(d.jogos, busca);
    const j = d.jogos.find((x) => x.gid === gid);
    const faltam = d.controles.filter((c) => !c.ok);
    return h("div", null,
        Sec("Qualidade por jogo",
            Campo("Buscar jogo", busca, setBusca, { description: achados.length + " jogo(s)" }),
            Lista("Jogo", opcoesJogos(achados), gid, setGid),
            j ? Lista("Resolução", j.niveis.map((n) => ({ data: n, label: n })), j.atual,
                (n) => fazer("qualidade_definir", { gid: j.gid, nivel: n })) : null,
            j ? Txt("Agora: " + j.atual + ". Vale a partir da próxima vez que abrir o jogo.") : null,
            Txt("Jogo pesado ou com gráfico estranho: escolha nativo. Padrão = o do console.", { opacity: 0.8 }),
            Msg(msg)),
        Sec("Botões A / B / X / Y", (d.layouts || []).length
            ? [Txt("Escolha como os botões funcionam em cada console:", null, "lh")].concat((d.layouts || []).map((l) =>
                Lista(l.emulador, Object.keys(l.opcoes).map((k) => ({ data: k, label: l.opcoes[k] })), l.atual,
                    (m) => fazer("controle_definir", { id: l.id, modo: m }))))
            : Txt("Nenhum emulador com escolha de botões aberto ainda (abra um jogo de Switch uma vez).")),
        Sec("Controles", faltam.length
            ? [Txt("Estes emuladores precisam que você escolha o controle UMA vez (no modo Desktop: abra o emulador → "
                + "Controles → escolha o controle do Deck):", null, "ch")].concat(faltam.map((c, i) => Txt("⚠️ " + c.emulador, null, "c" + i)))
            : Txt("✅ Todos os emuladores já reconhecem o controle.")));
}

// ---- 8. Desinstalar jogos (como o "Desinstalar" do Steam: sai da biblioteca e libera o espaço) ---------------
function TelaDesinstalar() {
    const [d, recarregar] = useDados("desinstalar_lista");
    const [busca, setBusca] = SP_REACT.useState("");
    const [gid, setGid] = SP_REACT.useState(null);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    const desinstalar = async (g) => {
        const plano = await painel("remover", { gid: g });
        if (!plano.ok) { await fazer("remover", { gid: g }); return; }  // mostra o erro
        confirmar("Desinstalar?", plano.texto, "Desinstalar", async () => {
            await fazer("remover", { gid: g, confirmar: true });
            setGid(null);
        });
    };
    if (!d || !d.ok) return Sec("Desinstalar jogos", Carregando(d));
    const achados = filtrar(d.jogos, busca);
    const j = d.jogos.find((x) => x.gid === gid);
    const lixo = d.tirados.filter((t) => !t.substituido);
    return h("div", null,
        Sec("Desinstalar jogos",
            Txt("Tira o jogo da biblioteca e libera o espaço. Por segurança os arquivos ficam 30 dias na quarentena "
                + "(dá para desfazer) e depois somem sozinhos.", { opacity: 0.85 }),
            Campo("Buscar jogo", busca, setBusca, { description: achados.length + " jogo(s)" }),
            Lista("Jogo", opcoesJogos(achados), gid, setGid),
            j ? Bt("🗑️ Desinstalar " + j.titulo, () => desinstalar(j.gid), { disabled: ocupado }, "d") : null,
            Msg(msg)),
        Sec("Tirados do Steam, mas ainda ocupando espaço", lixo.length
            ? lixo.map((t) => [
                Txt(t.titulo + " (" + t.console + ")", null, "t" + t.gid),
                Bt("🗑️ Apagar os arquivos", () => desinstalar(t.gid), { disabled: ocupado }, "a" + t.gid),
                Bt("↩ Trazer de volta para a biblioteca", () => fazer("devolver", { gid: t.gid }), { disabled: ocupado }, "v" + t.gid)])
            : Txt("Nenhum: tudo que você tirou do Steam já foi apagado.")),
        h(SugestoesEspaco, { desinstalar, fazer, ocupado }));
}

// Sugestões: jogos grandes que você não joga há 3+ meses (calcula só quando você pede: pode levar ~1 min)
function SugestoesEspaco({ desinstalar, fazer, ocupado }) {
    const [s, setS] = SP_REACT.useState(null);
    const ver = async () => { setS("carregando"); setS(await painel("espaco_sugestoes")); };
    return Sec("Liberar espaço",
        !s ? Bt("🔎 Ver jogos parados há 3+ meses", ver, null, "ver")
            : s === "carregando" ? Txt("Calculando tamanhos… (até 1 min)")
            : !s.ok ? Txt("⚠️ " + s.erro, { color: "#ff8a80" })
            : !s.itens.length ? Txt("✅ Nenhum jogo grande parado há mais de 3 meses.")
            : s.itens.map((it) => [
                Txt(it.texto, null, "s" + it.gid),
                Bt("📦 Levar para o PC", () => fazer("transferir_enviar", { gid: it.gid }), { disabled: ocupado }, "p" + it.gid),
                Bt("🗑️ Desinstalar", () => desinstalar(it.gid), { disabled: ocupado }, "d" + it.gid)]));
}

// ---- 9. Música (Spotify + volume do jogo × música) -----------------------------------------------
function TelaMusica() {
    const [d, recarregar] = useDados("musica", {}, 5000);
    const [msg, ocupado, fazer] = useAcao(recarregar);
    const [nome, setNome] = SP_REACT.useState("");
    const [link, setLink] = SP_REACT.useState("");
    if (!d || !d.ok) return Sec("Música", Carregando(d));
    const t = d.tocando;
    const vol = (tipo, rotulo) => d.volume[tipo] === null || d.volume[tipo] === undefined
        ? Txt(rotulo + ": nada tocando agora.", { opacity: 0.8 }, "v" + tipo)
        : Row(h(D.SliderField, { label: rotulo, value: d.volume[tipo], min: 0, max: 150, step: 5, showValue: true,
            onChange: (v) => fazer("musica_volume", { tipo, pct: v }) }), "v" + tipo);
    return h("div", null,
        Sec("Tocando agora",
            Txt(t && t.titulo ? (t.estado === "Playing" ? "▶ " : "⏸ ") + t.titulo + (t.artista ? " — " + t.artista : "")
                : "Nada tocando. Toque em ⏯ para abrir o Spotify."),
            Bt("⏯ Tocar / pausar", () => fazer("musica_midia", { acao: "tocar_pausar" }), { disabled: ocupado }, "pp"),
            Bt("⏭ Próxima", () => fazer("musica_midia", { acao: "proxima" }), { disabled: ocupado }, "nx"),
            Bt("⏮ Anterior", () => fazer("musica_midia", { acao: "anterior" }), { disabled: ocupado }, "pv"),
            Msg(msg)),
        Sec("Volume", D.SliderField ? [vol("jogo", "🎮 Jogo"), vol("musica", "🎵 Música")] : Txt("Volume: atualize o Decky.")),
        Sec("Playlists rápidas",
            d.playlists.length ? d.playlists.map((pl) => [
                Bt("🎵 " + pl.nome, () => fazer("musica_playlist", pl), { disabled: ocupado }, "p" + pl.nome),
                Bt("✖ tirar " + pl.nome, () => fazer("musica_salvar", { remover: pl.nome }), { disabled: ocupado }, "x" + pl.nome)])
                : Txt("Nenhuma ainda. No Spotify: playlist → Compartilhar → Copiar link, e cole abaixo."),
            Campo("Nome (ex.: Foco)", nome, setNome),
            Campo("Link da playlist", link, setLink),
            Bt("＋ Guardar playlist", async () => { await fazer("musica_salvar", { nome, uri: link }); setNome(""); setLink(""); },
                { disabled: ocupado || !nome || !link }, "add")));
}

const TELAS = { telegram: TelaTelegram, downloads: TelaDownloads, traducao: TelaTraducao, pc: TelaPC, musica: TelaMusica,
    transferir: TelaTransferir, qualidade: TelaQualidade, desinstalar: TelaDesinstalar, atalhos: AtalhosPanel };

function Panel() {
    const [tela, setTela] = SP_REACT.useState(null);
    // Dentro de uma tela do painel, o botão B e a seta "←" do topo chamam o "fechar plugin" do próprio Decky
    // (deckyState.closeActivePlugin). Enquanto uma tela está aberta, esse "fechar" volta ao menu do Deck
    // Commander; no menu (ou ao sair do painel) o comportamento original do Decky volta.
    SP_REACT.useEffect(() => {
        const st = window.DeckyPluginLoader && window.DeckyPluginLoader.deckyState;
        if (!st || !tela) return undefined;
        st.closeActivePlugin = () => setTela(null);   // propriedade da instância cobre a do protótipo
        if (st.notifyUpdate) st.notifyUpdate();       // o Decky religa os botões com a função nova
        return () => {
            delete st.closeActivePlugin;
            if (st.notifyUpdate) st.notifyUpdate();
        };
    }, [tela]);
    if (!TEM_DFL) return h(AtalhosPanel, null);  // Decky sem os componentes: só o painel antigo
    if (!tela || !TELAS[tela]) return h(TelaInicio, { ir: setTela });
    return h("div", null,
        h(D.PanelSection, null, h(D.PanelSectionRow, null, h(D.ButtonItem, { layout: "below", onClick: () => setTela(null) }, "← Voltar"))),
        h(TELAS[tela], null));
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
