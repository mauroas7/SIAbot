import os
import time
import glob
import requests
import threading
from flask import Flask, request, jsonify
import google.generativeai as genai 

# --- CONFIGURACIÓN DE ACCESO CON LOS TOKENS ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# El bot buscará los archivos localmente en la carpeta 'documentos'

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# --- PROMPT ENGINEERING ---
SYSTEM_INSTRUCTION = (
    "Actúa como Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia, tratando de no sobrepasar el limite de escritura de Telegram. "
    "**Prioriza el contenido de los archivos de contexto (PDFs) para responder preguntas sobre la materia principal.** "
    "Si la información específica no se encuentra en el material de estudio, **utiliza tu conocimiento general para proveer una respuesta completa y útil.** "
    "Responde siempre en español."
)

app = Flask(__name__)
model = None
chat_session = None # Usaremos una sesión simple o gestión directa

# --- FUNCIÓN DE AUTO-CARGA DE ARCHIVOS ---
def upload_and_configure_gemini():
    """Sube los PDFs de la carpeta 'documentos' a Gemini al iniciar."""
    global model
    
    if not GEMINI_API_KEY:
        print("❌ ERROR: No hay GEMINI_API_KEY.")
        return

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        uploaded_files = []
        
        # Buscamos todos los PDFs en la carpeta 'documentos'
        pdf_files = glob.glob("documentos/*.pdf")
        
        if not pdf_files:
            print("⚠️ ADVERTENCIA: No se encontraron PDFs en la carpeta 'documentos'.")
        
        print(f"📂 Iniciando carga de {len(pdf_files)} documentos...")
        
        for pdf_path in pdf_files:
            print(f"   Subiendo: {pdf_path}...")
            # Subimos el archivo a la nube de Google (Temporal por 48hs)
            # Como el bot se reinicia en Render, esto renueva los archivos siempre.
            file_ref = genai.upload_file(pdf_path, mime_type="application/pdf")
            uploaded_files.append(file_ref)
            
        print(f"✅ ¡Éxito! {len(uploaded_files)} archivos cargados y listos para usar.")

        # Configuramos el modelo con los archivos YA cargados
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Guardamos la lista de archivos en una variable global para usarlos en el chat
        return uploaded_files

    except Exception as e:
        print(f"❌ FALLO CRÍTICO AL SUBIR ARCHIVOS: {e}")
        return []

# --- INICIALIZACIÓN GLOBAL ---
# Ejecutamos la subida UNA VEZ cuando arranca el servidor
print("--- SISTEMA DE AUTO-CARGA INICIADO ---")
global_file_handles = upload_and_configure_gemini()
# -----------------------------

def generate_ai_response(prompt_text):
    """Genera respuesta usando los archivos que acabamos de subir."""
    global model, global_file_handles
    
    if not model:
        return "El sistema está iniciándose o hubo un error de configuración."

    try:
        # Preparamos el contenido: Archivos + Pregunta
        contents = []
        
        # Añadimos los archivos cargados al contexto
        if global_file_handles:
            contents.extend(global_file_handles)
            
        contents.append(prompt_text)
        
        # Generamos respuesta
        response = model.generate_content(
            contents,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1
            )
        )
        return response.text
    
    except Exception as e:
        print(f"Error AI: {e}")
        return "Ocurrió un error al procesar tu solicitud. Intenta de nuevo en unos segundos."

def send_reply(chat_id, text):
    """Envía mensaje a Telegram (con protección anti-errores 400)."""
    if len(text) > 4000:
        text = text[:4000] + "\n\n(Truncado...)"
        
    url = TELEGRAM_API_URL + "sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

def background_ai_task(chat_id, message_text):
    response = generate_ai_response(message_text)
    send_reply(chat_id, response)

@app.route('/webhook', methods=['POST'])
def receive_update():
    update_data = request.json
    try:
        if 'message' in update_data:
            chat_id = update_data['message']['chat']['id']
            text = update_data['message'].get('text')
            
            if text:
                threading.Thread(target=background_ai_task, args=(chat_id, text)).start()
                
        return jsonify(success=True), 200
    except Exception:
        return jsonify(success=False), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)