import os
import glob
import requests
import threading
from flask import Flask, request, jsonify
# --- IMPORTACIÓN ROBUSTA (Soluciona el ImportError) ---
import google.generativeai as genai 
from google.generativeai import types
# ----------------------------------------------------

# --- CONFIGURACIÓN DE ACCESO ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

if not TOKEN:
    # Esto detiene el servidor si falta la variable de entorno
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# --- PROMPT ENGINEERING: DEFINICIÓN DEL ROL ---
SYSTEM_INSTRUCTION = (
    "Eres un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. "
    "**Prioriza el contenido de los archivos de contexto (PDFs) para responder preguntas sobre la materia principal.** "
    "Si la información específica no se encuentra en el material de estudio, **utiliza tu conocimiento general para proveer una respuesta completa y útil.** "
    "Responde siempre en español. **Recuerda el historial de la conversación actual para responder preguntas de seguimiento o información personal que te den.**"
)

app = Flask(__name__)
model = None
global_file_handles = [] 
chat_sessions = {} # Diccionario para almacenar las sesiones de chat de cada usuario
# ------------------------------

# --- FUNCIÓN DE AUTO-CARGA DE ARCHIVOS (ESTABILIZADA) ---
def upload_and_configure_gemini():
    """
    Sube los PDFs de la carpeta 'documentos' a Gemini al iniciar. 
    NO USA genai.Client() para evitar el error.
    """
    global model, global_file_handles
    
    if not GEMINI_API_KEY:
        print("❌ ERROR: No hay GEMINI_API_KEY.")
        return

    try:
        # Configuración estándar para toda la aplicación
        genai.configure(api_key=GEMINI_API_KEY)
        
        uploaded_files = []
        # El Dockerfile ya asegura que la carpeta 'documentos' esté aquí.
        pdf_files = glob.glob("documentos/*.pdf")
        
        print(f"DEBUG: Archivos PDF encontrados localmente: {pdf_files}")
        
        if not pdf_files:
            print("⚠️ ADVERTENCIA: No se encontraron PDFs en la carpeta 'documentos'.")
        
        print(f"📂 Iniciando carga de {len(pdf_files)} documentos...")
        
        for pdf_path in pdf_files:
            try:
                # 🟢 Subida de archivo usando la función directa, la forma correcta:
                file_ref = genai.upload_file(file=pdf_path, mime_type="application/pdf")
                uploaded_files.append(file_ref)
                print(f"   ✅ Carga exitosa: {pdf_path} -> {file_ref.name}")
            except Exception as e:
                print(f"   ❌ ERROR CRÍTICO al subir {pdf_path}: {e}")
            
        print(f"DEBUG: Total de referencias de archivo subidas con éxito: {len(uploaded_files)}")

        # Configuramos el modelo que usaremos para el chat
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
        )
        
        global_file_handles = uploaded_files

    except Exception as e:
        # Aquí saltará si el API Key es inválido o hay otro error de configuración
        print(f"❌ FALLO CRÍTICO AL SUBIR ARCHIVOS O CONFIGURAR MODELO: {e}")

# --- INICIALIZACIÓN GLOBAL ---
# ESTA LÍNEA EJECUTA LA CARGA AL ARRANCAR EL SERVIDOR
print("--- SISTEMA DE AUTO-CARGA INICIADO ---")
upload_and_configure_gemini()
# -----------------------------

# --- FUNCIÓN PRINCIPAL DE RESPUESTA CON MEMORIA Y RAG ---
def generate_ai_response(chat_id, prompt_text):
    """Genera respuesta usando el modelo, manteniendo el estado de la conversación."""
    global model, global_file_handles, chat_sessions
    
    if not model:
        return "El modelo de IA no está configurado. Revisa el log de errores."

    try:
        # 1. Recuperar o Crear Sesión de Chat
        if chat_id not in chat_sessions:
            print(f"💬 Creando nueva sesión de chat para: {chat_id}")
            
            initial_history = []
            if global_file_handles:
                # Pasamos la instrucción del sistema y los archivos RAG en el primer turno del usuario
                user_parts = global_file_handles + [
                    types.Part.from_text("Actúa bajo la siguiente instrucción: " + SYSTEM_INSTRUCTION)
                ]
                initial_history.append(types.Content(
                    role='user', 
                    parts=user_parts
                ))
                # El modelo responde 'Entendido' para inicializar el historial y el contexto.
                initial_history.append(types.Content(
                    role='model', 
                    parts=[types.Part.from_text('Entendido. Soy el Asistente de Estudio de Sistemas Inteligentes. Estoy listo para tus preguntas.')]
                ))
            
            chat_sessions[chat_id] = model.start_chat(
                history=initial_history 
            )

        chat = chat_sessions[chat_id]
        
        # 2. Enviar Mensaje y recibir respuesta
        # send_message gestiona la historia automáticamente
        response = chat.send_message(prompt_text)
        
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
    response = generate_ai_response(chat_id, message_text)
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