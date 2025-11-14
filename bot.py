import os
import requests
import threading
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.generativeai.errors import APIError

# --- CONFIGURACIÓN DE ACCESO ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# LÓGICA RAG: Lee los IDs de archivo (p. ej., 'files/abc,files/def')
# obtenidos al subir tus PDFs y los guarda en una lista.
GEMINI_FILE_NAMES = os.environ.get("GEMINI_FILE_NAMES", "").split(',')
GEMINI_FILE_NAMES = [name.strip() for name in GEMINI_FILE_NAMES if name.strip()]

# El bot NO puede funcionar sin el token de Telegram. Si falta, detenemos el deploy.
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Inicialización perezosa del cliente
client = None
# -------------------------------

# --- PROMPT ENGINEERING: DEFINICIÓN DEL ROL ---
SYSTEM_INSTRUCTION = (
    "Eres un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. **Debes basar tu respuesta estrictamente en los archivos de contexto "
    "proporcionados. Si la información no está en los archivos, respóndelo de manera cortés "
    "y sin inventar contenido. Mantén tus respuestas en español.**"
)
# -----------------------------------------------

app = Flask(__name__)

def get_gemini_client():
    """Inicializa el cliente de Gemini de forma segura si no está inicializado."""
    global client
    if client is None and GEMINI_API_KEY:
        try:
            # Usamos genai.Client() para poder interactuar con la API de Files
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("Cliente Gemini inicializado exitosamente.")
        except Exception as e:
            print(f"FALLO DE INICIALIZACIÓN DE GEMINI: {e}")
            return None
    return client

def generate_ai_response(prompt_text):
    """Genera una respuesta usando el modelo Gemini, con RAG si hay archivos."""
    ai_client = get_gemini_client()
    
    if not ai_client:
        return "Disculpa, no puedo acceder al modelo de IA. Verifica la configuración de la clave de Gemini (GEMINI_API_KEY)."

    try:
        contents_for_gemini = [prompt_text] # Por defecto, solo la pregunta

        # LÓGICA RAG: Si hay IDs de archivo, los inyectamos en la solicitud.
        if GEMINI_FILE_NAMES:
            print(f"Usando archivos RAG: {GEMINI_FILE_NAMES}")
            
            # 1. Obtiene las referencias (handles) de los archivos subidos.
            # Esta llamada busca los archivos por su ID ('files/...') en la API.
            file_handles = [ai_client.files.get(name=name) for name in GEMINI_FILE_NAMES]
            
            # 2. El contenido enviado será: Archivos (contexto) + Pregunta
            contents_for_gemini = file_handles + [prompt_text]
        else:
            print("Operando solo con conocimiento general de Gemini (sin RAG).")

        config = genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1 # Baja temperatura para fomentar respuestas fácticas (RAG)
        )
        
        # Llamada al modelo con los contenidos (archivos + pregunta)
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents_for_gemini,
            config=config
        )
        
        # El modelo genera citas automáticas cuando usa los archivos.
        return response.text
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return "Disculpa, la API de Gemini rechazó la solicitud. Revisa la validez de tu clave o el formato de GEMINI_FILE_NAMES."
    except Exception as e:
        print(f"Error inesperado en IA: {e}")
        return "Ocurrió un error inesperado al procesar tu solicitud."

def send_reply(chat_id, text):
    """Envía un mensaje al chat_id especificado."""
    url = TELEGRAM_API_URL + "sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload).raise_for_status()
        print(f"Respuesta enviada a chat {chat_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar respuesta: {e}")

# --- FUNCIÓN PARA CORRER EN SEGUNDO PLANO (ASÍNCRONO) ---
def background_ai_task(chat_id, message_text):
    """Tarea que se ejecuta en un hilo separado (no bloqueante)."""
    ai_response = generate_ai_response(message_text)
    send_reply(chat_id, ai_response)
# ---------------------------------------------


@app.route('/webhook', methods=['POST'])
def receive_update():
    """Ruta que recibe las peticiones POST de Telegram (el Webhook)."""
    update_data = request.json
    
    try:
        message_data = update_data.get('message', {})
        chat_id = message_data.get('chat', {}).get('id')
        message_text = message_data.get('text')
        
        if chat_id and message_text:
            print(f"Pregunta recibida: {message_text}")
            
            # Inicia un hilo separado para la tarea lenta de la IA
            ai_thread = threading.Thread(
                target=background_ai_task, 
                args=(chat_id, message_text)
            )
            ai_thread.start()
            
            # Devolver 200 OK INMEDIATAMENTE: La clave de la asincronía.
            return jsonify(success=True, status="Processing in background"), 200
        
        print("Mensaje no procesable (sticker, etc.)")
        return jsonify(success=True), 200 
            
    except Exception as e:
        print(f"Error procesando el update: {e}")
        return jsonify(success=False, error=str(e)), 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)