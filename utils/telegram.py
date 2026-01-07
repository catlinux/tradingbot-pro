# Archivo: gridbot_binance/utils/telegram.py
import requests
import os
import threading
import json5
from dotenv import load_dotenv
from utils.logger import log

# Cargamos variables de entorno
load_dotenv(dotenv_path='config/.env')

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CONFIG_PATH = 'config/config.json5'

def _check_enabled():
    """Lee la configuración para ver si Telegram está activado"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                conf = json5.load(f)
                return conf.get('system', {}).get('telegram_enabled', True)
    except Exception as e:
        log.debug(f"Error reading telegram config: {e}")
        return True  # En caso de duda, activado
    return True

def _send_request(message):
    """Función interna que hace la petición HTTP"""
    if not TOKEN or not CHAT_ID:
        return
    
    # Comprobación de configuración
    if not _check_enabled():
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")

def send_msg(text):
    """
    Envía un mensaje a Telegram en un hilo separado para no bloquear el Bot.
    Acepta HTML (negritas <b>, cursivas <i>, etc).
    """
    if not TOKEN or not CHAT_ID:
        return

    # Ejecutamos en un thread (Daemon) para que el bot no se pare esperando a Telegram
    threading.Thread(target=_send_request, args=(text,), daemon=True).start()