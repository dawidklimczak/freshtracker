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
st.set_page_config(
    page_title="FreshTrack - Skaner Produktów",
    page_icon="🥫",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Customowy CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 1rem;
    }
    .stButton>button {
        width: 100%;
    }
    .product-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 1rem;
        padding: 1rem;
    }
    .status-message {
        padding: 0.5rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .camera-container {
        position: sticky;
        top: 0;
        z-index: 1000;
        background: white;
        padding: 1rem 0;
        border-bottom: 1px solid #eee;
    }
    .floating-analyze {
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        z-index: 1000;
    }
    div[data-testid="stVerticalBlock"] > div:has(> div.stButton) {
        position: sticky;
        bottom: 0;
        padding: 1rem;
        background: white;
        border-top: 1px solid #eee;
    }
</style>
""", unsafe_allow_html=True)

# Inicjalizacja stanu sesji
if 'captured_images' not in st.session_state:
    st.session_state.captured_images = []
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = []
if 'batch_size' not in st.session_state:
    st.session_state.batch_size = 0
if 'analyzing' not in st.session_state:
    st.session_state.analyzing = False

# Konfiguracja klientów
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
        
        response_content = response.choices[0].message.content
        clean_content = re.sub(r'```json\s*|\s*```', '', response_content).strip()
        
        try:
            result = json.loads(clean_content)
            return result
        except json.JSONDecodeError as e:
            st.error(f"Błąd parsowania JSON: {e}")
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
st.title("🥫 FreshTrack - Skaner Produktów")

# Tryb szybkiego skanowania
with st.container():
    # Sekcja kamery (przyklejona do góry)
    with st.container():
        st.markdown("### 📸 Zrób zdjęcie produktu")
        camera_col, status_col = st.columns([3, 1])
        with camera_col:
            camera_input = st.camera_input("", key="camera")
            if camera_input is not None and camera_input not in st.session_state.captured_images:
                # Zmniejsz rozmiar zdjęcia przed zapisaniem
                image = Image.open(camera_input)
                # Zachowaj proporcje, ale zmniejsz wysokość
                baseheight = 300
                hpercent = (baseheight/float(image.size[1]))
                wsize = int((float(image.size[0])*float(hpercent)))
                image = image.resize((wsize, baseheight), Image.Resampling.LANCZOS)
                
                # Zapisz zmniejszone zdjęcie
                buf = io.BytesIO()
                image.save(buf, format='JPEG', quality=85)
                buf.seek(0)
                
                st.session_state.captured_images.append(buf)
                st.session_state.batch_size += 1
        with status_col:
            st.metric("Zeskanowane", f"{len(st.session_state.captured_images)} produktów")

    # Siatka zdjęć
    if st.session_state.captured_images:
        st.markdown("### 📦 Zeskanowane produkty")
        cols = st.columns(4)
        for idx, img in enumerate(st.session_state.captured_images):
            with cols[idx % 4]:
                st.image(img, use_container_width=True)
                if st.button("🗑️ Usuń", key=f"delete_{idx}"):
                    st.session_state.captured_images.pop(idx)
                    st.session_state.batch_size -= 1
                    st.rerun()

# Przycisk analizy (pływający)
if st.session_state.captured_images and not st.session_state.analyzing:
    if st.button(f"🔍 Analizuj wszystkie ({len(st.session_state.captured_images)}) produkty", type="primary"):
        st.session_state.analyzing = True
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, img in enumerate(st.session_state.captured_images):
            progress = (idx + 1) / len(st.session_state.captured_images)
            progress_bar.progress(progress)
            status_text.text(f"Analizuję produkt {idx + 1} z {len(st.session_state.captured_images)}...")
            
            result = analyze_image(img)
            if result:
                st.session_state.analysis_results.append(result)
                if save_to_spreadsheet(result):
                    st.success(f"✅ Zapisano: {result['product_name']}")
        
        progress_bar.empty()
        status_text.empty()
        st.session_state.analyzing = False
        st.session_state.captured_images = []
        st.session_state.batch_size = 0
        st.rerun()

# Wyświetlanie ostatnich wyników
if st.session_state.analysis_results:
    with st.expander("📊 Ostatnio przeanalizowane produkty", expanded=False):
        for result in reversed(st.session_state.analysis_results[-5:]):
            st.write(f"✅ {result['product_name']} - ważne do: {result['expiry_date'] or 'nie znaleziono'}")

# Przycisk do wyczyszczenia sesji
if st.sidebar.button("🗑️ Wyczyść wszystko"):
    st.session_state.captured_images = []
    st.session_state.analysis_results = []
    st.session_state.batch_size = 0
    st.session_state.analyzing = False
    st.rerun()