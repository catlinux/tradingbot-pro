# Archivo: gridbot_binance/utils/logger.py
import logging
import json5
import os
import sys
from datetime import datetime
from colorama import init, Fore, Back, Style

# Inicializar colores (autoreset limpia el color tras cada print)
init(autoreset=True)

class BotLogger:
    def __init__(self, level='INFO'):
        self.level = level.upper()
        # Desactivamos logs de librerías ruidosas
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("ccxt").setLevel(logging.WARNING)

    def _timestamp(self):
        return datetime.now().strftime('%H:%M:%S')

    def info(self, message):
        # Mensaje general (Blanco/Gris)
        print(f"{Fore.LIGHTBLACK_EX}[{self._timestamp()}] {Fore.WHITE}ℹ️  {message}")

    def warning(self, message):
        # Alerta (Amarillo)
        print(f"{Fore.LIGHTBLACK_EX}[{self._timestamp()}] {Fore.YELLOW}⚠️  {message}")

    def error(self, message):
        # Error (Rojo brillante)
        print(f"{Fore.LIGHTBLACK_EX}[{self._timestamp()}] {Fore.RED}{Style.BRIGHT}❌ ERROR: {message}")

    def success(self, message):
        # Éxito (Verde)
        print(f"{Fore.LIGHTBLACK_EX}[{self._timestamp()}] {Fore.GREEN}✅ {message}")

    def trade(self, symbol, side, price, amount):
        # Operación (Formato especial muy visible)
        ts = self._timestamp()
        if side.lower() == 'buy':
            # Fondo Verde letra Blanca
            print(f"\n{Back.GREEN}{Fore.WHITE} ⚡ COMPRA {symbol} {Style.RESET_ALL} {Fore.GREEN}@{price} | Cant: {amount} | Hora: {ts}")
        else:
            # Fondo Rojo letra Blanca
            print(f"\n{Back.RED}{Fore.WHITE} 💰 VENTA  {symbol} {Style.RESET_ALL} {Fore.RED}@{price} | Cant: {amount} | Hora: {ts}")
        print() # Espacio extra

    def status(self, message):
        # BARRA DE ESTADO (Sobreescribe la línea actual)
        # \r vuelve al principio de la línea, end='' evita el salto de línea
        sys.stdout.write(f"\r{Fore.CYAN}{Style.BRIGHT}🤖 ESTADO: {Fore.RESET}{message} " + " " * 10)
        sys.stdout.flush()

config_path = 'config/config.json5'
level = 'INFO'
try:
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json5.load(f)
            level = config['system'].get('log_level', 'INFO')
except Exception as e:
    print(f"Warning loading logger configuration: {e}")

log = BotLogger(level=level)