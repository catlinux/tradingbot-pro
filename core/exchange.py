# Archivo: gridbot_binance/core/exchange.py
import ccxt
import os
import json5
import time
from utils.logger import log
from core.database import BotDatabase

# Nota: no cargamos variables de exchange desde .env aquí para evitar intentos de conexión automáticos.
# Las credenciales deben gestionarse exclusivamente desde la base de datos y el Dashboard.

class BinanceConnector:
    def __init__(self):
        self.exchange = None
        self.config_path = 'config/config.json5'
        self.last_config_mtime = 0 
        self.config = self._load_config()
        self._connect()
        # Cargamos mercados de forma lazy (cuando se necesiten, no en __init__)
        self._markets_loaded = False
        # Programar carga de mercados en background (no bloquea el startup)
        import threading
        threading.Thread(target=self._load_markets_background, daemon=True).start()

    def _load_config(self):
        try:
            mtime = os.path.getmtime(self.config_path)
            self.last_config_mtime = mtime
            with open(self.config_path, 'r') as f:
                return json5.load(f)
        except Exception as e:
            log.error(f"Error leyendo config.json5: {e}")
            if hasattr(self, 'config'):
                return self.config
            return {}

    def check_and_reload_config(self):
        try:
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self.last_config_mtime:
                log.warning("Detectado cambio en config.json5...")
                new_config = self._load_config()
                if new_config:
                    old_testnet = self.config.get('system', {}).get('use_testnet', True)
                    new_testnet = new_config.get('system', {}).get('use_testnet', True)

                    self.config = new_config
                    # Solo reconectar si hay cambios significativos de red y tenemos exchange activo
                    if (old_testnet != new_testnet) and self.exchange:
                         log.warning(f"🔄 RECONFIGURACIÓN DE RED: {'TESTNET' if new_testnet else 'REAL'}. Conectando...")
                         self._connect()
                         try:
                             if self.exchange:
                                 self.exchange.load_markets()
                         except Exception as e:
                             log.debug(f"load_markets failed during config reload: {e}")

                    return True
        except Exception as e:
            log.error(f"Error verificando config: {e}")
        return False

    def _connect(self):
        """Intenta conectar usando credenciales de la base de datos (prioridad)"""
        try:
            db = BotDatabase()
            exchanges = db.get_exchanges()
            
            # Buscar el primer exchange marcado como activo
            active_exchange = next((e for e in exchanges if e.get('is_active')), None)
            
            if active_exchange:
                name = active_exchange['name']
                use_testnet = active_exchange['use_testnet']
                log.info(f"📡 Cargando credenciales para exchange activo: {name} (Testnet: {use_testnet})")
                
                creds = db.get_exchange_credentials(name)
                if creds and creds.get('success'):
                    api_key = creds.get('api_key')
                    secret_key = creds.get('secret_key')
                    passphrase = creds.get('passphrase')
                    
                    if api_key and secret_key:
                        self.connect_with_credentials(
                            api_key=api_key,
                            secret_key=secret_key,
                            passphrase=passphrase,
                            use_testnet=use_testnet,
                            exchange_type=active_exchange.get('type', 'binance')
                        )
                        return
                    else:
                        log.error(f"❌ Credenciales vacías para exchange {name}.")
                else:
                    log.error(f"❌ Error recuperando credenciales para exchange {name}.")
            else:
                log.warning("⚠️ No hay ningún exchange activo configurado en la base de datos.")
                
            # Si llegamos aquí, no nos hemos conectado
            self.exchange = None
            log.info("ℹ️ El bot inicia en modo DESCONECTADO. Configura un exchange en el Dashboard.")
            
        except Exception as e:
            log.error(f"❌ Error crítico en _connect: {e}")
            self.exchange = None

    def _load_markets_background(self):
        """Carga los mercados en un thread separado sin bloquear el startup"""
        try:
            if self.exchange:
                log.info("📊 Cargando mercados en background...")
                self.exchange.load_markets()
                self._markets_loaded = True
                log.success("✅ Mercados cargados correctamente.")
        except Exception as e:
            log.error(f"⚠️  Error cargando mercados en background: {e}")
            self._markets_loaded = False

    def validate_connection(self):
        if not self.exchange:
            return False
        try:
            self.exchange.fetch_time()
            return True
        except Exception as e:
            log.debug(f"validate_connection failed: {e}")
            return False

    def connect_with_credentials(self, api_key: str, secret_key: str, passphrase: str = None, use_testnet: bool = None, exchange_type: str = 'binance'):
        """Conecta el conector usando credenciales proporcionadas (no lee .env).
        Soporta 'binance' y 'bitget' (básico) actualmente."""
        try:
            if use_testnet is None:
                use_testnet = self.config.get('system', {}).get('use_testnet', True)

            if not api_key or not secret_key:
                log.error("❌ Faltan claves para conectar con credenciales proporcionadas.")
                self.exchange = None
                return False, "Faltan claves"

            # Construir objeto de exchange según tipo
            if exchange_type == 'bitget':
                opts = {'apiKey': api_key, 'secret': secret_key, 'password': passphrase or '', 'enableRateLimit': True, 'timeout': 30000}
                self.exchange = ccxt.bitget(opts)
            else:  # por defecto, Binance
                self.exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': secret_key,
                    'enableRateLimit': True,
                    'timeout': 30000,
                    'options': {
                        'defaultType': 'spot',
                        'adjustForTimeDifference': True,
                        'recvWindow': 60000
                    }
                })

            if use_testnet and exchange_type == 'binance':
                try:
                    self.exchange.set_sandbox_mode(True)
                except Exception:
                    pass
                
                # ACTUALIZACIÓN SEGURA DE URLS PARA NO BORRAR OTROS ENDPOINTS
                try:
                    # Aseguramos que existe el dict 'api'
                    if 'api' not in self.exchange.urls:
                         self.exchange.urls['api'] = {}
                    
                    # Actualizamos URLs de Spot (API v3)
                    self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api/v3'
                    self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api/v3'
                    
                    # Actualizamos URLs de Futures (FAPI v1) para evitar errores de claves faltantes
                    self.exchange.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com/fapi/v1'
                    self.exchange.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com/fapi/v1'
                except Exception as e:
                    log.warning(f"Error actualizando URLs Testnet: {e}")

            # Verificación no bloqueante con timeout
            try:
                import threading
                _fetch_result = [None]
                def _attempt_fetch_time():
                    try:
                        self.exchange.fetch_time()
                        _fetch_result[0] = True
                    except Exception as e:
                        _fetch_result[0] = e
                _t = threading.Thread(target=_attempt_fetch_time, daemon=True)
                _t.start()
                _t.join(timeout=3)
                if _t.is_alive():
                    log.warning("⚠️ Verificación de tiempo del exchange lenta (timeout 3s). Continuando sin bloquear.")
                elif isinstance(_fetch_result[0], Exception):
                    log.warning(f"⚠️ Conexión establecida pero verificación falló: {_fetch_result[0]}")
                else:
                    log.success("✅ Conexión EXITOSA con exchange vía credenciales." )
            except Exception as v_e:
                log.warning(f"⚠️ Error durante verificación de conexión: {v_e}")

            # Lanzar carga de mercados en background
            try:
                import threading
                threading.Thread(target=self._load_markets_background, daemon=True).start()
            except Exception:
                pass

            return True, "Conectado"

        except Exception as e:
            log.error(f"❌ Error conectando con credenciales: {e}")
            self.exchange = None
            return False, str(e)

    # --- GESTOR DE ERRORES CENTRALIZADO ---
    def _handle_api_error(self, e, context=""):
        err_str = str(e).lower()
        if "418" in err_str or "too much request weight" in err_str or "-1003" in err_str:
            log.error("🚨 IP BANEADA TEMPORALMENTE POR BINANCE (418).")
            log.warning("⏳ Pausando el bot durante 2 minutos para enfriar la conexión...")
            time.sleep(120) # Espera 2 minutos
            log.success("🔄 Reanudando operaciones...")
        elif "content-length" in err_str or "json" in err_str:
            # Ignoramos errores puntuales de red
            pass
        else:
            log.error(f"Error API ({context}): {e}")
    # --------------------------------------------

    # --- FUNCIÓ MODIFICADA: ESTAT DEL COMPTE (SOLUCIÓ 0%) ---
    def get_account_status(self):
        """Retorna nivell VIP i comissions reals buscant en diversos parells"""
        if not self.exchange:
            return {'tier': 'N/A', 'maker': 0, 'taker': 0}
        
        info = {'tier': 'VIP 0', 'maker': 0.0, 'taker': 0.0}
        
        try:
            # 1. Intentem obtenir comissions provant diversos parells comuns
            # Molts parells tenen 0% per promoció, així que busquem el primer que tingui fee > 0
            test_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'BTC/USDC']

            
            for pair in test_pairs:
                try:
                    fees = self.exchange.fetch_trading_fee(pair)
                    if fees:
                        maker = fees.get('maker', 0.0)
                        taker = fees.get('taker', 0.0)
                        
                        # Si trobem una comissió > 0, assumim que és la tarifa real del compte
                        if maker > 0 or taker > 0:
                            info['maker'] = maker * 100
                        info['taker'] = taker * 100
                        break
                        
                        # Si és 0, guardem el valor provisional però seguim buscant
                        info['maker'] = maker * 100
                        info['taker'] = taker * 100
                except Exception as e:
                    log.debug(f"fetch_trading_fee failed for {pair}: {e}")
                    continue
            
            # 2. Obtenim nivell VIP
            if hasattr(self.exchange, 'sapi_get_account_status'):
                res = self.exchange.sapi_get_account_status()
                # La resposta sol ser {'data': 'Normal'} o {'data': '1'}
                level = res.get('data', 'Normal')
                if level == 'Normal':
                    info['tier'] = 'VIP 0'
                else:
                    info['tier'] = f"VIP {level}"
            
            if getattr(self.exchange, 'sandbox', False):
                info['tier'] = 'Testnet'

        except Exception as e:
            log.error(f"Error obtenint estat del compte: {e}")
        
        return info
    # -------------------------------------------------------

    def get_asset_balance(self, asset):
        if not self.exchange:
            return 0.0
        try:
            balance = self.exchange.fetch_balance()
            return float(balance.get(asset, {}).get('free', 0.0))
        except Exception as e:
            self._handle_api_error(e, f"balance {asset}")
            return 0.0

    def get_total_balance(self, asset):
        if not self.exchange:
            return 0.0
        try:
            balance = self.exchange.fetch_balance()
            if asset in balance:
                free = float(balance[asset].get('free', 0.0))
                used = float(balance[asset].get('used', 0.0))
                return free + used
            return 0.0
        except Exception as e:
            self._handle_api_error(e, f"total balance {asset}")
            return 0.0

    # --- NUEVA FUNCIÓN OPTIMIZADA: DESCARGA EN GRUPO (BATCH) ---
    def fetch_batch_prices(self, symbols_list):
        """Pide precios de múltiples monedas en UNA sola petición API"""
        if not self.exchange or not symbols_list:
            return {}
        try:
            # fetch_tickers (plural) obtiene datos de múltiples pares a la vez
            tickers = self.exchange.fetch_tickers(symbols_list)
            prices = {}
            for sym, data in tickers.items():
                if 'last' in data and data['last']:
                    prices[sym] = float(data['last'])
            return prices
        except Exception as e:
            self._handle_api_error(e, "fetch_batch_prices")
            return {}
    # -----------------------------------------------------------

    def fetch_current_price(self, symbol):
        # Mantenemos esta por compatibilidad, pero recomendamos usar batch
        if not self.exchange:
            return 0.0
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            self._handle_api_error(e, f"price {symbol}")
            return 0.0

    def place_order(self, symbol, side, amount, price):
        if not self.exchange:
            return None
        params = {}
        try:
            order = self.exchange.create_order(symbol, 'limit', side, amount, price, params)
            log.trade(symbol, side, price, amount)
            return order
        except ccxt.InsufficientFunds as e:
            log.error(f"FONDOS INSUFICIENTES: {e}")
            return None
        except Exception as e:
            self._handle_api_error(e, "place order")
            return None

    def place_market_sell(self, symbol, amount):
        if not self.exchange:
            return None
        try:
            log.warning(f"Ejecutando Venta a Mercado {symbol} Cantidad: {amount}")
            return self.exchange.create_order(symbol, 'market', 'sell', amount)
        except Exception as e:
            self._handle_api_error(e, "market sell")
            return None

    def place_market_buy(self, symbol, amount_usdc):
        """Compra a mercado especificando cuántos USDC queremos gastar"""
        if not self.exchange:
            return None
        try:
            log.warning(f"Ejecutando COMPRA INICIAL a Mercado {symbol} Valor: {amount_usdc} USDC")

            price = self.fetch_current_price(symbol)
            if price == 0:
                return None

            amount_base = amount_usdc / price
            # Aplicamos precisión del exchange
            amount_base = self.exchange.amount_to_precision(symbol, amount_base)

            return self.exchange.create_order(symbol, 'market', 'buy', amount_base)
        except Exception as e:
            self._handle_api_error(e, "market buy")
            return None

    def cancel_order(self, order_id, symbol):
        if not self.exchange:
            return None
        try:
            return self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            self._handle_api_error(e, f"cancel {order_id}")
            return None

    def cancel_all_orders(self, symbol):
        if not self.exchange:
            return None
        try:
            return self.exchange.cancel_all_orders(symbol)
        except ccxt.OrderNotFound:
            return None
        except Exception as e:
            # Ignoramos error específico de Binance cuando no hay órdenes (-2011)
            if "-2011" in str(e):
                return None
            self._handle_api_error(e, f"cancel all {symbol}")
            return None
            
    def fetch_open_orders(self, symbol):
        if not self.exchange:
            return []
        try:
            return self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            self._handle_api_error(e, f"open orders {symbol}")
            return []

    # Cambio solicitado: Límite por defecto a 500
    def fetch_candles(self, symbol, timeframe='15m', limit=500):
        if not self.exchange:
            return []
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            self._handle_api_error(e, f"candles {symbol}")
            return []

    def fetch_my_trades(self, symbol, limit=20):
        if not self.exchange:
            return []
        try:
            return self.exchange.fetch_my_trades(symbol, limit=limit)
        except Exception as e:
            self._handle_api_error(e, f"trades {symbol}")
            return []