# Archivo: gridbot_binance/core/database.py
import sqlite3
import json
import time
import os
from utils.logger import log
from cryptography.fernet import Fernet
import base64
import hashlib

DB_FOLDER = "data"
DB_NAME = "bot_data.db"
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)

# Gestión segura de la clave de encriptación:
# 1) Si existe la variable de entorno GRIDBOT_MASTER_KEY, se usa (se deriva a clave Fernet si no es una clave Fernet válida)
# 2) Si existe el fichero de clave en data/.encryption_key se lee y se usa
# 3) Si no existe, se genera una nueva clave Fernet y se persiste en data/.encryption_key con permisos restringidos

def _load_or_generate_encryption_key():
    # 1) variable de entorno
    env_key = os.getenv('GRIDBOT_MASTER_KEY')
    if env_key:
        # Si parece una clave Fernet (44 bytes base64), usarla tal cual
        try:
            if isinstance(env_key, str) and len(env_key) == 44:
                return env_key.encode()
        except Exception:
            pass
        # Si no, derivar una clave Fernet estable a partir del valor proporcionado
        hash_bytes = hashlib.sha256(env_key.encode()).digest()
        return base64.urlsafe_b64encode(hash_bytes)

    # 2) fichero en data/
    key_path = os.path.join(DB_FOLDER, '.encryption_key')
    try:
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                return f.read().strip()
    except Exception:
        pass

    # 3) generar nueva y persistir
    try:
        new_key = Fernet.generate_key()
        os.makedirs(DB_FOLDER, exist_ok=True)
        with open(key_path, 'wb') as f:
            f.write(new_key)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return new_key
    except Exception:
        # Fallback: derivar de valor fijo (sólo si todo lo demás falla)
        secret = "gridbot-pro-2024-secret"
        hash_bytes = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(hash_bytes)

ENCRYPTION_KEY = _load_or_generate_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

