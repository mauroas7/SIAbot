import os
import requests
import threading
from flask import Flask, request, jsonify
import google.generativeai as genai 

# --- CONFIGURACIÓN DE ACCESO ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# LÓGICA RAG: Lee los IDs de archivo
GEMINI_FILE_NAMES = os.environ.get("GEMINI_FILE_NAMES", "").split(',')
GEMINI_FILE_NAMES = [name.strip() for name in GEMINI_FILE_NAMES if name.strip()]

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está configurado.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# --- PROMPT ENGINEERING (FINAL) ---
SYSTEM_INSTRUCTION = (
    "Eres un Asistente de Estudio experto en Sistemas Inteligentes, Bot conversacionales, "
    "APIs y Webhooks. Tu objetivo es educar. Responde a las preguntas del estudiante "
    "de manera clara, concisa, profesional y usando la terminología técnica adecuada "
    "de la materia. "
    
    "**Prioriza el contenido de los archivos de contexto (PDFs) para responder preguntas sobre la materia principal.** "
    "Si la información específica no se encuentra en el material de estudio, **utiliza tu conocimiento general para proveer una respuesta completa y útil.** "
    "Responde siempre en español."
)
# ----------------------------------------

# --- INICIALIZACIÓN DEL MODELO ---
model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=SYSTEM_INSTRUCTION
        )
        print("Modelo Gemini 2.5 Flash inicializado exitosamente.")
        if GEMINI_FILE_NAMES:
            print(f"Archivos RAG detectados: {GEMINI_FILE_NAMES}")
        else:
            print("Advertencia: No se encontraron GEMINI_FILE_NAMES. Operando sin RAG.")
            
    except Exception as e:
        print(f"FALLO DE INICIALIZACIÓN DE GEMINI (al inicio): {e}")
else:
    print("Advertencia: GEMINI_API_KEY no encontrada. El bot no podrá responder.")
# ---------------------------------

app = Flask(__name__)

def generate_ai_response(prompt_text):
    """Genera una respuesta usando el modelo Gemini, con RAG si hay archivos."""
    
    if not model:
        return "Disculpa, el modelo de IA no está disponible. Revisa la configuración (GEMINI_API_KEY)."

    try:
        contents_for_gemini = [] # Lista de contenidos para la IA

        # LÓGICA RAG
        if GEMINI_FILE_NAMES:
            print(f"Usando archivos RAG: {GEMINI_FILE_NAMES}")
            for name in GEMINI_FILE_NAMES:
                file_handle = genai.get_file(name=name) 
                contents_for_gemini.append(file_handle)
        
        contents_for_gemini.append(prompt_text)
        
        # Generamos la respuesta
        response = model.generate_content(
            contents=contents_for_gemini,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1 # Baja temperatura para priorizar contenido RAG
            )
        )
        
        return response.text
    
    except Exception as e:
        print(f"EXCEPCIÓN NO CONTROLADA DURANTE API CALL: {e}") 

        if "API key" in str(e):
            return "Error de API: La clave de Gemini es inválida o está mal configurada."
        if "not found" in str(e).lower() and "files/" in str(e):
             return f"Error de RAG: No se pudo encontrar uno de los archivos. Revisa los IDs en GEMINI_FILE_NAMES."
        
        return "Ocurrió un error inesperado al contactar a la IA."

def send_reply(chat_id, text):
    """Envía un mensaje al chat_id especificado, con correcciones para el error 400."""
    
    # CORRECCIÓN 1: Trunca el texto si es demasiado largo (4000 caracteres de buffer)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (Mensaje truncado por límite de Telegram)"
        
    url = TELEGRAM_API_URL + "sendMessage"
    
    # CORRECCIÓN 2: Eliminamos 'parse_mode' para evitar el error 400 por formato
    payload = {'chat_id': chat_id, 'text': text} 
    
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
            
            ai_thread = threading.Thread(
                target=background_ai_task, 
                args=(chat_id, message_text)
            )
            ai_thread.start()
            
            return jsonify(success=True, status="Processing in background"), 200
        
        return jsonify(success=True), 200 
            
    except Exception as e:
        print(f"Error procesando el update: {e}")
        return jsonify(success=False, error=str(e)), 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 8080)) 
    app.run(host='0.0.0.0', port=PORT)