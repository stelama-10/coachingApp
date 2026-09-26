import streamlit as st
import datetime

# --- AUTENTICAZIONE GIA' EFFETTUATA IN ALTO ---
# spreadsheet = client.open_by_key(ID_FOGLIO)

# 1. Definisci i fogli
sheet_programma = spreadsheet.get_worksheet(0) # Programma Coach
# In base al tuo file di esempio, le risposte andranno nel Diario
sheet_storico = spreadsheet.worksheet("Diario Atleta") 

# 2. Estrazione dati dal Foglio Google
# Estraiamo tutta la griglia per evitare problemi con le righe vuote iniziali
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
