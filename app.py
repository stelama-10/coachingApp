import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Diario Allenamento", page_icon="🏋️", layout="centered")

@st.cache_resource
def ottieni_client_google():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # In cloud le credenziali vengono lette dai "Secrets" di Streamlit
    credenziali = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(credenziali)

st.title("🏋️ Il tuo Diario di Allenamento")

id_foglio = st.query_params.get("id")

if not id_foglio:
    st.warning("⚠️ Nessun ID rilevato. Accedi tramite il link personalizzato fornito dal tuo coach.")
    st.stop()

st.write("Compila i campi a fine serie per registrare i tuoi progressi.")

with st.form("form_allenamento", clear_on_submit=True):
    data_oggi = st.date_input("Data della sessione", datetime.today())
    
    esercizio = st.selectbox("Esercizio", [
        "Squat Bilanciere", "Panca Piana Bilanciere", "Stacco da Terra", 
        "Lat Machine Avanti", "Rematore Bilanciere", "Spinte Manubri Inclinata", "Leg Press 45°"
    ])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        serie = st.number_input("Serie Fatte", min_value=1, step=1)
    with col2:
        reps = st.number_input("Ripetizioni Fatte", min_value=1, step=1)
    with col3:
        kg = st.number_input("Kg Sollevati", min_value=0.0, step=0.5)
        
    rpe = st.slider("RPE Percepito (Fatica da 1 a 10)", min_value=1.0, max_value=10.0, value=8.0, step=0.5)
    
    feedback = st.text_area("Feedback / Dolori (Opzionale)", placeholder="Es. Ottima spinta, leggero fastidio al polso.")
    
    submitted = st.form_submit_button("Salva Allenamento 💾", use_container_width=True)
    
    if submitted:
        try:
            client = ottieni_client_google()
            foglio = client.open_by_key(id_foglio)
            scheda_diario = foglio.worksheet("Diario Atleta") 
            
            data_str = data_oggi.strftime("%d/%m/%Y")
            
            # --- CALCOLO TONNELLAGGIO IN PYTHON ---
            # Calcoliamo il volume totale prima di inviare i dati
            tonnellaggio = serie * reps * kg
            
            nuova_riga = [
                data_str, 
                esercizio, 
                serie,                        
                reps,                         
                str(kg).replace(".", ","),    
                str(tonnellaggio).replace(".", ","),  # Sostituisce la formula con il valore reale
                str(rpe).replace(".", ","),   
                feedback                      
            ]
            
            scheda_diario.append_row(nuova_riga, value_input_option='USER_ENTERED')
            
            st.success(f"Dati salvati con successo per {esercizio}!")
            st.balloons()
            
        except gspread.exceptions.APIError as e:
            st.error(f"Errore di comunicazione con Google: {e}")
        except gspread.exceptions.WorksheetNotFound:
            st.error("La scheda 'Diario Atleta' non è stata trovata in questo foglio.")
        except Exception as e:
            st.error(f"Si è verificato un errore: {e}")