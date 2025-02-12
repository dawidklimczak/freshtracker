import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import io
import base64
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Konfiguracja strony
st.set_page_config(page_title="Skaner Produktów", layout="wide")
st.title("Skaner Produktów i Dat Ważności")

# Inicjalizacja stanu sesji
if 'captured_images' not in st.session_state:
    st.session_state.captured_images = []
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = []

# Konfiguracja OpenAI i Google Sheets
openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def setup_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["google_credentials"], scope)
    client = gspread.authorize(creds)
    sheet = client.open(st.secrets["spreadsheet_name"]).sheet1
    return sheet

def analyze_image(image_file):
    import json
    import re
    image_data = image_file.getvalue()
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Przeanalizuj to zdjęcie produktu i znajdź następujące informacje:
1. Nazwa produktu
2. Data ważności (w formacie YYYY-MM-DD)

Odpowiedz dokładnie w tym formacie, bez dodatkowych znaczników czy komentarzy:
{"product_name": "pełna nazwa produktu", "expiry_date": "YYYY-MM-DD"}

Jeśli nie możesz znaleźć którejś informacji, użyj null."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        
        # Pobierz odpowiedź i wyczyść ją ze znaczników markdown
        response_content = response.choices[0].message.content
        # Usuń znaczniki markdown i białe znaki
        clean_content = re.sub(r'```json\s*|\s*```', '', response_content).strip()
        st.write("Oczyszczona odpowiedź:", clean_content)
        
        try:
            result = json.loads(clean_content)
            return result
        except json.JSONDecodeError as e:
            st.error(f"Błąd parsowania JSON: {e}")
            st.write("Otrzymana odpowiedź:", clean_content)
            return None
    except Exception as e:
        st.error(f"Błąd podczas analizy obrazu: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Błąd podczas analizy obrazu: {str(e)}")
        return None

def save_to_spreadsheet(data):
    try:
        sheet = setup_google_sheets()
        row = [
            data['product_name'],
            data['expiry_date'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Błąd podczas zapisywania do arkusza: {str(e)}")
        return False

# Interface główny
st.write("### 1. Zrób zdjęcie produktu")

# Obsługa zdjęć
camera_input = st.camera_input("Zrób zdjęcie produktu")
if camera_input is not None and camera_input not in st.session_state.captured_images:
    # Dodaj zdjęcie do sesji tylko jeśli jeszcze nie istnieje
    st.session_state.captured_images.append(camera_input)
    st.success(f"Dodano zdjęcie! Liczba zdjęć: {len(st.session_state.captured_images)}")
    st.experimental_rerun()  # Odśwież stronę po dodaniu zdjęcia

# Wyświetlanie zrobionych zdjęć
if st.session_state.captured_images:
    st.write("### Zrobione zdjęcia:")
    
    for idx, img in enumerate(st.session_state.captured_images):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.image(img, caption=f"Zdjęcie {idx + 1}", use_column_width=True)
        with col2:
            if st.button(f"Usuń zdjęcie {idx + 1}", key=f"delete_{idx}"):
                st.session_state.captured_images.pop(idx)
                st.experimental_rerun()

    st.write("### 2. Analiza zdjęć")
    if st.button("Analizuj wszystkie zdjęcia"):
        with st.spinner("Analizuję zdjęcia..."):
            for img in st.session_state.captured_images:
                st.write("Analizuję kolejne zdjęcie...")
                result = analyze_image(img)
                if result:
                    st.session_state.analysis_results.append(result)
                    if save_to_spreadsheet(result):
                        st.success(f"Zapisano produkt: {result['product_name']}")
                st.write("---")

# Wyświetlanie wyników
if st.session_state.analysis_results:
    st.write("### 3. Wyniki analizy")
    for i, result in enumerate(st.session_state.analysis_results):
        st.write(f"Produkt {i+1}:")
        st.write(f"- Nazwa: {result['product_name']}")
        st.write(f"- Data ważności: {result['expiry_date']}")

# Przycisk do wyczyszczenia sesji
if st.button("Wyczyść wszystko"):
    st.session_state.captured_images = []
    st.session_state.analysis_results = []
    st.experimental_rerun()