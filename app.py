import streamlit as st
import datetime
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from streamlit_cookies_controller import CookieController

# 1. CONFIGURAZIONE PAGINA
st.set_page_config(
    page_title="Diario Allenamento", 
    page_icon="🏋️", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 2. INIZIALIZZA IL CONTROLLER DEI COOKIE
controller = CookieController()

# --- BANNER INSTALLAZIONE INTELLIGENTE ---
st.markdown("""
    <style>
        .pwa-banner {
            background: linear-gradient(135deg, #0ea5e9, #2563eb);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-size: 14px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
        }
        @media all and (display-mode: standalone) {
            .pwa-banner { display: none !important; }
        }
        @media all and (display-mode: fullscreen) {
            .pwa-banner { display: none !important; }
        }
    </style>
    <div class="pwa-banner">
        📲 <b>Salva l'app sul telefono!</b><br><br>
        Tocca l'icona di condivisione del browser ( 📤 ) e seleziona <b>"Aggiungi alla schermata Home"</b> per non perdere la tua scheda.
    </div>
""", unsafe_allow_html=True)

# --- 1. AUTENTICAZIONE GOOGLE ---
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(credentials)
except Exception as e:
    st.error("Errore di autenticazione con Google. Controlla le chiavi segrete.")
    st.stop()

# --- 2. RECUPERO ID FOGLIO (AUTOMATICO DA URL O MEMORIA) ---
id_foglio = st.query_params.get("id")

if id_foglio:
    controller.set("id_salvato", id_foglio, max_age=31536000)
else:
    id_foglio = controller.get("id_salvato")

if not id_foglio:
    st.info("🔄 Sincronizzazione scheda in corso...")
    st.markdown("<p style='text-align: center; color: gray; font-size: 12px;'>Se la schermata rimane bloccata, assicurati di aver aperto il link originale inviato dal coach almeno una volta.</p>", unsafe_allow_html=True)
    st.stop()

try:
    spreadsheet = client.open_by_key(id_foglio)
except Exception as e:
    st.error(f"Impossibile accedere al foglio. Dettagli: {e}")
    st.stop()

# --- 3. DEFINIZIONE DEI FOGLI ---
try:
    sheet_programma = spreadsheet.get_worksheet(0)
    sheet_storico = spreadsheet.worksheet("Diario Atleta") 
except Exception as e:
    st.error(f"Errore: Impossibile trovare 'Diario Atleta'. Controlla che le schede nel file Excel si chiamino correttamente. Errore: {e}")
    st.stop()


# --- 4. SISTEMA ANTI-BLOCCO (CACHE) ---
# QUESTA è la funzione mancante che evita a Google di bloccarti!
@st.cache_data(ttl=300)
def scarica_dati_fogli(_prog, _storico):
    return _prog.get_all_values(), _storico.get_all_values()

dati_programma, dati_storico = scarica_dati_fogli(sheet_programma, sheet_storico)


# --- 5. ESTRAZIONE DATI PROGRAMMA E STORICO ---
riga_header = -1
idx_es, idx_giorno = -1, -1
idx_serie_coach, idx_rip_coach, idx_carico_coach = -1, -1, -1

for i, riga in enumerate(dati_programma):
    if "Esercizio" in riga and "Giorno" in riga:
        riga_header = i
        idx_es = riga.index("Esercizio")
        idx_giorno = riga.index("Giorno")
        
        for j, col in enumerate(riga):
            col_str = str(col).lower().strip()
            if "serie" in col_str: idx_serie_coach = j
            elif "rip" in col_str: idx_rip_coach = j
            elif "kg" in col_str or "carico" in col_str or "peso" in col_str: idx_carico_coach = j
        break

if riga_header == -1:
    st.error("Errore: Impossibile trovare le colonne 'Esercizio' e 'Giorno' nel programma.")
    st.stop()

esercizi_dict = {}
giorni_disponibili = set()

for riga in dati_programma[riga_header+1:]:
    if len(riga) > max(idx_es, idx_giorno): 
        nome = riga[idx_es].strip()
        giorno = riga[idx_giorno].strip().upper()
        
        serie_coach = riga[idx_serie_coach].strip() if idx_serie_coach != -1 and len(riga) > idx_serie_coach else "?"
        rip_coach = riga[idx_rip_coach].strip() if idx_rip_coach != -1 and len(riga) > idx_rip_coach else "?"
        carico_coach = riga[idx_carico_coach].strip() if idx_carico_coach != -1 and len(riga) > idx_carico_coach else ""
        
        if nome != "":
            if giorno not in esercizi_dict:
                esercizi_dict[giorno] = []
            esercizi_dict[giorno].append({
                "nome": nome, 
                "serie_coach": serie_coach,
                "rip_coach": rip_coach,
                "carico_coach": carico_coach
            })
            if giorno != "":
                giorni_disponibili.add(giorno)

giorni_disponibili = sorted(list(giorni_disponibili))

riga_header_storico = -1
for i, riga in enumerate(dati_storico):
    if "Esercizio" in riga and "Kg Sollevati" in riga:
        riga_header_storico = i
        break

if riga_header_storico != -1 and len(dati_storico) > riga_header_storico + 1:
    df_storico = pd.DataFrame(dati_storico[riga_header_storico+1:], columns=dati_storico[riga_header_storico])
else:
    df_storico = pd.DataFrame()

def ottieni_testo_titolo(es_nome, serie_coach, rip_coach, carico_coach):
    s_val = str(serie_coach).strip() if str(serie_coach).strip() not in ["", "N/D", "nan", "?"] else "?"
    r_val = str(rip_coach).strip() if str(rip_coach).strip() not in ["", "N/D", "nan", "?"] else "?"
    base_str = f"{s_val} Serie x {r_val} rip"
    
    if not df_storico.empty and "Esercizio" in df_storico.columns:
        df_es = df_storico[df_storico["Esercizio"] == es_nome]
        if not df_es.empty and "Kg Sollevati" in df_es.columns:
            pesi_validi = df_es[~df_es["Kg Sollevati"].astype(str).str.strip().isin(["", "0", "0,0", "0.0", "nan"])]
            if not pesi_validi.empty:
                ultimi_kg = pesi_validi["Kg Sollevati"].iloc[-1]
                kg_str = str(ultimi_kg).strip().replace(",0", "").replace(".0", "")
                return f"{base_str}  |  {kg_str} kg"
                
    c_val = str(carico_coach).strip()
    if c_val not in ["", "N/D", "nan", "-1", "?"]:
        return f"{base_str}  |  {c_val} kg"
        
    return f"{base_str}  |  Kg liberi"


# --- 6. INTERFACCIA A SCHEDE (TABS) ---
tab_dash, tab_workout = st.tabs(["📊 Dashboard", "🏋️‍♂️ Scheda Allenamento"])

# ==========================================
# SEZIONE 1: DASHBOARD
# ==========================================
with tab_dash:
    st.header("I Tuoi Progressi 🚀")
    
    if df_storico.empty:
        st.info("Non ci sono ancora dati registrati. Inizia ad allenarti per sbloccare i grafici!")
    else:
        df_stat = df_storico.copy()
        
        if "Tonnellaggio" in df_stat.columns or "Tonnellaggi" in df_stat.columns:
            col_tonn = "Tonnellaggio" if "Tonnellaggio" in df_stat.columns else "Tonnellaggi"
            df_stat[col_tonn] = pd.to_numeric(df_stat[col_tonn].astype(str).replace(",", ".", regex=True), errors='coerce').fillna(0)
        else:
            df_stat["Tonnellaggi"] = 0
            col_tonn = "Tonnellaggi"

        tot_allenamenti = df_stat["Data"].nunique() if "Data" in df_stat.columns else 0
        tot_volume = df_stat[col_tonn].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Allenamenti Fatti", tot_allenamenti)
        c2.metric("Tonnellaggio Totale", f"{tot_volume:,.0f} kg")
        
        st.divider()
        st.subheader("Volume sollevato nel tempo 📈")
        if "Data" in df_stat.columns:
            vol_time = df_stat.groupby("Data")[col_tonn].sum().reset_index()
            vol_time = vol_time.set_index("Data")
            st.line_chart(vol_time)


# ==========================================
# SEZIONE 2: SCHEDA DI ALLENAMENTO
# ==========================================
with tab_workout:
    
    if st.session_state.get("dati_salvati", False):
        st.success("Dati della scheda inviati al coach! 🏋️‍♂️🔥 Puoi chiudere questa pagina.")
        if st.button("Inserisci un'altra scheda"):
            st.session_state.dati_salvati = False
            st.rerun()
    else:
        st.write("### Registra la sessione di oggi")
        data_sessione = st.date_input("Data della sessione", datetime.date.today())

        if not giorni_disponibili:
            st.warning("Non ci sono esercizi assegnati o manca la lettera del 'Giorno' nel programma.")
        else:
            giorno_scelto = st.selectbox("Quale scheda (Giorno) vuoi allenare oggi?", giorni_disponibili)
            esercizi_assegnati = esercizi_dict[giorno_scelto]
            
            # Memoria
            if "contatore_serie" not in st.session_state:
                st.session_state.contatore_serie = {}
            if "ultimo_giorno_scelto" not in st.session_state:
                st.session_state.ultimo_giorno_scelto = giorno_scelto
            if "es_aperto" not in st.session_state:
                st.session_state.es_aperto = None
                
            if st.session_state.ultimo_giorno_scelto != giorno_scelto:
                st.session_state.contatore_serie = {}
                st.session_state.ultimo_giorno_scelto = giorno_scelto
                st.session_state.es_aperto = None

            st.divider()
            
            with st.form("workout_form"):
                
                # --- FIX ERRORE INVIO DELLA TASTIERA ---
                # Questo bottone intercetta il tasto Invio del telefono impedendo che le tendine si sballino
                submit_nascosto = st.form_submit_button("🔄 Salva Dati (Premi Invio per confermare)", use_container_width=True)
                if submit_nascosto:
                    pass # Aggiorna la pagina innocuamente
                
                st.divider()
                
                for es_obj in esercizi_assegnati:
                    es = es_obj["nome"]
                    serie_coach = es_obj["serie_coach"]
                    rip_coach = es_obj["rip_coach"]
                    carico_coach = es_obj["carico_coach"]
                    
                    if es not in st.session_state.contatore_serie:
                        st.session_state.contatore_serie[es] = 1
                    
                    testo_titolo = ottieni_testo_titolo(es, serie_coach, rip_coach, carico_coach)
                    titolo_expander = f"🏋️‍♂️ {es}  |  {testo_titolo}"
                    
                    # Tiene aperta la tendina dell'ultimo esercizio su cui abbiamo premuto "+"
                    tieni_aperto = (st.session_state.es_aperto == es)
                    
                    with st.expander(titolo_expander, expanded=tieni_aperto):
                        
                        for i in range(st.session_state.contatore_serie[es]):
                            st.markdown(f"**Serie {i + 1}**")
                            c1, c2 = st.columns(2)
                            with c1:
                                st.number_input("Ripetizioni", min_value=0, step=1, key=f"rip_{es}_{i}")
                            with c2:
                                st.number_input("Kg", min_value=0.0, step=0.5, key=f"kg_{es}_{i}")
                        
                        # --- FIX NUOVE SERIE (COPIA DATI DALLA PRECEDENTE) ---
                        if st.form_submit_button(f"➕ Aggiungi Serie", key=f"btn_add_{es}"):
                            idx_nuovo = st.session_state.contatore_serie[es]
                            idx_vecchio = idx_nuovo - 1
                            
                            # Clona i Kg e le Ripetizioni della serie appena completata e li prepara per la nuova
                            st.session_state[f"rip_{es}_{idx_nuovo}"] = st.session_state.get(f"rip_{es}_{idx_vecchio}", 0)
                            st.session_state[f"kg_{es}_{idx_nuovo}"] = st.session_state.get(f"kg_{es}_{idx_vecchio}", 0.0)
                            
                            st.session_state.contatore_serie[es] += 1
                            st.session_state.es_aperto = es # Mantiene aperto l'esercizio!
                            st.rerun() 

                st.divider()
                st.write("### Fine Allenamento")
                rpe_globale = st.slider(
                    "Fatica percepita (10=fatica massima, 0=nessuna fatica)", 
                    min_value=0.0, max_value=10.0, value=7.0, step=0.5
                )
                feedback_globale = st.text_area(
                    "Feedback / Dolori (Opzionale)", 
                    placeholder="Scrivi qui se hai provato fastidi, come ti sei sentito, ecc..."
                )
                
                st.divider()
                
                # PULSANTE FINALE
                submit_finale = st.form_submit_button("💾 Consegna Intero Allenamento", type="primary", use_container_width=True)
                
                if submit_finale:
                    righe_da_inserire = []
                    
                    for es_obj in esercizi_assegnati:
                        es = es_obj["nome"]
                        
                        for i in range(st.session_state.contatore_serie[es]):
                            rip = st.session_state.get(f"rip_{es}_{i}", 0)
                            kg = st.session_state.get(f"kg_{es}_{i}", 0.0)
                            
                            if rip > 0:
                                numero_serie = i + 1
                                tonnellaggio = rip * kg
                                
                                nuova_riga = [
                                    str(data_sessione),             
                                    es,                             
                                    numero_serie,        
                                    rip,          
                                    str(kg).replace(".", ","),           
                                    str(tonnellaggio).replace(".", ","),
                                    str(rpe_globale).replace(".", ","),          
                                    feedback_globale          
                                ]
                                righe_da_inserire.append(nuova_riga)
                    
                    if len(righe_da_inserire) > 0:
                        try:
                            sheet_storico.append_rows(righe_da_inserire, value_input_option='USER_ENTERED')
                            
                            scarica_dati_fogli.clear() # Questo sblocca i grafici per mostrare subito le novità
                            
                            st.session_state.dati_salvati = True
                            st.session_state.contatore_serie = {} 
                            st.session_state.es_aperto = None 
                            st.rerun() 
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio: {e}")
                    else:
                        st.warning("⚠️ Non hai compilato nessuna serie valida (Ripetizioni > 0). Nessun dato salvato.")
