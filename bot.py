import os
import requests
import threading
from flask import Flask, request, jsonify
from google import genai 
from google.genai.errors import APIError

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 
if not TOKEN or not GEMINI_API_KEY:
    # Esto solo se ejecuta al iniciar el contenedor.
    raise ValueError("Faltan variables de entorno (TOKEN o GEMINI_API_KEY).")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Inicializar el cliente de Gemini
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    # Esto ocurre si la clave es inválida al inicio.
    print(f"Error al inicializar el cliente Gemini: {e}")

# --- PROMPT ENGINEERING: DEFINICIÓN DEL ROL ---
SYSTEM_INSTRUCTION = (
    "Eres un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. Mantén tus respuestas en español. No inventes información."
)
# -----------------------------------------------

app = Flask(__name__)

def generate_ai_response(prompt_text):
    """Genera una respuesta usando el modelo Gemini."""
    try:
        config = genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_text,
            config=config
        )
        
        return response.text
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return "Disculpa, tengo un problema de conexión con el modelo de IA. Inténtalo de nuevo."
    except Exception as e:
        print(f"Error inesperado: {e}")
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

# --- NUEVA FUNCIÓN PARA CORRER EN SEGUNDO PLANO ---
def background_ai_task(chat_id, message_text):
    """
    Tarea que se ejecuta en un hilo separado. 
    Contiene la lógica lenta de la IA y el envío de la respuesta.
    """
    # 1. Generar la respuesta de la IA (Lento)
    ai_response = generate_ai_response(message_text)
    
    # 2. Enviar la respuesta a Telegram (Rápido)
    send_reply(chat_id, ai_response)
# ---------------------------------------------------


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
            
            # 1. Iniciar un hilo separado para la tarea lenta de la IA
            ai_thread = threading.Thread(
                target=background_ai_task, 
                args=(chat_id, message_text)
            )
            ai_thread.start()
            
            # 2. Devolver 200 OK INMEDIATAMENTE
            # ESTO es la clave para evitar el timeout de Telegram.
            return jsonify(success=True, status="Processing in background"), 200
        
        # Si no hay texto, devolvemos 200 OK para no reintentar el Webhook
        return jsonify(success=True), 200 
            
    except Exception as e:
        print(f"Error procesando el update: {e}")
        # En caso de error, siempre devolvemos 200 OK para evitar loops
        return jsonify(success=False, error=str(e)), 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)
