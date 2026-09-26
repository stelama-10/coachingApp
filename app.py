import streamlit as st
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. AUTENTICAZIONE GOOGLE ---
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(credentials)
except Exception as e:
    st.error("Errore di autenticazione con Google. Controlla le chiavi segrete.")
    st.stop()

# --- 2. RECUPERO ID FOGLIO DALL'URL ---
# Legge il parametro ?id=... dal link
if "id" not in st.query_params:
    st.error("Nessun ID foglio trovato nell'URL. Assicurati di aprire il link dalla tua App Flet (CRM).")
    st.stop()
    
id_foglio = st.query_params["id"]

try:
    spreadsheet = client.open_by_key(id_foglio)
except Exception as e:
    st.error(f"Impossibile accedere al foglio. Assicurati che l'email del bot sia impostata come Editor. Dettagli: {e}")
    st.stop()

# --- 3. DEFINIZIONE DEI FOGLI ---
try:
    sheet_programma = spreadsheet.get_worksheet(0) # Programma Coach (la primissima scheda in basso a sinistra)
    sheet_storico = spreadsheet.worksheet("Diario Atleta") # La scheda dove verranno scritte le risposte
except Exception as e:
    st.error(f"Errore: Impossibile trovare 'Diario Atleta'. Controlla che le schede nel file Excel si chiamino correttamente. Errore: {e}")
    st.stop()

# --- 4. ESTRAZIONE DATI DAL FOGLIO PROGRAMMA ---
# Scarica tutta la griglia per cercare le colonne "Esercizio" e "Giorno"
dati_programma = sheet_programma.get_all_values()

riga_header = -1
idx_es = -1
idx_giorno = -1

for i, riga in enumerate(dati_programma):
    if "Esercizio" in riga and "Giorno" in riga:
        riga_header = i
        idx_es = riga.index("Esercizio")
        idx_giorno = riga.index("Giorno")
        break

if riga_header == -1:
    st.error("Errore: Impossibile trovare le colonne 'Esercizio' e 'Giorno' nel file. Controlla le intestazioni.")
    st.stop()

esercizi_totali = []
giorni_disponibili = set()

# Estrae solo gli esercizi validi
for riga in dati_programma[riga_header+1:]:
    if len(riga) > max(idx_es, idx_giorno): 
        nome = riga[idx_es].strip()
        giorno = riga[idx_giorno].strip().upper()
        
        if nome != "":
            esercizi_totali.append({"nome": nome, "giorno": giorno})
            if giorno != "":
                giorni_disponibili.add(giorno)

giorni_disponibili = sorted(list(giorni_disponibili))

# --- 5. INTERFACCIA UTENTE E FORM STREAMLIT ---
st.write("### Registra la sessione di oggi")
data_sessione = st.date_input("Data della sessione", datetime.date.today())

if not giorni_disponibili:
    st.warning("Non ci sono esercizi assegnati o manca la lettera del 'Giorno' nel programma.")
else:
    # L'utente seleziona la scheda (A, B, C...)
    giorno_scelto = st.selectbox("Quale scheda (Giorno) vuoi allenare oggi?", giorni_disponibili)
    esercizi_assegnati = [es["nome"] for es in esercizi_totali if es["giorno"] == giorno_scelto]
    
    st.info(f"Mostrando gli esercizi per la Scheda: **{giorno_scelto}**")

    # Form Unico per il salvataggio
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
            
            dati_input[es] = {
                "serie": serie, "rip": rip, "kg": kg, "rpe": rpe, "feed": feedback
            }
            
        submit_btn = st.form_submit_button("💾 Salva Intero Allenamento")
        
        # Invio massivo a Google Fogli
        if submit_btn:
            righe_da_inserire = []
            
            for es in esercizi_assegnati:
                if dati_input[es]["serie"] > 0:
                    
                    # Calcolo del tonnellaggio in Python
                    tonnellaggio = dati_input[es]["serie"] * dati_input[es]["rip"] * dati_input[es]["kg"]
                    
                    nuova_riga = [
                        str(data_sessione),             
                        es,                             
                        dati_input[es]["serie"],        
                        dati_input[es]["rip"],          
                        dati_input[es]["kg"],           
                        tonnellaggio,
                        dati_input[es]["rpe"],          
                        dati_input[es]["feed"]          
                    ]
                    righe_da_inserire.append(nuova_riga)
            
            if len(righe_da_inserire) > 0:
                try:
                    sheet_storico.append_rows(righe_da_inserire, value_input_option='USER_ENTERED')
                    st.success(f"✅ Ottimo lavoro! Scheda {giorno_scelto} salvata con {len(righe_da_inserire)} esercizi completati.")
                    st.balloons() # <-- Animazione di successo
                except Exception as e:
                    st.error(f"Errore durante il salvataggio dei dati sul foglio: {e}")
            else:
                st.warning("⚠️ Non hai compilato nessuna serie. Nessun dato è stato salvato.")
