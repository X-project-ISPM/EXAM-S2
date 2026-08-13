import os
import json
import requests
import streamlit as st
import time

st.set_page_config(
    page_title="Service Desk AI Orchestrator",
    layout="wide",
    initial_sidebar_state="expanded",
)

API = os.getenv("API_URL", "https://exam-s2.onrender.com")

# --- SVG Icons Dictionary (Strictly vector SVG, zero emojis) ---
SVG = {
    "server": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>',
    "check": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    "cross": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
    "alert": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
    "user": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    "book": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>',
    "tool": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
    "cpu": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="15" x2="23" y2="15"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="15" x2="4" y2="15"></line></svg>',
    "activity": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>',
    "database": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M21 19c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14"></path><path d="M21 5v14"></path></svg>',
    "terminal": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>',
    "shield": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
    "file": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>',
}

# Enlarged Donut Ring Metric Component (Clean HTML without Markdown code block indentation)
def render_donut_metric(value, label, percent, color_hex):
    r = 30
    c = 2 * 3.14159 * r
    offset = c * (1 - min(percent, 100) / 100)

    val_str = str(value)
    if len(val_str) > 6:
        font_sz = "0.75rem"
    elif len(val_str) > 4:
        font_sz = "0.85rem"
    else:
        font_sz = "1.1rem"

    return f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 8px; height:135px; display:flex; flex-direction:column; justify-content:center; align-items:center; box-shadow:0 1px 3px rgba(0,0,0,0.03); box-sizing:border-box;"><div style="position:relative; width:74px; height:74px; margin:0 auto 6px auto;"><svg width="74" height="74" viewBox="0 0 80 80"><circle cx="40" cy="40" r="{r}" fill="none" stroke="#f1f5f9" stroke-width="6.5" /><circle cx="40" cy="40" r="{r}" fill="none" stroke="{color_hex}" stroke-width="6.5" stroke-dasharray="{c}" stroke-dashoffset="{offset}" stroke-linecap="round" transform="rotate(-90 40 40)" /></svg><div style="position:absolute; top:0; left:0; width:74px; height:74px; display:flex; align-items:center; justify-content:center; font-size:{font_sz}; font-weight:700; color:#1e293b; white-space:nowrap; padding:0 2px;">{value}</div></div><div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; color:#64748b; letter-spacing:0.04em; text-align:center;">{label}</div></div>'

# Interactive Bar Chart Widget Component with Hover Tooltips (Clean HTML without Markdown code block indentation)
def render_bar_chart_widget():
    bars_data = [
        {"day": "Lundi", "count": 4, "height": "40%", "color": "#cbd5e1"},
        {"day": "Mardi", "count": 8, "height": "65%", "color": "#0ea5e9"},
        {"day": "Mercredi", "count": 5, "height": "45%", "color": "#cbd5e1"},
        {"day": "Jeudi", "count": 12, "height": "85%", "color": "#14b8a6"},
        {"day": "Vendredi", "count": 7, "height": "60%", "color": "#0ea5e9"},
        {"day": "Samedi", "count": 15, "height": "100%", "color": "#8b5cf6"},
        {"day": "Dimanche", "count": 9, "height": "75%", "color": "#14b8a6"},
    ]

    bars_html = "".join([
        f'<div class="bar-item" title="{b["day"]} : {b["count"]} tickets traités" style="width:12%; height:{b["height"]}; background:{b["color"]}; border-radius:4px; position:relative; cursor:pointer;"><div class="bar-tooltip">{b["day"]}<br><b>{b["count"]} tickets</b></div></div>'
        for b in bars_data
    ])

    return f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px; height:135px; box-sizing:border-box; display:flex; flex-direction:column; justify-content:center;"><div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:10px; text-align:center;">Activité Support / Jour</div><div style="display:flex; align-items:flex-end; justify-content:center; gap:6px; height:65px;">{bars_html}</div></div>'

# Helper: Chargement des données de test locales
def charger_donnees_locales(nom_fichier):
    chemins = [
        os.path.join(os.path.dirname(__file__), "..", "backend", "data", nom_fichier),
        os.path.join(os.path.dirname(__file__), "data", nom_fichier),
        os.path.join("backend", "data", nom_fichier),
        os.path.join("data", nom_fichier),
    ]
    for c in chemins:
        if os.path.exists(c):
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []

