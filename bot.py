import os
import requests
import threading
from flask import Flask, request, jsonify
from google import genai 
from google.genai.errors import APIError

# --- CONFIGURACIÓN DE ACCESO ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# El bot NO puede funcionar sin el token de Telegram. Si falta, detenemos el deploy.
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Inicializamos el cliente de Gemini como None. Su inicialización se hace 
# de forma segura en la función get_gemini_client (inicialización perezosa).
client = None
# -------------------------------

# --- PROMPT ENGINEERING: DEFINICIÓN DEL ROL ---
SYSTEM_INSTRUCTION = (
    "Eres un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. Mantén tus respuestas en español. No inventes información."
)
# -----------------------------------------------

app = Flask(__name__)

def get_gemini_client():
    """Inicializa el cliente de Gemini de forma segura si no está inicializado."""
    global client
    # Si el cliente es None (primera ejecución) Y tenemos una clave de API
    if client is None and GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("Cliente Gemini inicializado exitosamente.")
        except Exception as e:
            print(f"FALLO DE INICIALIZACIÓN DE GEMINI: {e}")
            return None # Retorna None si la inicialización falla
    # Si el cliente ya existe o falló la inicialización, lo devuelve
    return client

def generate_ai_response(prompt_text):
    """Genera una respuesta usando el modelo Gemini."""
    ai_client = get_gemini_client()
    
    # Notifica al usuario si el cliente no se pudo inicializar
    if not ai_client:
        return "Disculpa, no puedo acceder al modelo de IA. Verifica la configuración de la clave de Gemini (GEMINI_API_KEY)."

    try:
        config = genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Llamada al modelo
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_text,
            config=config
        )
        
        return response.text
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return "Disculpa, la API de Gemini rechazó la solicitud. Revisa la validez de tu clave."
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
    # 1. Generar la respuesta de la IA (Lento)
    ai_response = generate_ai_response(message_text)
    # 2. Enviar la respuesta a Telegram (Rápido)
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
        
        # Si no hay texto, devolvemos 200 OK
        print("Mensaje no procesable (sticker, etc.)")
        return jsonify(success=True), 200 
            
    except Exception as e:
        print(f"Error procesando el update: {e}")
        # En caso de error, devolvemos 200 OK para no romper el Webhook
        return jsonify(success=False, error=str(e)), 200

if __name__ == '__main__':
    # El puerto es asignado por Render (o se usa 8080 por defecto)
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)