class BotDatabase:
    def __init__(self):
        if not os.path.exists(DB_FOLDER):
            os.makedirs(DB_FOLDER)
        self._init_db()

    @staticmethod
    def _encrypt_data(data):
        """Encripta una cadena de texto"""
        if not data:
            return None
        return cipher_suite.encrypt(data.encode()).decode()
    
    @staticmethod
    def _decrypt_data(encrypted_data):
        """Desencripta una cadena de texto. Si falla, devuelve None (no expone datos encriptados)."""
        if not encrypted_data:
            return None
        try:
            return cipher_suite.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            log.error(f"Error desencriptando datos: {e}")
            return None

    def _get_conn(self):
        """Abre una conexión nueva segura para el hilo actual"""
        return sqlite3.connect(DB_PATH, timeout=30) 

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass

            cursor.execute('''CREATE TABLE IF NOT EXISTS market_data (symbol TEXT PRIMARY KEY, price REAL, candles_json TEXT, updated_at REAL)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS grid_status (symbol TEXT PRIMARY KEY, open_orders_json TEXT, grid_levels_json TEXT, updated_at REAL)''')
            
            try:
                cursor.execute("ALTER TABLE grid_status ADD COLUMN setup_done BOOLEAN DEFAULT 0")
            except Exception:
                pass 

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    price REAL,
                    amount REAL,
                    cost REAL,
                    fee_cost REAL,
                    fee_currency TEXT,
                    timestamp REAL,
                    buy_id INTEGER
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS balance_history (
                    timestamp REAL PRIMARY KEY,
                    equity REAL
                )
            ''')
            # Añadimos columna exchange si no existe (para soportar múltiples exchanges)
            try:
                cursor.execute("ALTER TABLE balance_history ADD COLUMN exchange TEXT DEFAULT 'default'")
            except Exception:
                # Si ya existe la columna, ignoramos el error
                pass
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS bot_info (key TEXT PRIMARY KEY, value TEXT)''')
            
            # --- SISTEMA PNL PER SESSIONS (Robust) ---
            
            # 1. HISTÒRIC: Resultats consolidats de sessions anteriors
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pnl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    pnl_value REAL,
                    timestamp REAL
                )
            ''')

            # 2. BACKUP: Estat actual de la sessió viva (per si hi ha crash)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pnl_backup (
                    symbol TEXT PRIMARY KEY,
                    pnl_value REAL,
                    updated_at REAL
                )
            ''')
            # -----------------------------------------------------

            # --- EXCHANGES MANAGEMENT ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    api_key TEXT,
                    secret_key TEXT,
                    passphrase TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    use_testnet BOOLEAN DEFAULT 0,
                    created_at REAL,
                    updated_at REAL
                )
            ''')
            # Añadir columna use_testnet a exchanges si no existe (migración)
            try:
                cursor.execute("ALTER TABLE exchanges ADD COLUMN use_testnet BOOLEAN DEFAULT 0")
            except Exception:
                pass
            # --------------------------------

            cursor.execute("SELECT value FROM bot_info WHERE key='next_buy_id'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO bot_info (key, value) VALUES (?, ?)", ('next_buy_id', '1'))
                
            cursor.execute("SELECT value FROM bot_info WHERE key='first_run'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO bot_info (key, value) VALUES (?, ?)", ('first_run', str(time.time())))
            
            conn.commit()

    # --- GESTIÓ DE PNL SESSIONS ---

    def update_pnl_backup(self, symbol, current_pnl):
        """Guarda el PnL de la sessió actual a la taula de seguretat (Backup)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pnl_backup (symbol, pnl_value, updated_at) VALUES (?, ?, ?)", 
                           (symbol, current_pnl, time.time()))
            conn.commit()

    def archive_session_stats(self):
        """
        Es crida AL INICI d'una nova sessió.
        Agafa el backup de la sessió anterior (si existeix) i el guarda a l'històric permanent.
        Després neteja el backup per començar de 0.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 1. Llegim el backup de l'última sessió (si n'hi ha)
            cursor.execute("SELECT symbol, pnl_value FROM pnl_backup")
            rows = cursor.fetchall()
            
            if rows:
                log.info(f"💾 Arxivant sessió anterior ({len(rows)} monedes) a l'històric...")
                current_time = time.time()
                for sym, pnl in rows:
                    if pnl != 0: # Només guardem si hi ha hagut moviment real
                        cursor.execute("INSERT INTO pnl_history (symbol, pnl_value, timestamp) VALUES (?, ?, ?)", 
                                       (sym, pnl, current_time))
                
                # 2. Netegem el backup per començar la nova sessió neta
                cursor.execute("DELETE FROM pnl_backup")
                conn.commit()
                return True
            return False

    def get_accumulated_pnl(self, symbol):
        """Retorna la suma de TOTES les sessions anteriors (Històric)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(pnl_value) FROM pnl_history WHERE symbol=?", (symbol,))
            row = cursor.fetchone()
            # Si és None (no hi ha historial), retorna 0.0
            return row[0] if row and row[0] is not None else 0.0

    def reset_global_pnl_history(self):
        """Esborra tot l'històric i el backup. Reset Global total."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pnl_history")
            cursor.execute("DELETE FROM pnl_backup")
            conn.commit()
            
    def reset_global_pnl_for_symbol(self, symbol):
        """Esborra historial només d'una moneda"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pnl_history WHERE symbol=?", (symbol,))
            cursor.execute("DELETE FROM pnl_backup WHERE symbol=?", (symbol,))
            conn.commit()

    # -------------------------------------------------------
    # RESTA DE FUNCIONS (Sense canvis, només manteniment)

    def get_next_buy_id(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='next_buy_id'")
            row = cursor.fetchone()
            current_id = int(row[0]) if row else 1
            assigned_id = current_id
            next_id = current_id + 1
            if next_id > 1000:
                next_id = 1
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('next_buy_id', str(next_id)))
            conn.commit()
            return assigned_id

    def set_trade_buy_id(self, trade_id, buy_id):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE trade_history SET buy_id = ? WHERE id = ?", (buy_id, trade_id))
            conn.commit()

    def get_last_buy_price(self, symbol):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT price FROM trade_history WHERE symbol=? AND side='buy' ORDER BY timestamp DESC LIMIT 1", (symbol,))
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0

    def find_linked_buy_id(self, symbol, sell_price, spread_pct):
        target_buy_price = sell_price / (1 + (spread_pct / 100))
        min_p = target_buy_price * 0.99
        max_p = target_buy_price * 1.01
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT buy_id FROM trade_history 
                WHERE symbol=? AND side='buy' AND price >= ? AND price <= ? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (symbol, min_p, max_p))
            row = cursor.fetchone()
            return row[0] if row else None

    def log_balance_snapshot(self, equity, exchange='default'):
        """Guarda instantánea del balance con referencia al exchange (p.ej. 'binance').
        Evita insertar duplicados cercanos en el tiempo o con variación insignificante para reducir ruido y duplicados.
        Devuelve True si se insertó una fila nueva, False si se omitió por deduplicación.
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                current_ts = time.time()

                # Recuperar última snapshot para este exchange
                cursor.execute("SELECT timestamp, equity FROM balance_history WHERE exchange = ? ORDER BY timestamp DESC LIMIT 1", (exchange,))
                last = cursor.fetchone()

                # Parámetros de deduplicación
                MIN_INTERVAL = 50  # segundos mínimos entre snapshots para considerar insertar
                MIN_DELTA = 0.01   # diferencia mínima en equity para considerar distinto

                if last:
                    try:
                        last_ts = float(last[0])
                        last_eq = float(last[1])
                        if (current_ts - last_ts) < MIN_INTERVAL and abs(float(equity) - last_eq) <= MIN_DELTA:
                            # Omitir inserción si es demasiado cercano en el tiempo y sin cambios relevantes
                            return False
                    except Exception:
                        # Si falla el parsing, seguimos y permitimos la inserción
                        pass

                # Insertar snapshot
                cursor.execute("INSERT INTO balance_history (timestamp, equity, exchange) VALUES (?, ?, ?)", (current_ts, equity, exchange))
                conn.commit()
                return True
        except Exception as e:
            log.error(f"Error guardando snapshot en DB: {e}")
            return False

    def get_balance_history(self, from_timestamp=0, exchange=None):
        """Si `exchange` es None devuelve datos de todos los exchanges; si se especifica, filtra por `exchange`."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if exchange:
                cursor.execute("SELECT timestamp, equity FROM balance_history WHERE timestamp >= ? AND exchange = ? ORDER BY timestamp ASC", (from_timestamp, exchange))
            else:
                cursor.execute("SELECT timestamp, equity FROM balance_history WHERE timestamp >= ? ORDER BY timestamp ASC", (from_timestamp,))
            rows = cursor.fetchall()
            return rows

    def get_last_balance_snapshot(self, exchange: str):
        """Devuelve la última snapshot (timestamp, equity) para un `exchange`, o `None` si no existe."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp, equity FROM balance_history WHERE exchange = ? ORDER BY timestamp DESC LIMIT 1", (exchange,))
                row = cursor.fetchone()
                if row:
                    return row  # (timestamp, equity)
                return None
        except Exception as e:
            log.error(f"Error obteniendo última snapshot para {exchange}: {e}")
            return None

    def set_session_start_balance(self, value):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('session_start_balance', str(value)))
            conn.commit()

    def get_session_start_balance(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='session_start_balance'")
            row = cursor.fetchone()
            if row:
                return float(row[0])
            return 0.0

    def set_global_start_balance_if_not_exists(self, value):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='global_start_balance'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO bot_info (key, value) VALUES (?, ?)", ('global_start_balance', str(value)))
            conn.commit()

    def get_global_start_balance(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='global_start_balance'")
            row = cursor.fetchone()
            if row:
                return float(row[0])
            return 0.0

    def set_coin_initial_balance(self, symbol, value_usdc):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='coins_initial_equity'")
            row = cursor.fetchone()
            data = {}
            if row:
                try:
                    data = json.loads(row[0])
                except Exception:
                    pass
            data[symbol] = value_usdc
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('coins_initial_equity', json.dumps(data)))
            conn.commit()

    # --- EXCHANGES MANAGEMENT ---
    
    def save_exchange(self, name: str, api_key: str, secret_key: str, passphrase: str = None, use_testnet: bool = False) -> dict:
        """Guarda o actualiza credenciales de un exchange (ENCRIPTADAS)"""
        try:
            # Trim y encriptar los datos sensibles
            api_key = api_key.strip() if isinstance(api_key, str) else api_key
            secret_key = secret_key.strip() if isinstance(secret_key, str) else secret_key
            passphrase = passphrase.strip() if isinstance(passphrase, str) else passphrase

            encrypted_api_key = self._encrypt_data(api_key)
            encrypted_secret_key = self._encrypt_data(secret_key)
            encrypted_passphrase = self._encrypt_data(passphrase) if passphrase else None
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                now = time.time()
                
                # Verificar si existe
                cursor.execute("SELECT id FROM exchanges WHERE name = ?", (name,))
                exists = cursor.fetchone()
                
                if exists:
                    # Actualizar
                    cursor.execute('''UPDATE exchanges SET api_key = ?, secret_key = ?, passphrase = ?, use_testnet = ?, updated_at = ? 
                                     WHERE name = ?''',
                                 (encrypted_api_key, encrypted_secret_key, encrypted_passphrase, int(bool(use_testnet)), now, name))
                else:
                    # Insertar
                    cursor.execute('''INSERT INTO exchanges (name, api_key, secret_key, passphrase, is_active, use_testnet, created_at, updated_at)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                 (name, encrypted_api_key, encrypted_secret_key, encrypted_passphrase, 1, int(bool(use_testnet)), now, now))
                
                conn.commit()
                return {"success": True, "message": f"Exchange '{name}' guardado correctamente"}
        except Exception as e:
            log.error(f"Error guardando exchange: {e}")
            return {"success": False, "message": str(e)}
    
    def get_exchanges(self) -> list:
        """Obtiene todos los exchanges configurados"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name, api_key, secret_key, passphrase, is_active, use_testnet FROM exchanges ORDER BY created_at")
                rows = cursor.fetchall()
                
                exchanges = []
                for row in rows:
                    exchanges.append({
                        "name": row[0],
                        "has_credentials": bool(row[1] and row[2]),
                        "is_active": bool(row[4]),
                        "use_testnet": bool(row[5]),
                        "type": "bitget" if row[0].lower() == "bitget" else "binance"
                    })
                return exchanges
        except Exception as e:
            log.error(f"Error obteniendo exchanges: {e}")
            return []
    
    def get_exchange_credentials(self, name: str) -> dict:
        """Obtiene credenciales de un exchange específico (DESENCRIPTADAS)"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT api_key, secret_key, passphrase, use_testnet FROM exchanges WHERE name = ?", (name,))
                row = cursor.fetchone()
                
                if row:
                    # Desencriptar los datos
                    api_key = self._decrypt_data(row[0]) if row[0] else None
                    secret_key = self._decrypt_data(row[1]) if row[1] else None
                    passphrase = self._decrypt_data(row[2]) if row[2] else None
                    use_testnet = bool(row[3])

                    # Si la desencriptación falla, devolver un error claro para que el cliente lo gestione
                    if api_key is None or secret_key is None:
                        log.error(f"No se pudieron desencriptar las credenciales para exchange {name}")
                        return {"success": False, "message": "No se pudieron desencriptar las credenciales. Comprueba la clave de encriptación"}

                    return {
                        "success": True,
                        "api_key": api_key,
                        "secret_key": secret_key,
                        "passphrase": passphrase or "",
                        "use_testnet": use_testnet
                    }
                return {"success": False, "message": "Exchange no encontrado"}
        except Exception as e:
            log.error(f"Error obteniendo credenciales: {e}")
            return {"success": False, "message": str(e)}
    
    def delete_exchange(self, name: str) -> dict:
        """Elimina un exchange"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM exchanges WHERE name = ?", (name,))
                conn.commit()
                return {"success": True, "message": f"Exchange '{name}' eliminado"}
        except Exception as e:
            log.error(f"Error eliminando exchange: {e}")
            return {"success": False, "message": str(e)}

    def get_coin_initial_balance(self, symbol):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='coins_initial_equity'")
            row = cursor.fetchone()
            if row:
                try:
                    data = json.loads(row[0])
                    return float(data.get(symbol, 0.0))
                except Exception:
                    pass
            return 0.0

    def reset_coin_initial_balances(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_info WHERE key='coins_initial_equity'")
            conn.commit()

    def update_market_snapshot(self, symbol, price, candles):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT OR REPLACE INTO market_data (symbol, price, candles_json, updated_at) VALUES (?, ?, ?, ?)''', (symbol, price, json.dumps(candles), time.time()))
            conn.commit()

    def update_grid_status(self, symbol, orders, levels):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT setup_done FROM grid_status WHERE symbol=?", (symbol,))
            row = cursor.fetchone()
            setup_val = row[0] if row else 0
            cursor.execute('''INSERT OR REPLACE INTO grid_status (symbol, open_orders_json, grid_levels_json, updated_at, setup_done) VALUES (?, ?, ?, ?, ?)''', (symbol, json.dumps(orders), json.dumps(levels), time.time(), setup_val))
            conn.commit()

    def set_symbol_setup_done(self, symbol, status=True):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            val = 1 if status else 0
            cursor.execute("UPDATE grid_status SET setup_done=? WHERE symbol=?", (val, symbol))
            if cursor.rowcount == 0:
                 cursor.execute("INSERT INTO grid_status (symbol, setup_done, updated_at) VALUES (?, ?, ?)", (symbol, val, time.time()))
            conn.commit()

    def get_symbol_setup_done(self, symbol):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT setup_done FROM grid_status WHERE symbol=?", (symbol,))
            row = cursor.fetchone()
            if row:
                return bool(row[0])
            return False

    def save_trades(self, trades):
        if not trades:
            return
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for t in trades:
                try:
                    fee_cost = 0.0
                    fee_currency = ''
                    if 'fee' in t and t['fee']:
                        fee_cost = float(t['fee'].get('cost', 0.0))
                        fee_currency = t['fee'].get('currency', '')

                    symbol_parts = t['symbol'].split('/')
                    quote_currency = symbol_parts[1] if len(symbol_parts) > 1 else 'USDC'
                    fee_in_quote = 0.0
                    
                    if fee_cost > 0:
                        if fee_currency == quote_currency:
                            fee_in_quote = fee_cost
                        else:
                            fee_in_quote = fee_cost * t['price']

                    cursor.execute('''
                        INSERT OR IGNORE INTO trade_history (id, symbol, side, price, amount, cost, fee_cost, fee_currency, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (t['id'], t['symbol'], t['side'], t['price'], t['amount'], t['cost'], fee_in_quote, 'USDC_EQ', t['timestamp']))
                except Exception as e: 
                    log.error(f"Error guardando trade DB: {e}")
                    pass
            conn.commit()

    def log_trade(self, trade):
        """Convenience wrapper para tests: guarda un único trade usando save_trades"""
        import uuid
        if 'id' not in trade:
            trade['id'] = str(uuid.uuid4())
        if 'cost' not in trade and 'price' in trade and 'amount' in trade:
            try:
                trade['cost'] = float(trade['price']) * float(trade['amount'])
            except Exception:
                trade['cost'] = 0.0
        # Fees and timestamps defaulting
        if 'fee' not in trade:
            trade['fee'] = None
        if 'timestamp' not in trade:
            trade['timestamp'] = time.time()
        self.save_trades([trade])
    def get_pair_data(self, symbol):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM market_data WHERE symbol=?", (symbol,))
            market_row = cursor.fetchone()
            market = {}
            if market_row:
                cols = [d[0] for d in cursor.description]
                market = dict(zip(cols, market_row))

            cursor.execute("SELECT * FROM grid_status WHERE symbol=?", (symbol,))
            grid_row = cursor.fetchone()
            grid = {}
            if grid_row:
                cols = [d[0] for d in cursor.description]
                grid = dict(zip(cols, grid_row))

            cursor.execute("SELECT * FROM trade_history WHERE symbol=? ORDER BY timestamp DESC LIMIT 50", (symbol,))
            trades_rows = cursor.fetchall()
            trades = []
            if trades_rows:
                cols = [d[0] for d in cursor.description]
                for row in trades_rows:
                    t_dict = dict(zip(cols, row))
                    if 'buy_id' not in t_dict:
                        t_dict['buy_id'] = None
                    trades.append(t_dict)
            
            return {
                "price": market.get('price', 0.0),
                "candles": json.loads(market.get('candles_json', '[]')) if market.get('candles_json') else [],
                "open_orders": json.loads(grid.get('open_orders_json', '[]')) if grid.get('open_orders_json') else [],
                "grid_levels": json.loads(grid.get('grid_levels_json', '[]')) if grid.get('grid_levels_json') else [],
                "trades": trades
            }

    def get_all_prices(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, price FROM market_data")
            rows = cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    def get_first_run_timestamp(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='first_run'")
            row = cursor.fetchone()
            if row:
                return float(row[0])
            return time.time()

    def get_stats(self, from_timestamp=0):
        # Aquesta funció segueix sent l'encarregada de calcular la SESSIÓ ACTUAL
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, side, cost, fee_cost, amount, timestamp FROM trade_history WHERE timestamp >= ?", (int(from_timestamp * 1000),))
            rows = cursor.fetchall()

            total_trades = len(rows)
            cash_flow_per_coin = {} 
            qty_delta_per_coin = {} 
            trades_per_coin = {} 

            cursor.execute("SELECT key, value FROM bot_info WHERE key LIKE 'session_start_%'")
            session_rows = cursor.fetchall()
            coin_sessions = {}
            for k, v in session_rows:
                sym = k.replace('session_start_', '')
                try:
                    coin_sessions[sym] = float(v)
                except Exception:
                    pass

            for symbol, side, cost, fee, amount, ts in rows:
                session_start_coin = coin_sessions.get(symbol, 0.0)
                if from_timestamp > 0 and session_start_coin > 0 and ts < (session_start_coin * 1000):
                    continue
                
                val = cost if side == 'sell' else -cost
                net_val = val - (fee if fee else 0.0)
                
                if symbol not in cash_flow_per_coin:
                    cash_flow_per_coin[symbol] = 0.0
                cash_flow_per_coin[symbol] += net_val

                if symbol not in qty_delta_per_coin:
                    qty_delta_per_coin[symbol] = 0.0
                if side == 'buy':
                    qty_delta_per_coin[symbol] += amount
                else:
                    qty_delta_per_coin[symbol] -= amount

                if symbol not in trades_per_coin:
                    trades_per_coin[symbol] = 0
                trades_per_coin[symbol] += 1

            best_coin = "-"
            highest_cf = -99999999.0
            for sym, val in cash_flow_per_coin.items():
                if val > highest_cf:
                    highest_cf = val
                    best_coin = sym
            if highest_cf == -99999999.0:
                best_coin = "-"

            trades_distribution = [{"name": k, "value": v} for k, v in trades_per_coin.items()]

            return {
                "trades": total_trades,
                "best_coin": best_coin,
                "trades_distribution": trades_distribution,
                "per_coin_stats": {
                    "cash_flow": cash_flow_per_coin,
                    "qty_delta": qty_delta_per_coin,
                    "trades": trades_per_coin
                }
            }

    def get_all_active_orders(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, open_orders_json FROM grid_status")
            rows = cursor.fetchall()
            all_orders = []
            for symbol, orders_json in rows:
                if not orders_json:
                    continue
                try:
                    orders = json.loads(orders_json)
                    for o in orders:
                        o['symbol'] = symbol
                        all_orders.append(o)
                except Exception:
                    pass
            return all_orders

    def prune_old_data(self, days_keep=30):
        cutoff = time.time() - (days_keep * 24 * 3600)
        cutoff_ms = cutoff * 1000
        
        # FIX VACUUM: Execució fora de transacció
        deleted_trades = 0
        deleted_balance = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trade_history WHERE timestamp < ?", (cutoff_ms,))
            deleted_trades = cursor.rowcount
            
            cursor.execute("DELETE FROM balance_history WHERE timestamp < ?", (cutoff,))
            deleted_balance = cursor.rowcount
            conn.commit()
            
        if deleted_trades > 0 or deleted_balance > 0:
            try:
                # isolation_level=None activa el mode autocommit
                vacuum_conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
                vacuum_conn.execute("VACUUM")
                vacuum_conn.close()
            except Exception as e:
                log.warning(f"No s'ha pogut fer VACUUM (no crític): {e}")

        return deleted_trades, deleted_balance

    def assign_id_to_trade_if_missing(self, trade_id):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT buy_id FROM trade_history WHERE id=?", (trade_id,))
            row = cursor.fetchone()
            
            if row and row[0] is not None:
                found_id = row[0]
                return found_id
                
            new_id = self.get_next_buy_id() 
        self.set_trade_buy_id(trade_id, new_id)
        return new_id

    def get_buy_trade_uuid_for_sell_order(self, symbol, sell_price, spread_pct):
        target = sell_price / (1 + (spread_pct / 100))
        min_p = target * 0.995 
        max_p = target * 1.005
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM trade_history 
                WHERE symbol=? AND side='buy' AND price >= ? AND price <= ? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (symbol, min_p, max_p))
            row = cursor.fetchone()
            return row[0] if row else None

    def delete_history_smart(self, symbol, keep_uuids):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if not keep_uuids:
                cursor.execute("DELETE FROM trade_history WHERE symbol=?", (symbol,))
            else:
                placeholders = ','.join(['?'] * len(keep_uuids))
                sql = f"DELETE FROM trade_history WHERE symbol=? AND id NOT IN ({placeholders})"
                params = [symbol] + keep_uuids
                cursor.execute(sql, params)
            count = cursor.rowcount
            
            # També netegem el PnL d'aquesta moneda en particular
            cursor.execute("DELETE FROM pnl_backup WHERE symbol=?", (symbol,))
            cursor.execute("DELETE FROM pnl_history WHERE symbol=?", (symbol,))
            
            conn.commit()
            return count

    def set_session_start_time(self, timestamp):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('session_start_time', str(timestamp)))
            conn.commit()

    def get_session_start_time(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='session_start_time'")
            row = cursor.fetchone()
            if row:
                return float(row[0])
            return 0.0

    def get_all_stored_grids(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, grid_levels_json FROM grid_status")
            rows = cursor.fetchall()
            grids = {}
            for symbol, levels_json in rows:
                try:
                    if levels_json:
                        grids[symbol] = json.loads(levels_json)
                except Exception:
                    pass
            return grids

    def clear_session_data(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_info WHERE key='session_start_time'")
            cursor.execute("DELETE FROM bot_info WHERE key='session_start_balance'")
            cursor.execute("DELETE FROM bot_info WHERE key LIKE 'session_start_%'")
            conn.commit()

    def reset_all_statistics(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trade_history")
            cursor.execute("DELETE FROM balance_history")
            cursor.execute("UPDATE grid_status SET setup_done=0")
            
            # Reset complet de les taules PnL
            cursor.execute("DELETE FROM pnl_history")
            cursor.execute("DELETE FROM pnl_backup")

            now = str(time.time())
            cursor.execute("DELETE FROM bot_info WHERE key IN ('first_run', 'global_start_balance', 'session_start_balance', 'coins_initial_equity', 'next_buy_id')")
            cursor.execute("INSERT INTO bot_info (key, value) VALUES (?, ?)", ('first_run', now))
            cursor.execute("INSERT INTO bot_info (key, value) VALUES (?, ?)", ('next_buy_id', '1'))
            
            cursor.execute("DELETE FROM bot_info WHERE key='session_start_time'")
            cursor.execute("DELETE FROM bot_info WHERE key='session_start_balance'")
            cursor.execute("DELETE FROM bot_info WHERE key LIKE 'session_start_%'")
            
            conn.commit()
        return True

    def clear_balance_history(self, exchange=None):
        """Si `exchange` es None borra todo; si se especifica, borra solo las filas de ese exchange."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if exchange:
                cursor.execute("DELETE FROM balance_history WHERE exchange = ?", (exchange,))
            else:
                cursor.execute("DELETE FROM balance_history")
            conn.commit()

    def clear_all_trades_history(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trade_history")
            # En un clear history total, també esborrem la comptabilitat PnL
            cursor.execute("DELETE FROM pnl_history")
            cursor.execute("DELETE FROM pnl_backup")
            conn.commit()

    def clear_orders_cache(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE grid_status SET open_orders_json = '[]'")
            conn.commit()

    def delete_trades_for_symbol(self, symbol):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trade_history WHERE symbol=?", (symbol,))
            cursor.execute("DELETE FROM pnl_backup WHERE symbol=?", (symbol,))
            cursor.execute("DELETE FROM pnl_history WHERE symbol=?", (symbol,))
            conn.commit()

    def set_coin_session_start(self, symbol, timestamp):
        key = f"session_start_{symbol}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", (key, str(timestamp)))
            conn.commit()

    def get_coin_session_start(self, symbol):
        key = f"session_start_{symbol}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key=?", (key,))
            row = cursor.fetchone()
            if row:
                return float(row[0])
            return 0.0

    def adjust_balance_history(self, delta_usdc):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='global_start_balance'")
            row = cursor.fetchone()
            current_glob = float(row[0]) if row else 0.0
            new_glob = current_glob + delta_usdc
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('global_start_balance', str(new_glob)))
            
            cursor.execute("SELECT value FROM bot_info WHERE key='session_start_balance'")
            row = cursor.fetchone()
            current_sess = float(row[0]) if row else 0.0
            new_sess = current_sess + delta_usdc
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('session_start_balance', str(new_sess)))
            
            conn.commit()

    def adjust_coin_initial_balance(self, symbol, delta_usdc):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_info WHERE key='coins_initial_equity'")
            row = cursor.fetchone()
            data = {}
            if row:
                try:
                    data = json.loads(row[0])
                except Exception:
                    pass

            current_val = float(data.get(symbol, 0.0))
            data[symbol] = current_val + delta_usdc
            
            cursor.execute("INSERT OR REPLACE INTO bot_info (key, value) VALUES (?, ?)", ('coins_initial_equity', json.dumps(data)))
            conn.commit()