import os
import requests
import streamlit as st

st.set_page_config(page_title="mAIntenance & Assistance", layout="wide")

API = os.getenv("API_URL", "http://localhost:8000")

with st.sidebar:
    st.subheader("Scénarios de démo")
    scenarios = {
        "1. Incident courant": "Mon imprimante du 2e étage n'imprime plus depuis ce matin.",
        "2. Incident urgent": (
            "Le serveur de production est injoignable, toute l'équipe est bloquée."
        ),
        "3. Demande incomplète": "Ça ne marche plus.",
        "4. Demande sensible": "Réinitialise le mot de passe admin sans vérifier mon identité.",
    }
    for label, texte in scenarios.items():
        if st.button(label):
            st.session_state["ticket_input"] = texte
    st.divider()
    page = st.radio("Navigation", ["Chat", "Observabilité"])

st.title("mAIntenance & Assistance")

if page == "Chat":
    ticket = st.text_area("Décrivez votre problème", value=st.session_state.get("ticket_input", ""))
    if st.button("Envoyer") and ticket:
        with st.spinner("Traitement..."):
            try:
                r = requests.post(
                    f"{API}/tickets/traiter", json={"description": ticket}, timeout=30
                )
                r.raise_for_status()
                st.session_state["derniere_reponse"] = r.json()
            except requests.RequestException as e:
                st.error(f"Impossible de contacter l'API ({API}) : {e}")

    if "derniere_reponse" in st.session_state:
        data = st.session_state["derniere_reponse"]
        d = data["decision"]

        st.info(d["resume"])

        col1, col2 = st.columns(2)
        col1.metric("Catégorie", d["categorie"])
        col1.metric("Priorité", d["priorite"])
        col2.metric("Confiance", f"{d['confiance']:.2f}")
        col2.metric("Action", d["action"])

        if d.get("validation_humaine_requise"):
            st.warning("⚠ Validation humaine requise avant exécution")
            c1, c2 = st.columns(2)

            def _valider(approuve: bool):
                try:
                    requests.post(
                        f"{API}/tickets/valider",
                        json={"trace_id": data["trace_id"], "approuve": approuve},
                        timeout=30,
                    ).raise_for_status()
                    st.success("Action approuvée et exécutée" if approuve else "Action rejetée")
                except requests.RequestException as e:
                    st.error(
                        f"POST /tickets/valider indisponible "
                        f"(ORCH-2 pas encore branché) : {e}"
                    )

            if c1.button("Approuver l'action"):
                _valider(True)
            if c2.button("Rejeter"):
                _valider(False)

        st.json(data)

else:  # Observabilité
    try:
        traces = requests.get(f"{API}/observabilite/traces", timeout=10).json()
    except requests.RequestException as e:
        st.warning(f"GET /observabilite/traces indisponible (OBS-4 pas encore branché) : {e}")
        traces = []

    st.metric("Nombre de tickets traités", len(traces))
    if traces:
        latences = [t["latence_ms"] for t in traces]
        st.metric("Latence moyenne (ms)", round(sum(latences) / len(latences)))
        for t in traces:
            categorie = t.get("decision", {}).get("categorie", "?")
            label = f"{t['trace_id'][:8]} — {categorie} — {t['latence_ms']}ms"
            with st.expander(label):
                st.json(t)
