import streamlit as st
import datetime
import gspread
import pandas as pd  # <-- NUOVA LIBRERIA AGGIUNTA
from google.oauth2.service_account import Credentials
from streamlit_cookies_controller import CookieController # Libreria per la memoria invisibile

# 1. CONFIGURAZIONE PAGINA
st.set_page_config(
    page_title="Diario Allenamento", 
    page_icon="🏋️", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 2. INIZIALIZZA IL CONTROLLER DEI COOKIE (Subito dopo la configurazione)
controller = CookieController()

# --- BANNER INSTALLAZIONE INTELLIGENTE ---
st.markdown("""
    <style>
        /* Disegna il banner visibile nel browser */
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
        
        /* IL TRUCCO: Se l'app viene eseguita dalla Home (standalone), nascondi tutto */
        @media all and (display-mode: standalone) {
            .pwa-banner {
                display: none !important;
            }
        }
        
        /* Copertura extra per vecchie versioni di iOS */
        @media all and (display-mode: fullscreen) {
            .pwa-banner {
                display: none !important;
            }
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
    # CASO A: Primo avvio da WhatsApp (l'URL è completo).
    controller.set("id_salvato", id_foglio, max_age=31536000)
else:
    # CASO B: L'app è stata aperta dalla schermata Home dell'iPhone (URL troncato).
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


# --- 4. ESTRAZIONE DATI PROGRAMMA E STORICO ---

# A) Leggiamo il programma del Coach in modo dinamico
dati_programma = sheet_programma.get_all_values()
riga_header = -1
idx_es, idx_giorno = -1, -1
idx_serie_coach, idx_rip_coach = -1, -1

for i, riga in enumerate(dati_programma):
    if "Esercizio" in riga and "Giorno" in riga:
        riga_header = i
        idx_es = riga.index("Esercizio")
        idx_giorno = riga.index("Giorno")
        
        # Cerca dinamicamente le colonne delle serie e ripetizioni (anche se chiamate diversamente)
        for j, col in enumerate(riga):
            col_str = str(col).lower()
            if "serie target" in col_str: idx_serie_coach = j
            elif "serie" in col_str and idx_serie_coach == -1: idx_serie_coach = j
            
            if "ripetizioni target" in col_str: idx_rip_coach = j
            elif "rip" in col_str and idx_rip_coach == -1: idx_rip_coach = j
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
        
        # Salviamo i target scritti dal coach
        serie_coach = riga[idx_serie_coach].strip() if idx_serie_coach != -1 and len(riga) > idx_serie_coach else "N/D"
        rip_coach = riga[idx_rip_coach].strip() if idx_rip_coach != -1 and len(riga) > idx_rip_coach else "N/D"
        
        if nome != "":
            if giorno not in esercizi_dict:
                esercizi_dict[giorno] = []
            esercizi_dict[giorno].append({
                "nome": nome, 
                "serie_coach": serie_coach,
                "rip_coach": rip_coach
            })
            if giorno != "":
                giorni_disponibili.add(giorno)

giorni_disponibili = sorted(list(giorni_disponibili))


# B) Leggiamo lo storico dell'Atleta (Diario)
dati_storico = sheet_storico.get_all_values()
riga_header_storico = -1

# Troviamo la riga delle intestazioni per evitare errori con righe vuote iniziali
for i, riga in enumerate(dati_storico):
    if "Esercizio" in riga and "Kg Sollevati" in riga:
        riga_header_storico = i
        break

if riga_header_storico != -1 and len(dati_storico) > riga_header_storico + 1:
    df_storico = pd.DataFrame(dati_storico[riga_header_storico+1:], columns=dati_storico[riga_header_storico])
else:
    df_storico = pd.DataFrame()

# Funzione per comporre la scritta sul titolo della tendina
def ottieni_testo_titolo(es_nome, serie_coach, rip_coach):
    if not df_storico.empty and "Esercizio" in df_storico.columns:
        df_es = df_storico[df_storico["Esercizio"] == es_nome]
        if not df_es.empty:
            # L'utente l'ha già fatto, peschiamo l'ultima riga!
            if "Kg Sollevati" in df_es.columns and "Ripetizioni Fatte" in df_es.columns:
                ultimi_kg = df_es["Kg Sollevati"].iloc[-1]
                ultime_rip = df_es["Ripetizioni Fatte"].iloc[-1]
                
                # Pulizia visiva dei Kg (es. 60.0 diventa 60)
                kg_str = str(ultimi_kg).strip().replace(",0", "").replace(".0", "")
                
                if kg_str != "" and kg_str != "nan":
                    return f"Ultimo: {ultime_rip} rip @ {kg_str} kg"
                elif str(ultime_rip).strip() != "" and str(ultime_rip).strip() != "nan":
                    return f"Ultimo: {ultime_rip} rip"
                    
    # Se non l'ha mai fatto, usiamo i target del coach
    s_val = str(serie_coach).strip()
    r_val = str(rip_coach).strip()
    
    if s_val not in ["", "N/D", "nan"] and r_val not in ["", "N/D", "nan"]:
        return f"Obiettivo: {s_val} x {r_val}"
    elif r_val not in ["", "N/D", "nan"]:
        return f"Obiettivo: {r_val} rip"
    
    return "Nuovo Esercizio"


# --- 5. INTERFACCIA A SCHEDE (TABS) ---
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
            df_stat[col_tonn] = pd.to_numeric(df_stat[col_tonn].astype(str).str.replace(",", "."), errors='coerce').fillna(0)
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
            
            # --- INIZIALIZZAZIONE MEMORIA SERIE ---
            if "contatore_serie" not in st.session_state:
                st.session_state.contatore_serie = {}
            if "ultimo_giorno_scelto" not in st.session_state:
                st.session_state.ultimo_giorno_scelto = giorno_scelto
                
            if st.session_state.ultimo_giorno_scelto != giorno_scelto:
                st.session_state.contatore_serie = {}
                st.session_state.ultimo_giorno_scelto = giorno_scelto

            st.divider()
            
            # --- CREAZIONE DELLA SCHEDA A MENU A TENDINA ---
            for es_obj in esercizi_assegnati:
                es = es_obj["nome"]
                serie_coach = es_obj["serie_coach"]
                rip_coach = es_obj["rip_coach"]
                
                # Di default prepariamo 1 serie iniziale per ogni esercizio
                if es not in st.session_state.contatore_serie:
                    st.session_state.contatore_serie[es] = 1
                
                # Costruisce il titolo visibile a tendina chiusa
                testo_titolo = ottieni_testo_titolo(es, serie_coach, rip_coach)
                titolo_expander = f"🏋️‍♂️ {es}  |  {testo_titolo}"
                
                with st.expander(titolo_expander, expanded=False):
                    
                    for i in range(st.session_state.contatore_serie[es]):
                        st.markdown(f"**Serie {i + 1}**")
                        c1, c2 = st.columns(2)
                        with c1:
                            # Tasti +/- nativi per le ripetizioni
                            st.number_input("Ripetizioni", min_value=0, step=1, key=f"rip_{es}_{i}")
                        with c2:
                            # Tasti +/- nativi per i Kg
                            st.number_input("Kg", min_value=0.0, step=0.5, key=f"kg_{es}_{i}")
                    
                    # Tasto per aggiungere dinamicamente una riga in più a quell'esercizio
                    if st.button("➕ Aggiungi Serie", key=f"btn_add_{es}"):
                        st.session_state.contatore_serie[es] += 1
                        st.rerun() 

            st.divider()
            
            # --- FEEDBACK E RPE GLOBALI ALLA FINE DELLA SCHEDA ---
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
            
            # Pulsante di salvataggio
            if st.button("💾 Consegna Intero Allenamento", type="primary", use_container_width=True):
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
                        st.session_state.dati_salvati = True
                        st.session_state.contatore_serie = {} 
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")
                else:
                    st.warning("⚠️ Non hai compilato nessuna serie valida (Ripetizioni > 0). Nessun dato salvato.")
