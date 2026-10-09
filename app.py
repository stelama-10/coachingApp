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

# A) Leggiamo il programma del Coach
dati_programma = sheet_programma.get_all_values()
riga_header = -1
idx_es, idx_giorno, idx_carico = -1, -1, -1

for i, riga in enumerate(dati_programma):
    if "Esercizio" in riga and "Giorno" in riga:
        riga_header = i
        idx_es = riga.index("Esercizio")
        idx_giorno = riga.index("Giorno")
        # Cerca la colonna del peso consigliato se esiste
        if "Kg" in riga: idx_carico = riga.index("Kg")
        elif "Carico" in riga: idx_carico = riga.index("Carico")
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
        carico_coach = riga[idx_carico].strip() if idx_carico != -1 and len(riga) > idx_carico else "N/D"
        
        if nome != "":
            if giorno not in esercizi_dict:
                esercizi_dict[giorno] = []
            esercizi_dict[giorno].append({"nome": nome, "carico_coach": carico_coach})
            if giorno != "":
                giorni_disponibili.add(giorno)

giorni_disponibili = sorted(list(giorni_disponibili))

# B) Leggiamo lo storico dell'Atleta (Diario) per grafici e carichi precedenti
dati_storico = sheet_storico.get_all_values()
if len(dati_storico) > 1:
    df_storico = pd.DataFrame(dati_storico[1:], columns=dati_storico[0])
else:
    df_storico = pd.DataFrame()

# Funzione per trovare l'ultimo peso usato o quello indicato dal coach
def ottieni_ultimo_peso(es_nome, carico_coach):
    if not df_storico.empty and "Esercizio" in df_storico.columns and "Kg" in df_storico.columns:
        df_es = df_storico[df_storico["Esercizio"] == es_nome]
        if not df_es.empty:
            ultimi_kg = df_es["Kg"].iloc[-1]
            if str(ultimi_kg).strip() != "":
                return f"{ultimi_kg} kg (Ultimo allenamento)"
    
    if carico_coach != "N/D" and carico_coach != "":
        return f"{carico_coach} (Indicato dal Coach)"
        
    return "Nessun dato precedente"


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
        
        # Pulizia dati per i calcoli
        if "Tonnellaggio" in df_stat.columns:
            df_stat["Tonnellaggio"] = pd.to_numeric(df_stat["Tonnellaggio"].astype(str).str.replace(",", "."), errors='coerce').fillna(0)
        else:
            df_stat["Tonnellaggio"] = 0

        tot_allenamenti = df_stat["Data"].nunique() if "Data" in df_stat.columns else 0
        tot_volume = df_stat["Tonnellaggio"].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Allenamenti Fatti", tot_allenamenti)
        c2.metric("Tonnellaggio Totale", f"{tot_volume:,.0f} kg")
        
        st.divider()
        st.subheader("Volume sollevato nel tempo 📈")
        if "Data" in df_stat.columns:
            vol_time = df_stat.groupby("Data")["Tonnellaggio"].sum().reset_index()
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
            
            # 4. Form Unico per il salvataggio
            with st.form("form_allenamento_completo"):
                
                # --- RPE GLOBALE PER L'INTERA SESSIONE ---
                rpe_globale = st.slider(
                    "Fatica percepita (10=fatica massima 0=nessuna fatica)", 
                    min_value=0.0, 
                    max_value=10.0, 
                    value=7.0, 
                    step=0.5
                )
                st.divider()
                
                st.info("💡 **Istruzioni:** Compila le ripetizioni e i Kg per la prima serie. Usa il tasto **'+'** sotto ogni tabella per aggiungere tutte le serie che hai fatto!")

                tabelle_compilate = {}
                feedbacks = {}
                
                for es_obj in esercizi_assegnati:
                    es = es_obj["nome"]
                    carico_consigliato = es_obj["carico_coach"]
                    
                    st.markdown(f"#### {es}")
                    
                    # Mostra l'ultimo peso o quello del coach
                    info_peso = ottieni_ultimo_peso(es, carico_consigliato)
                    st.caption(f"🎯 **Obiettivo/Storico:** {info_peso}")
                    
                    # Tabella dinamica per aggiungere infinite serie
                    df_init = pd.DataFrame([{"Ripetizioni": 0, "Kg": 0.0}])
                    tabelle_compilate[es] = st.data_editor(
                        df_init, 
                        num_rows="dynamic", # Questo abilita il tasto "+"
                        hide_index=True, 
                        key=f"editor_{es}",
                        use_container_width=True
                    )
                    
                    feedbacks[es] = st.text_input("Feedback / Dolori (Opzionale)", key=f"feed_{es}")
                    st.divider()
                    
                submit_btn = st.form_submit_button("💾 Salva Intero Allenamento")
                
                # 5. Invio massivo a Google Fogli
                if submit_btn:
                    righe_da_inserire = []
                    
                    for es_obj in esercizi_assegnati:
                        es = es_obj["nome"]
                        df_edit = tabelle_compilate[es]
                        
                        for index, row in df_edit.iterrows():
                            rip = int(row.get("Ripetizioni", 0))
                            kg = float(row.get("Kg", 0.0))
                            
                            # Salva solo le serie dove l'atleta ha inserito almeno 1 ripetizione
                            if rip > 0:
                                numero_serie = index + 1
                                tonnellaggio = rip * kg
                                
                                nuova_riga = [
                                    str(data_sessione),             
                                    es,                             
                                    numero_serie,        
                                    rip,          
                                    str(kg).replace(".", ","),           
                                    str(tonnellaggio).replace(".", ","),
                                    str(rpe_globale).replace(".", ","),          
                                    feedbacks[es]          
                                ]
                                righe_da_inserire.append(nuova_riga)
                    
                    if len(righe_da_inserire) > 0:
                        try:
                            sheet_storico.append_rows(righe_da_inserire, value_input_option='USER_ENTERED')
                            st.session_state.dati_salvati = True
                            st.rerun() 
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio: {e}")
                    else:
                        st.warning("⚠️ Non hai compilato nessuna serie valida (Ripetizioni > 0). Nessun dato salvato.")
