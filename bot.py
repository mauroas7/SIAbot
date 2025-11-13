import os
import requests
from flask import Flask, request, jsonify

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado como variable de entorno.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"
# ---------------------

app = Flask(__name__)

def send_reply(chat_id, text):
    """Envía un mensaje al chat_id especificado."""
    url = TELEGRAM_API_URL + "sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    
    try:
        requests.post(url, json=payload).raise_for_status()
        print(f"Respuesta enviada a chat {chat_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar respuesta: {e}")

@app.route('/webhook', methods=['POST'])
def receive_update():
    """Ruta que recibe las peticiones POST de Telegram."""
    update_data = request.json
    
    try:
        message_data = update_data.get('message', {})
        chat_id = message_data.get('chat', {}).get('id')
        message_text = message_data.get('text')
        user_first_name = message_data.get('from', {}).get('first_name', 'Usuario')

        if chat_id and message_text:
            # --- Aquí se integrará la lógica de Sistemas Inteligentes ---
            # Por ahora, un eco de prueba:
            reply_text = f"🤖 Hola, *{user_first_name}*.\n\n"
            reply_text += "¡Mi despliegue en Render fue exitoso!\n"
            reply_text += f"\n_Me dijiste: '{message_text}'_"
            
            send_reply(chat_id, reply_text)
        else:
            print("Mensaje no procesable.")
            
    except Exception as e:
        print(f"Error procesando el update: {e}")

    return jsonify(success=True), 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)