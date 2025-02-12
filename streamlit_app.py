import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import io
import base64
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid

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
    .product-card {
        border: 1px solid #eee;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .image-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 0.5rem;
        padding: 0.5rem;
    }
    .camera-container {
        background: white;
        padding: 1rem 0;
        border-bottom: 1px solid #eee;
    }
</style>
""", unsafe_allow_html=True)

# Inicjalizacja stanu sesji
if 'products' not in st.session_state:
    st.session_state.products = []  # Lista produktów, każdy produkt to słownik {id, images}
if 'current_product_id' not in st.session_state:
    st.session_state.current_product_id = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = []

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

def analyze_product_images(images):
    import json
    import re
    
    # Przygotuj listę obrazów w formacie base64
    image_contents = []
    for img in images:
        image_data = img.getvalue()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        image_contents.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        })
    
    try:
        # Dodaj tekst na początku listy content
        content = [
            {
                "type": "text",
                "text": """Przeanalizuj te zdjęcia produktu i znajdź następujące informacje:
1. Nazwa produktu
2. Data ważności (w formacie YYYY-MM-DD)

Odpowiedz dokładnie w tym formacie, bez dodatkowych znaczników czy komentarzy:
{"product_name": "pełna nazwa produktu", "expiry_date": "YYYY-MM-DD"}

Jeśli nie możesz znaleźć którejś informacji, użyj null."""
            }
        ]
        content.extend(image_contents)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": content
            }],
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
        st.error(f"Błąd podczas analizy obrazów: {str(e)}")
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

def process_image(image_file):
    # Zmniejsz rozmiar zdjęcia
    image = Image.open(image_file)
    baseheight = 300
    hpercent = (baseheight/float(image.size[1]))
    wsize = int((float(image.size[0])*float(hpercent)))
    image = image.resize((wsize, baseheight), Image.Resampling.LANCZOS)
    
    # Zapisz zmniejszone zdjęcie
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf

# Interface główny
st.title("🥫 FreshTrack - Skaner Produktów")

# Przyciski nawigacyjne
col1, col2 = st.columns(2)
with col1:
    if st.button("➕ Nowy produkt", use_container_width=True):
        new_product_id = str(uuid.uuid4())
        st.session_state.products.append({"id": new_product_id, "images": []})
        st.session_state.current_product_id = new_product_id
        st.rerun()

# Sekcja kamery
camera_input = st.camera_input("📸 Zrób zdjęcie", key="camera")
if camera_input is not None:
    # Jeśli nie ma aktywnego produktu, stwórz nowy
    if st.session_state.current_product_id is None:
        new_product_id = str(uuid.uuid4())
        st.session_state.products.append({"id": new_product_id, "images": []})
        st.session_state.current_product_id = new_product_id
    
    # Znajdź aktywny produkt i dodaj do niego zdjęcie
    for product in st.session_state.products:
        if product["id"] == st.session_state.current_product_id:
            processed_image = process_image(camera_input)
            product["images"].append(processed_image)
            st.rerun()

# Wyświetlanie produktów
for idx, product in enumerate(st.session_state.products):
    with st.container():
        st.markdown(f"### 📦 Produkt {idx + 1}")
        
        # Siatka zdjęć
        if product["images"]:
            cols = st.columns(len(product["images"]))
            for img_idx, img in enumerate(product["images"]):
                with cols[img_idx]:
                    st.image(img, use_container_width=True)
                    if st.button("🗑️", key=f"delete_{product['id']}_{img_idx}"):
                        product["images"].pop(img_idx)
                        st.rerun()
        
        # Przyciski akcji
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📸 Dodaj zdjęcie", key=f"add_{product['id']}", 
                        disabled=st.session_state.current_product_id != product["id"]):
                st.session_state.current_product_id = product["id"]
        with col2:
            if st.button("🗑️ Usuń produkt", key=f"delete_product_{product['id']}"):
                st.session_state.products.remove(product)
                if st.session_state.current_product_id == product["id"]:
                    st.session_state.current_product_id = None
                st.rerun()
        
        st.markdown("---")

# Przycisk analizy
if st.session_state.products:
    if st.button("🔍 Analizuj wszystkie produkty", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, product in enumerate(st.session_state.products):
            if product["images"]:
                progress = (idx + 1) / len(st.session_state.products)
                progress_bar.progress(progress)
                status_text.text(f"Analizuję produkt {idx + 1} z {len(st.session_state.products)}...")
                
                result = analyze_product_images(product["images"])
                if result:
                    st.session_state.analysis_results.append(result)
                    if save_to_spreadsheet(result):
                        st.success(f"✅ Zapisano: {result['product_name']}")
        
        progress_bar.empty()
        status_text.empty()
        st.session_state.products = []
        st.session_state.current_product_id = None
        st.rerun()

# Przycisk do wyczyszczenia sesji
if st.sidebar.button("🗑️ Wyczyść wszystko"):
    st.session_state.products = []
    st.session_state.current_product_id = None
    st.session_state.analysis_results = []
    st.rerun()