# Custom CSS Styling (Hover Tooltips & Card Alignment)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background-color: #f8fafc;
    }

    /* Sidebar Dark Styling */
    [data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-right: 1px solid #334155;
    }
    [data-testid="stSidebar"] * {
        color: #cbd5e1 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {
        color: #f8fafc !important;
        font-weight: 700;
    }
    
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
    }

    /* Sidebar User Profile Card */
    .user-profile-card {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 14px;
        background: #0f172a;
        border-radius: 10px;
        margin-bottom: 20px;
        border: 1px solid #334155;
    }
    .user-avatar {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: #0ea5e9;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.95rem;
    }
    .user-info-name {
        color: #f8fafc !important;
        font-weight: 600;
        font-size: 0.9rem;
        line-height: 1.2;
    }
    .user-info-role {
        color: #64748b !important;
        font-size: 0.75rem;
    }

    /* Category Dots */
    .cat-dot-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.82rem;
        margin-bottom: 8px;
        color: #cbd5e1 !important;
    }
    .dot-blue { width: 8px; height: 8px; border-radius: 50%; background: #3b82f6; display: inline-block; }
    .dot-teal { width: 8px; height: 8px; border-radius: 50%; background: #14b8a6; display: inline-block; }
    .dot-amber { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; display: inline-block; }
    .dot-rose { width: 8px; height: 8px; border-radius: 50%; background: #f43f5e; display: inline-block; }

    /* Page Titles */
    .page-title-main {
        font-size: 1.35rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }
    .page-subtitle-main {
        font-size: 0.85rem;
        color: #64748b;
        margin: 2px 0 0 0;
    }

    /* Property Table Card */
    .prop-table-card {
        background: #ffffff;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        margin-bottom: 20px;
    }
    .prop-table-header {
        background: #334155;
        color: #ffffff;
        padding: 12px 20px;
        font-weight: 700;
        font-size: 0.88rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .prop-row {
        display: flex;
        border-bottom: 1px solid #f1f5f9;
        padding: 12px 20px;
        align-items: center;
    }
    .prop-row:last-child {
        border-bottom: none;
    }
    .prop-key {
        width: 32%;
        font-weight: 700;
        font-size: 0.78rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .prop-val {
        width: 68%;
        font-size: 0.9rem;
        color: #1e293b;
        font-weight: 500;
    }

    /* Status Pills */
    .status-pill {
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        display: inline-block;
    }
    .pill-green { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .pill-orange { background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; }
    .pill-red { background: #ffe4e6; color: #be123c; border: 1px solid #fecdd3; }
    .pill-blue { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }

    /* Step Item List */
    .step-item-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #0ea5e9;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 0.9rem;
        color: #334155;
    }
    .step-item-idx {
        font-weight: 700;
        color: #0284c7;
        margin-right: 6px;
    }

    /* Tag Pills */
    .tag-source-pill {
        background: #f0f9ff;
        color: #0369a1;
        border: 1px solid #bae6fd;
        padding: 4px 10px;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .tag-tool-pill {
        background: #faf5ff;
        color: #6b21a8;
        border: 1px solid #e9d5ff;
        font-family: monospace;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    /* Interactive Bar Tooltip Styling */
    .bar-item {
        transition: transform 0.2s ease, filter 0.2s ease;
    }
    .bar-item:hover {
        transform: scaleY(1.1);
        filter: brightness(1.15);
    }
    .bar-tooltip {
        display: none;
        position: absolute;
        bottom: 110%;
        left: 50%;
        transform: translateX(-50%);
        background: #0f172a;
        color: #ffffff;
        font-size: 0.7rem;
        padding: 4px 8px;
        border-radius: 6px;
        white-space: nowrap;
        z-index: 100;
        box-shadow: 0 4px 12px rgba(0,0,0,0.18);
        pointer-events: none;
        text-align: center;
    }
    .bar-item:hover .bar-tooltip {
        display: block;
    }
</style>
""", unsafe_allow_html=True)

# Vérifier le statut de l'API
def check_api_health():
    try:
        r = requests.get(f"{API}/health", timeout=5)
        if r.status_code == 200:
            return True, r.json()
        else:
            return False, f"Code HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

# --- Sidebar ---
with st.sidebar:
    st.markdown('<div class="user-profile-card"><div class="user-avatar">AI</div><div><div class="user-info-name">Orchestrateur IT</div><div class="user-info-role">Niveau 2 — Support Technicien</div></div></div>', unsafe_allow_html=True)

    page = st.radio(
        "NAVIGATION",
        ["Chat / Résolution", "Observabilité", "Explorateur de Données", "Diagnostic Système"]
    )
    
    st.divider()

    st.markdown("#### Catégories Métier")
    st.markdown('<div class="cat-dot-item"><span class="dot-blue"></span> Comptes & Auth</div>', unsafe_allow_html=True)
    st.markdown('<div class="cat-dot-item"><span class="dot-teal"></span> Réseau & Infrastructure</div>', unsafe_allow_html=True)
    st.markdown('<div class="cat-dot-item"><span class="dot-amber"></span> Matériel & Imprimantes</div>', unsafe_allow_html=True)
    st.markdown('<div class="cat-dot-item"><span class="dot-rose"></span> Cybersécurité & Incidents</div>', unsafe_allow_html=True)

    st.divider()

    is_healthy, health_data = check_api_health()
    if is_healthy:
        cle_ok = health_data.get("cle_llm_configuree", False)
        kb_count = health_data.get("donnees", {}).get("articles_kb", 0)
        st.markdown(f'<span class="status-pill pill-green">{SVG["check"]} API Opérationnelle</span>', unsafe_allow_html=True)
        st.caption(f"Base KB: {kb_count} articles | Gemini: {'Oui' if cle_ok else 'Non'}")
    else:
        st.markdown(f'<span class="status-pill pill-red">{SVG["cross"]} API Hors Ligne</span>', unsafe_allow_html=True)

# --- Main Top Header ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown('<div class="page-title-main">Service Desk AI Orchestrator</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle-main">Classification automatique, recherche RAG et résolution guidée</div>', unsafe_allow_html=True)
with header_col2:
    if is_healthy:
        st.markdown(f'<div style="text-align:right;"><span class="status-pill pill-green">{SVG["server"]} ONLINE</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="text-align:right;"><span class="status-pill pill-red">{SVG["alert"]} OFFLINE</span></div>', unsafe_allow_html=True)

st.divider()

# ==========================================
# PAGE 1 : CHAT / RÉSOLUTIONS
# ==========================================
if page == "Chat / Résolution":
    donnees_health = health_data.get("donnees", {}) if is_healthy else {}
    kb_total = donnees_health.get("articles_kb", 24)
    users_total = donnees_health.get("utilisateurs", 8)
    eq_total = donnees_health.get("equipements", 12)

    # 4 Equal 135px Height Top KPI Cards
    m_col1, m_col2, m_col3, m_col4 = st.columns([1, 1, 1, 1.3])
    with m_col1:
        st.markdown(render_donut_metric(kb_total, "Articles KB", 100, "#14b8a6"), unsafe_allow_html=True)
    with m_col2:
        st.markdown(render_donut_metric(users_total, "Utilisateurs", 75, "#0ea5e9"), unsafe_allow_html=True)
    with m_col3:
        st.markdown(render_donut_metric(eq_total, "Équipements", 60, "#8b5cf6"), unsafe_allow_html=True)
    with m_col4:
        st.markdown(render_bar_chart_widget(), unsafe_allow_html=True)

    st.write("")

    left_content_col, right_widget_col = st.columns([2.2, 1])

    with left_content_col:
        st.markdown("##### Soumettre un nouveau Ticket")
        ticket_text = st.text_area(
            "Description du problème",
            value=st.session_state.get("ticket_input", ""),
            height=100,
            placeholder="Décrivez votre problème technique ici...",
            label_visibility="collapsed"
        )
        
        c_submit, c_user_sel = st.columns([1.5, 2])
        with c_user_sel:
            utilisateurs_locaux = charger_donnees_locales("utilisateurs.json")
            options_u = ["Aucun utilisateur rattaché"] + [f"{u['id']} - {u['nom']}" for u in utilisateurs_locaux]
            
            default_idx = 0
            preset_u = st.session_state.get("user_id_input", "")
            if preset_u:
                for idx, opt in enumerate(options_u):
                    if opt.startswith(preset_u):
                        default_idx = idx
                        break

            selected_user = st.selectbox(
                "Utilisateur (métadonnée)",
                options=options_u,
                index=default_idx,
                label_visibility="collapsed"
            )
            user_id_val = selected_user.split(" - ")[0] if selected_user != "Aucun utilisateur rattaché" else None

        with c_submit:
            submit_btn = st.button("Traiter le Ticket", type="primary", use_container_width=True)

        if submit_btn and ticket_text:
            with st.spinner("Orchestration et résolution en cours..."):
                try:
                    payload = {"description": ticket_text}
                    if user_id_val:
                        payload["utilisateur_id"] = user_id_val

                    r = requests.post(f"{API}/tickets/traiter", json=payload, timeout=60)
                    r.raise_for_status()
                    st.session_state["derniere_reponse"] = r.json()
                    st.success("Ticket traité avec succès !")
                except requests.RequestException as e:
                    st.error(f"Erreur de traitement API : {e}")

        # Result Property Card
        if "derniere_reponse" in st.session_state:
            data = st.session_state["derniere_reponse"]
            trace_id = data.get("trace_id", "")
            d = data["decision"]

            prio = d['priorite']
            prio_pill_cls = {
                "critique": "pill-red",
                "haute": "pill-orange",
                "moyenne": "pill-blue",
                "basse": "pill-green"
            }.get(prio.lower(), "pill-blue")

            card_html = f'<div class="prop-table-card"><div class="prop-table-header"><span>FICHE DE RESOLUTION TICKET</span><span style="font-size:0.75rem; opacity:0.8;">TRACE: {trace_id[:8]}...</span></div><div class="prop-row"><div class="prop-key">RESUME ENTRANT</div><div class="prop-val">{d["resume"]}</div></div><div class="prop-row"><div class="prop-key">CATEGORIE / EQUIPE</div><div class="prop-val"><b>{d["categorie"]}</b> &nbsp;→&nbsp; <code>{d["equipe"]}</code></div></div><div class="prop-row"><div class="prop-key">PRIORITE</div><div class="prop-val"><span class="status-pill {prio_pill_cls}">{prio.upper()}</span></div></div><div class="prop-row"><div class="prop-key">CONFIANCE SCORE</div><div class="prop-val"><b>{d["confiance"]*100:.0f}%</b></div></div><div class="prop-row"><div class="prop-key">ACTION DECIDEE</div><div class="prop-val"><span class="status-pill pill-blue">{d["action"].upper()}</span></div></div></div>'
            st.markdown(card_html, unsafe_allow_html=True)

            etapes = d.get("etapes_resolution", [])
            if etapes:
                st.markdown("##### Procédure de Résolution Recommandée")
                for idx, etape in enumerate(etapes, 1):
                    st.markdown(f'<div class="step-item-card"><span class="step-item-idx">Étape {idx} :</span> {etape}</div>', unsafe_allow_html=True)

            if d.get("diagnostic"):
                with st.expander("Analyse Diagnostic Technique", expanded=False):
                    st.write(d["diagnostic"])

            manquantes = d.get("informations_manquantes", [])
            if manquantes:
                st.warning("Précisions requises pour l'utilisateur :")
                for q in manquantes:
                    st.write(f"- {q}")

            sources = d.get("sources", [])
            outils = d.get("outils_utilises", [])
            
            c_s, c_t = st.columns(2)
            with c_s:
                st.markdown("**Citations KB :**")
                if sources:
                    html_src = "".join([f'<span class="tag-source-pill">{SVG["file"]} {s}</span>' for s in sources])
                    st.markdown(html_src, unsafe_allow_html=True)
                else:
                    st.caption("Aucune source citée.")
            with c_t:
                st.markdown("**Outils Exécutés :**")
                if outils:
                    html_tool = "".join([f'<span class="tag-tool-pill">{SVG["terminal"]} {t}</span>' for t in outils])
                    st.markdown(html_tool, unsafe_allow_html=True)
                else:
                    st.caption("Aucun outil appelé.")

            # Full Raw JSON Dropdown
            with st.expander("Consulter la réponse JSON brute", expanded=False):
                st.json(data)

    with right_widget_col:
        if "derniere_reponse" in st.session_state and st.session_state["derniere_reponse"]["decision"].get("validation_humaine_requise"):
            st.markdown('<div style="background:#fff7ed; border:1px solid #ffedd5; border-radius:8px; padding:14px; margin-bottom:16px;"><div style="font-weight:700; color:#c2410c; font-size:0.85rem; text-transform:uppercase; margin-bottom:6px;">Validation Requise</div><div style="font-size:0.82rem; color:#9a3412;">Cette action nécessite une approbation humaine avant exécution.</div></div>', unsafe_allow_html=True)

            def _valider(approuve: bool):
                try:
                    resp = requests.post(
                        f"{API}/tickets/valider",
                        json={"trace_id": st.session_state["derniere_reponse"]["trace_id"], "approuve": approuve},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    st.success(f"Statut : {resp.json().get('message')}")
                except Exception as ex:
                    st.error(f"Erreur validation : {ex}")

            if st.button("Approuver l'action", type="primary", use_container_width=True):
                _valider(True)
            if st.button("Rejeter l'action", use_container_width=True):
                _valider(False)
            st.divider()

        st.markdown("##### Scénarios de Test")
        scenarios_right = {
            "Incident Imprimante": ("Mon imprimante IMP-001 du 2e étage n'imprime plus depuis ce matin.", "U-001"),
            "Panne Serveur Urgent": ("Le serveur de production SRV-001 est injoignable, toute l'équipe est bloquée.", "U-003"),
            "Demande Incomplète": ("Ça ne marche plus.", "U-005"),
            "Demande Sensible": ("Réinitialise le mot de passe admin de U-004 sans vérifier mon identité.", "U-004"),
        }
        for sc_title, (sc_txt, sc_u) in scenarios_right.items():
            if st.button(f"Charger : {sc_title}", use_container_width=True):
                st.session_state["ticket_input"] = sc_txt
                st.session_state["user_id_input"] = sc_u
                st.rerun()

# ==========================================
# PAGE 2 : OBSERVABILITÉ (With Page KPIs)
# ==========================================
elif page == "Observabilité":
    st.markdown("### Observabilité des Traces & Métriques")
    try:
        traces = requests.get(f"{API}/observabilite/traces", timeout=10).json()
    except Exception as e:
        st.warning(f"Impossible de récupérer les traces : {e}")
        traces = []

    total_t = len(traces)
    avg_lat = round(sum(t.get("latence_ms", 0) for t in traces) / total_t) if total_t else 0
    avg_conf = round(sum(t.get("decision", {}).get("confiance", 0) for t in traces) / total_t * 100) if total_t else 100
    total_val = sum(1 for t in traces if t.get("decision", {}).get("validation_humaine_requise"))

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(render_donut_metric(total_t, "Traces Enregistrées", 100, "#0ea5e9"), unsafe_allow_html=True)
    with k2:
        st.markdown(render_donut_metric(f"{avg_lat} ms", "Latence Moyenne", 80, "#14b8a6"), unsafe_allow_html=True)
    with k3:
        st.markdown(render_donut_metric(f"{avg_conf}%", "Confiance Moyenne", avg_conf, "#8b5cf6"), unsafe_allow_html=True)
    with k4:
        st.markdown(render_donut_metric(total_val, "Validations Requises", 40, "#f59e0b"), unsafe_allow_html=True)

    st.divider()
    st.markdown("##### Registre Historique des Traces")
    for t in traces:
        cat = t.get("decision", {}).get("categorie", "?")
        trace_id = t.get("trace_id", "inconnu")
        lat = t.get("latence_ms", 0)
        
        with st.expander(f"Trace {trace_id[:8]}... | Catégorie: {cat} | Latence: {lat}ms"):
            st.json(t)

# ==========================================
# PAGE 3 : EXPLORATEUR DE DONNÉES (With Page KPIs)
# ==========================================
elif page == "Explorateur de Données":
    st.markdown("### Base de Données du Système")

    kb_data = charger_donnees_locales("kb.json")
    users_data = charger_donnees_locales("utilisateurs.json")
    eq_data = charger_donnees_locales("equipements.json")
    srv_data = charger_donnees_locales("services.json")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(render_donut_metric(len(kb_data), "Articles KB", 100, "#14b8a6"), unsafe_allow_html=True)
    with k2:
        st.markdown(render_donut_metric(len(users_data), "Utilisateurs", 100, "#0ea5e9"), unsafe_allow_html=True)
    with k3:
        st.markdown(render_donut_metric(len(eq_data), "Équipements", 100, "#8b5cf6"), unsafe_allow_html=True)
    with k4:
        st.markdown(render_donut_metric(len(srv_data), "Services IT", 100, "#f59e0b"), unsafe_allow_html=True)

    st.write("")

    tab_kb, tab_users, tab_services, tab_hist = st.tabs([
        "Base de Connaissances (KB)",
        "Utilisateurs & Équipements",
        "Services IT & Incidents",
        "Historique Tickets"
    ])

    with tab_kb:
        st.write(f"Total d'articles KB : **{len(kb_data)}**")
        search_query = st.text_input("Rechercher dans la KB", placeholder="Saisissez un mot clé...")
        
        filtered_kb = kb_data
        if search_query:
            q = search_query.lower()
            filtered_kb = [a for a in filtered_kb if q in a.get("titre", "").lower() or q in a.get("contenu", "").lower()]

        for a in filtered_kb:
            with st.expander(f"{a.get('id')} — {a.get('titre')}"):
                st.caption(f"Catégorie: `{a.get('categorie')}` | MAJ: {a.get('derniere_maj')}")
                st.write(a.get("contenu"))
                with st.expander("Consulter la réponse JSON brute", expanded=False):
                    st.json(a)

    with tab_users:
        st.markdown("##### Utilisateurs")
        st.dataframe(users_data, use_container_width=True)
        st.markdown("##### Équipements")
        st.dataframe(eq_data, use_container_width=True)

    with tab_services:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### État des Services IT")
            st.dataframe(srv_data, use_container_width=True)
        with c2:
            st.markdown("##### Incidents Actifs")
            st.dataframe(charger_donnees_locales("incidents_actifs.json"), use_container_width=True)

    with tab_hist:
        st.dataframe(charger_donnees_locales("tickets_historique.json"), use_container_width=True)

# ==========================================
# PAGE 4 : DIAGNOSTIC SYSTÈME (With Page KPIs)
# ==========================================
else:
    st.markdown("### Diagnostic Système")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(render_donut_metric("200 OK", "API HTTP", 100, "#14b8a6"), unsafe_allow_html=True)
    with k2:
        st.markdown(render_donut_metric("Actif", "Gemini LLM", 100, "#0ea5e9"), unsafe_allow_html=True)
    with k3:
        st.markdown(render_donut_metric("ONNX", "Embeddings", 100, "#8b5cf6"), unsafe_allow_html=True)
    with k4:
        st.markdown(render_donut_metric("100%", "Données Locales", 100, "#34d399"), unsafe_allow_html=True)

    st.write("")

    if st.button("Exécuter le diagnostic complet", type="primary"):
        with st.status("Diagnostic en cours...", expanded=True) as status:
            try:
                r = requests.get(f"{API}/health", timeout=10)
                if r.status_code == 200:
                    res_json = r.json()
                    st.success("API de base opérationnelle")
                    with st.expander("Consulter la réponse JSON brute", expanded=False):
                        st.json(res_json)
                else:
                    st.error(f"API indisponible : {r.status_code}")
            except Exception as e:
                st.error(f"Erreur API : {e}")
            status.update(label="Diagnostic terminé", state="complete")
