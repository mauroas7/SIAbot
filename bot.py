import os
import glob
import requests
import threading
from flask import Flask, request, jsonify
import google.generativeai as genai 

# --- CONFIGURACIÓN DE ACCESO ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# --- PROMPT ENGINEERING: DEFINICIÓN DEL ROL ---
SYSTEM_INSTRUCTION = (
    "Actúa como un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. Tratando de no sobrepasar el limite de escritura de Telegram."
    "**Prioriza el contenido de los archivos de contexto (PDFs) para responder preguntas sobre la materia principal.** "
    "Si la información específica no se encuentra en el material de estudio, **utiliza tu conocimiento general para proveer una respuesta completa y útil.** "
    "Responde siempre en español. **Recuerda el historial de la conversación actual para responder preguntas de seguimiento o información personal que te den.**"
)

app = Flask(__name__)
model = None
global_file_handles = [] 
# Diccionario global para almacenar las sesiones de chat de cada usuario
chat_sessions = {} 
# ------------------------------

# --- FUNCIÓN DE AUTO-CARGA DE ARCHIVOS ---
def upload_and_configure_gemini():
    """Sube los PDFs de la carpeta 'documentos' a Gemini al iniciar."""
    global model, global_file_handles
    
    if not GEMINI_API_KEY:
        print("❌ ERROR: No hay GEMINI_API_KEY.")
        return

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        uploaded_files = []
        
        pdf_files = glob.glob("documentos/*.pdf")
        
        print(f"📂 Iniciando carga de {len(pdf_files)} documentos...")
        
        for pdf_path in pdf_files:
            print(f"   Subiendo: {pdf_path}...")
            # Subimos el archivo a la nube (Temporal por 48hs, pero se renueva en cada deploy)
            file_ref = genai.upload_file(pdf_path, mime_type="application/pdf")
            uploaded_files.append(file_ref)
            
        print(f"✅ ¡Éxito! {len(uploaded_files)} archivos cargados.")

        # Configuramos el modelo que usará la instrucción del sistema
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        global_file_handles = uploaded_files

    except Exception as e:
        print(f"❌ FALLO CRÍTICO AL SUBIR ARCHIVOS O CONFIGURAR MODELO: {e}")

# --- INICIALIZACIÓN GLOBAL ---
print("--- SISTEMA DE AUTO-CARGA INICIADO ---")
upload_and_configure_gemini()
# -----------------------------


# --- FUNCIÓN PRINCIPAL DE RESPUESTA CON MEMORIA ---
def generate_ai_response(chat_id, prompt_text):
    """Genera respuesta usando el modelo, manteniendo el estado de la conversación."""
    global model, global_file_handles, chat_sessions
    
    if not model:
        return "El modelo de IA no está configurado."

    try:
        # 1. Recuperar o Crear Sesión de Chat
        if chat_id not in chat_sessions:
            print(f"💬 Creando nueva sesión de chat para: {chat_id}")
            
            # **AQUÍ ESTÁ EL CAMBIO DE SINTAXIS:**
            # Pasamos los archivos RAG como el primer contenido en el historial.
            initial_history = []
            if global_file_handles:
                # El primer turno debe ser el contexto (los archivos)
                initial_history.append(genai.types.Content(
                    role='user', 
                    parts=global_file_handles
                ))
                # La respuesta inicial del modelo debe estar vacía para no arruinar el chat
                initial_history.append(genai.types.Content(
                    role='model', 
                    parts=[genai.types.Part.from_text('Entendido. Estoy listo para las preguntas.')]
                ))
            
            chat_sessions[chat_id] = model.start_chat(
                history=initial_history 
                # Ya no se usa: config={"context": global_file_handles}
            )

        chat = chat_sessions[chat_id]
        
        # 2. Enviar Mensaje y recibir respuesta
        # La función send_message maneja la historia automáticamente
        response = chat.send_message(prompt_text)
        
        return response.text
    
    except Exception as e:
        # ... (el resto del bloque except sigue igual)
        print(f"Error AI: {e}")
        return "Ocurrió un error al procesar tu solicitud. Intenta de nuevo en unos segundos."

def send_reply(chat_id, text):
    """Envía mensaje a Telegram (con protección anti-errores 400)."""
    # Trunca el mensaje si es demasiado largo para Telegram
    if len(text) > 4000:
        text = text[:4000] + "\n\n(Truncado...)"
        
    url = TELEGRAM_API_URL + "sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

def background_ai_task(chat_id, message_text):
    # Pasamos el chat_id para que generate_ai_response sepa qué sesión usar
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
                # La lógica de IA ahora se corre en un hilo, incluyendo la gestión de sesión
                ai_thread = threading.Thread(target=background_ai_task, args=(chat_id, text))
                ai_thread.start()
                
        return jsonify(success=True), 200
    except Exception:
        return jsonify(success=False), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)