# Archivo: gridbot_binance/main.py
from core.bot import GridBot
from utils.logger import log
from web.server import start_server
from utils.telegram import send_msg 
import sys
import os
from dotenv import load_dotenv
from colorama import Fore, Style

def main():
    # 1. Cargamos la configuración inicial para saber Puerto y Host
    load_dotenv('config/.env', override=True)
    
    # Leemos el puerto y el host, con valores por defecto si no están definidos
    HOST = os.getenv('WEB_HOST', '0.0.0.0')
    PORT = int(os.getenv('WEB_PORT', 8001)) # Puerto cambiado a 8001 para entorno de pruebas

    log.info(f"{Fore.CYAN}Iniciando Sistema WEB (Modo Servidor)...{Style.RESET_ALL}")
    
    # Alerta inicial a Telegram
    send_msg(f"🖥️ <b>SISTEMA ONLINE (Puerto {PORT})</b>\nServidor web listo para recibir órdenes.")
    
    # 2. Instanciamos el bot (se queda en standby)
    bot = GridBot()
    
    log.info(f"Servidor web listo en http://{HOST}:{PORT}")
    log.info("Usa 'pkill -f main.py' o Ctrl+C para detener el sistema.")
    
    try:
        # 3. Arrancamos la web (Esto bloquea el programa hasta que se cierra)
        start_server(bot, host=HOST, port=PORT)
    except (KeyboardInterrupt, SystemExit):
        # Captura tanto Ctrl+C como señales de sistema
        pass
    finally:
        # 4. Bloque de limpieza final (se ejecuta SIEMPRE al cerrar)
        print()
        log.warning("🛑 Deteniendo sistema...")
        send_msg("🔌 <b>SISTEMA OFF</b>\nApagando servidor...")
        
        # Si el motor del bot estaba corriendo, lo paramos suavemente
        if bot.is_running:
            bot.stop_logic()
            
        print(f"\n{Fore.GREEN}👋 ¡Sistema cerrado correctamente!{Style.RESET_ALL}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
