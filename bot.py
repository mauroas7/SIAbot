import os
import requests
from flask import Flask, request, jsonify
from google import genai # Importar la librería de Gemini
from google.genai.errors import APIError # Para manejar errores

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Nueva clave
if not TOKEN or not GEMINI_API_KEY:
    raise ValueError("Faltan variables de entorno (TOKEN o GEMINI_API_KEY).")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Inicializar el cliente de Gemini
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
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
        # Configuración del modelo con el rol definido (System Instruction)
        config = genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Llamada a la API de Gemini
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Un modelo rápido y potente
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
    # ... (Esta función sigue igual) ...
    url = TELEGRAM_API_URL + "sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload).raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar respuesta: {e}")

@app.route('/webhook', methods=['POST'])
def receive_update():
    update_data = request.json
    
    try:
        message_data = update_data.get('message', {})
        chat_id = message_data.get('chat', {}).get('id')
        message_text = message_data.get('text')
        
        if chat_id and message_text:
            print(f"Pregunta recibida: {message_text}")
            
            # --- Lógica de la IA (Reemplaza el 'eco') ---
            ai_response = generate_ai_response(message_text)
            
            # Envía la respuesta generada por la IA
            send_reply(chat_id, ai_response)
        # ... (Manejo de mensajes sin texto sigue igual) ...
        
    except Exception as e:
        print(f"Error procesando el update: {e}")

    return jsonify(success=True), 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)    app.run(host='0.0.0.0', port=PORT)
