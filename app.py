import streamlit as st
import datetime
import gspread
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

# 3. STILI DISPOSITIVI MOBILI
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black">
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
    # Salviamo l'ID in automatico e silenziosamente nel telefono per 1 anno.
    controller.set("id_salvato", id_foglio, max_age=31536000)
else:
    # CASO B: L'app è stata aperta dalla schermata Home dell'iPhone (URL troncato).
    # Peschiamo l'ID direttamente dalla memoria in background.
    id_foglio = controller.get("id_salvato")

# Poiché leggere la memoria richiede qualche decimo di secondo, gestiamo l'attesa
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
# (Da qui in poi lascia il tuo codice ESATTAMENTE com'è)
try:
    sheet_programma = spreadsheet.get_worksheet(0)
    sheet_storico = spreadsheet.worksheet("Diario Atleta") # La scheda dove verranno scritte le risposte
except Exception as e:
    st.error(f"Errore: Impossibile trovare 'Diario Atleta'. Controlla che le schede nel file Excel si chiamino correttamente. Errore: {e}")
    st.stop()

# --- 4. ESTRAZIONE DATI DAL FOGLIO PROGRAMMA ---
# Scarica tutta la griglia per cercare le colonne "Esercizio" e "Giorno"
dati_programma = sheet_programma.get_all_values()

# Trova dinamicamente la riga di intestazione e gli indici delle colonne
riga_header = -1
idx_es = -1
idx_giorno = -1

for i, riga in enumerate(dati_programma):
    if "Esercizio" in riga and "Giorno" in riga:
        riga_header = i
        idx_es = riga.index("Esercizio")
        idx_giorno = riga.index("Giorno")
        break

# Arresta l'app se le colonne non vengono trovate
if riga_header == -1:
    st.error("Errore: Impossibile trovare le colonne 'Esercizio' e 'Giorno' nel file.")
    st.stop()

# Raccoglie tutti gli esercizi e mappa i "giorni" disponibili (A, B, C...)
esercizi_totali = []
giorni_disponibili = set()

for riga in dati_programma[riga_header+1:]:
    # Evita gli errori sulle righe vuote o tagliate
    if len(riga) > max(idx_es, idx_giorno): 
        nome = riga[idx_es].strip()
        giorno = riga[idx_giorno].strip().upper()
        
        if nome != "":
            esercizi_totali.append({"nome": nome, "giorno": giorno})
            if giorno != "":
                giorni_disponibili.add(giorno)

giorni_disponibili = sorted(list(giorni_disponibili))

# 3. Interfaccia utente - SELEZIONE SCHEDA
st.write("### Registra la sessione di oggi")
data_sessione = st.date_input("Data della sessione", datetime.date.today())

if not giorni_disponibili:
    st.warning("Non ci sono esercizi assegnati o manca la lettera del 'Giorno' nel programma.")
else:
    # L'utente sceglie la scheda prima di aprire il form
    giorno_scelto = st.selectbox("Quale scheda (Giorno) vuoi allenare oggi?", giorni_disponibili)
    
    # Estraiamo solo gli esercizi corrispondenti al giorno selezionato
    esercizi_assegnati = [es["nome"] for es in esercizi_totali if es["giorno"] == giorno_scelto]
    
    st.info(f"Mostrando gli esercizi per la Scheda: **{giorno_scelto}**")

    # 4. Form Unico per il salvataggio
    with st.form("form_allenamento_completo"):
        dati_input = {}
        
        for es in esercizi_assegnati:
            st.markdown(f"**{es}**")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                serie = st.number_input("Serie fatte", min_value=0, step=1, key=f"serie_{es}")
            with col2:
                rip = st.number_input("Ripetizioni", min_value=0, step=1, key=f"rip_{es}")
            with col3:
                kg = st.number_input("Kg Sollevati", min_value=0.0, step=0.5, key=f"kg_{es}")
                
            rpe = st.slider("RPE Percepito", 1, 10, 8, key=f"rpe_{es}")
            feedback = st.text_input("Feedback / Dolori (Opzionale)", key=f"feed_{es}")
            st.divider()
            
            # Salvataggio temporaneo nel dizionario
            dati_input[es] = {
                "serie": serie, "rip": rip, "kg": kg, "rpe": rpe, "feed": feedback
            }
            
        submit_btn = st.form_submit_button("💾 Salva Intero Allenamento")
        
        # 5. Invio massivo a Google Fogli
        if submit_btn:
            righe_da_inserire = []
            
            for es in esercizi_assegnati:
                # Salva l'esercizio solo se è stata registrata almeno una serie
                if dati_input[es]["serie"] > 0:
                    nuova_riga = [
                        str(data_sessione),             
                        es,                             
                        dati_input[es]["serie"],        
                        dati_input[es]["rip"],          
                        dati_input[es]["kg"],           
                        "", # Tonnellaggi - lasciato vuoto se calcolato da Fogli  
                        dati_input[es]["rpe"],          
                        dati_input[es]["feed"]          
                    ]
                    righe_da_inserire.append(nuova_riga)
            
            if len(righe_da_inserire) > 0:
                sheet_storico.append_rows(righe_da_inserire, value_input_option='USER_ENTERED')
                st.success(f"✅ Scheda {giorno_scelto} salvata! Registrati {len(righe_da_inserire)} esercizi.")
            else:
                st.warning("⚠️ Non hai compilato nessuna serie. Nessun dato è stato salvato.")
