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
    }
</style>
""", unsafe_allow_html=True)

# Inicjalizacja stanu sesji
if 'products' not in st.session_state:
    # Automatycznie dodaj pierwszy produkt przy starcie
    st.session_state.products = [{"id": str(uuid.uuid4()), "images": []}]
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = []

# Konfiguracja OpenAI
openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def setup_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["google_credentials"], scope)
    client = gspread.authorize(creds)
    sheet = client.open(st.secrets["spreadsheet_name"]).sheet1
    return sheet

def process_image(image_file):
    image = Image.open(image_file)
    baseheight = 300
    hpercent = (baseheight/float(image.size[1]))
    wsize = int((float(image.size[0])*float(hpercent)))
    image = image.resize((wsize, baseheight), Image.Resampling.LANCZOS)
    
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf

def analyze_product_images(images):
    import json
    import re
    
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
        content = [
            {
                "type": "text",
                "text": """Przeanalizuj te zdjęcia produktu i znajdź następujące informacje:
1. Nazwa produktu
2. Data ważności (w formacie YYYY-MM-DD)

Odpowiedz dokładnie w tym formacie:
{"product_name": "pełna nazwa produktu", "expiry_date": "YYYY-MM-DD"}

Jeśli nie możesz znaleźć którejś informacji, użyj null."""
            }
        ]
        content.extend(image_contents)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
            max_tokens=300
        )
        
        response_content = response.choices[0].message.content
        clean_content = re.sub(r'```json\s*|\s*```', '', response_content).strip()
        return json.loads(clean_content)
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

# Interface główny
st.title("🥫 FreshTrack - Skaner Produktów")

# Sekcja kamery
camera_input = st.camera_input("📸 Zrób zdjęcie", key="camera")
if camera_input is not None:
    # Zabezpieczenie przed duplikacją - sprawdzamy czy to zdjęcie już istnieje
    processed_image = process_image(camera_input)
    current_images = st.session_state.products[-1]["images"]
    
    # Porównujemy nowe zdjęcie z istniejącymi
    is_duplicate = False
    if current_images:
        new_data = processed_image.getvalue()
        for existing_img in current_images:
            if existing_img.getvalue() == new_data:
                is_duplicate = True
                break
    
    if not is_duplicate:
        st.session_state.products[-1]["images"].append(processed_image)
        st.rerun()

# Przycisk nowego produktu
if st.button("➕ Nowy produkt", type="primary"):
    st.session_state.products.append({"id": str(uuid.uuid4()), "images": []})
    st.rerun()

# Wyświetlanie produktów
for idx, product in enumerate(st.session_state.products):
    st.markdown(f"### 📦 Produkt {idx + 1}")
    
    if product["images"]:
        # Wyświetl zdjęcia w rzędzie
        cols = st.columns(len(product["images"]))
        for img_idx, img in enumerate(product["images"]):
            with cols[img_idx]:
                st.image(img, use_container_width=True)
                if st.button("🗑️ Usuń", key=f"delete_{product['id']}_{img_idx}"):
                    product["images"].pop(img_idx)
                    st.rerun()
    else:
        st.info("Zrób zdjęcie produktu...")
    
    # Przycisk usuwania produktu
    if len(st.session_state.products) > 1:  # Nie pozwól usunąć ostatniego produktu
        if st.button("🗑️ Usuń produkt", key=f"delete_product_{product['id']}"):
            st.session_state.products.remove(product)
            st.rerun()
    
    st.markdown("---")

# Przycisk analizy wszystkich produktów
if any(len(p["images"]) > 0 for p in st.session_state.products):
    if st.button("🔍 Analizuj wszystkie produkty", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_products = len([p for p in st.session_state.products if p["images"]])
        processed = 0
        
        for product in st.session_state.products:
            if product["images"]:
                processed += 1
                progress_bar.progress(processed / total_products)
                status_text.text(f"Analizuję produkt {processed} z {total_products}...")
                
                result = analyze_product_images(product["images"])
                if result:
                    st.session_state.analysis_results.append(result)
                    if save_to_spreadsheet(result):
                        st.success(f"✅ Zapisano: {result['product_name']}")
        
        # Wyczyść po zakończeniu
        st.session_state.products = [{"id": str(uuid.uuid4()), "images": []}]  # Nowy produkt po analizie
        progress_bar.empty()
        status_text.empty()
        st.rerun()

# Przycisk do wyczyszczenia wszystkiego
if st.sidebar.button("🗑️ Wyczyść wszystko"):
    st.session_state.products = [{"id": str(uuid.uuid4()), "images": []}]
    st.session_state.analysis_results = []
    st.rerun()