# Archivo: gridbot_binance/web/server.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
import os
import time
import json5 
from datetime import datetime
from core.database import BotDatabase 
from utils.telegram import send_msg
from utils.logger import log
from dotenv import load_dotenv 

app = FastAPI()

# Middleware para agregar headers de seguridad incluyendo CSP permisivo
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # CSP mejorado que permite todos los CDNs necesarios
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "object-src 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Timestamp de arranque del servidor web (fallback para uptime de sesión si no hay global_start_time)
SERVER_START_TS = time.time()

static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
    os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

db = BotDatabase()
bot_instance = None 

# Sistema de caché simple para evitar llamadas bloqueantes repetidas
_tickers_cache = {"data": {}, "timestamp": 0}
_balance_cache = {"data": {}, "timestamp": 0}
_cache_ttl = 10  # Validez de caché: 10 segundos

def _get_cached_tickers():
    """Obtiene tickers con caché de 10 segundos"""
    global _tickers_cache
    current_time = time.time()
    
    # Si el caché es válido, devolverlo
    if current_time - _tickers_cache["timestamp"] < _cache_ttl and _tickers_cache["data"]:
        return _tickers_cache["data"]
    
    # Intentar actualizar caché
    try:
        if bot_instance and bot_instance.connector and bot_instance.connector.exchange:
            # Timeout de 3 segundos para no bloquear
            import threading
            result = [None]
            
            def fetch_with_timeout():
                try:
                    result[0] = bot_instance.connector.exchange.fetch_tickers()
                except Exception as e:
                    log.warning(f"Error fetching tickers: {e}")
                    result[0] = None
            
            thread = threading.Thread(target=fetch_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=3)  # Esperar máximo 3 segundos
            
            if result[0]:
                _tickers_cache["data"] = result[0]
                _tickers_cache["timestamp"] = current_time
                return result[0]
    except Exception as e:
        log.warning(f"Exception in _get_cached_tickers: {e}")
    
    # Devolver caché antiguo o vacío
    return _tickers_cache["data"]

def _get_cached_balance():
    """Obtiene balance con caché de 10 segundos"""
    global _balance_cache
    current_time = time.time()
    
    # Si el caché es válido, devolverlo
    if current_time - _balance_cache["timestamp"] < _cache_ttl and _balance_cache["data"]:
        return _balance_cache["data"]
    
    # Intentar actualizar caché
    try:
        if bot_instance and bot_instance.connector and bot_instance.connector.exchange:
            import threading
            result = [None]
            
            def fetch_with_timeout():
                try:
                    result[0] = bot_instance.connector.exchange.fetch_balance()
                except Exception as e:
                    log.warning(f"Error fetching balance: {e}")
                    result[0] = None
            
            thread = threading.Thread(target=fetch_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=3)  # Esperar máximo 3 segundos
            
            if result[0]:
                _balance_cache["data"] = result[0]
                _balance_cache["timestamp"] = current_time
                return result[0]
    except Exception as e:
        log.warning(f"Exception in _get_cached_balance: {e}")
    
    # Devolver caché antiguo o vacío
    return _balance_cache["data"]

class ConfigUpdate(BaseModel):
    content: str
class CloseOrderRequest(BaseModel):
    symbol: str
    order_id: str
    side: str
    amount: float
class LiquidateRequest(BaseModel):
    asset: str
class ClearHistoryRequest(BaseModel):
    symbol: str
class CoinResetRequest(BaseModel):
    symbol: str
class BalanceAdjustRequest(BaseModel):
    asset: str    
    amount: float 

def _calculate_rsi(candles, period=14):
    try:
        if not candles or len(candles) < period + 1:
            return 50.0 
        closes = [float(c[4]) for c in candles]
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        if avg_gain == 0:
            return 0.0
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    except Exception as e:
        log.debug(f"Error calculating RSI: {e}")
        return 50.0

def start_server(bot, host=None, port=None):
    global bot_instance
    bot_instance = bot
    load_dotenv('config/.env', override=True)
    if host is None:
        host = os.getenv('WEB_HOST', '127.0.0.1')
    if port is None:
        port = int(os.getenv('WEB_PORT', 8001))
    uvicorn.run(app, host=host, port=port, log_level="error")

def format_uptime(seconds):
    if seconds < 0:
        return "0s"
    seconds = int(seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    return f"{hours}h {mins}m"

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- NOU ENDPOINT: INFO COMPTE ---
@app.get("/api/account/info")
def get_account_info_api():
    """Retorna informació del compte: VIP Tier i Comissions"""
    if not bot_instance or not bot_instance.connector:
        return {'tier': 'Offline', 'maker': 0, 'taker': 0}
    
    return bot_instance.connector.get_account_status()
# ---------------------------------

@app.get("/api/status")
def get_status():
    if not bot_instance:
        return {
            "status": "Offline",
            "service": "online",
            "stats": {
                "session": {"trades": 0, "profit": 0, "best_coin": "-", "uptime": "-", "uptime_seconds": 0},
                "global": {"trades": 0, "profit": 0, "best_coin": "-", "uptime": "-", "uptime_seconds": 0},
            },
        }

    try:
        status_text = "Stopped"
        if bot_instance.is_running:
            status_text = "Paused" if bot_instance.is_paused else "Running"

        prices = db.get_all_prices()

        all_balances_cache = {}
        try:
            all_balances_cache = _get_cached_balance()
        except Exception:
            pass

        def get_bal_safe(asset):
            if not all_balances_cache:
                return 0.0
            data = all_balances_cache.get(asset, {})
            free = float(data.get('free', 0.0))
            used = float(data.get('used', 0.0))
            return free + used

        # Calculamos el total basado en la wallet completa (incluye saldos bloqueados y libres)
        portfolio = []
        current_total_equity = 0.0

        # Intentamos extraer balances y tickers del conector (si está disponible)
        balances_map = {}
        tickers = {}
        try:
            if bot_instance.connector and bot_instance.connector.exchange:
                bal = all_balances_cache
                # CCXT puede devolver un dict con 'total' o con subdicts por asset
                if isinstance(bal, dict) and 'total' in bal and isinstance(bal['total'], dict):
                    for asset, total_qty in bal['total'].items():
                        balances_map[asset] = float(total_qty)
                else:
                    for asset, info in (bal or {}).items():
                        if isinstance(info, dict):
                            total_qty = info.get('total')
                            if total_qty is None:
                                free = float(info.get('free', 0.0))
                                used = float(info.get('used', 0.0))
                                total_qty = free + used
                            balances_map[asset] = float(total_qty)

                tickers = _get_cached_tickers()
        except Exception:
            balances_map = {}
            tickers = {}

        # Helper para obtener precio en USDC
        def get_price_usdc(asset):
            if asset in ('USDC', 'USD'):
                return 1.0
            if asset == 'USDT':
                return 1.0
            # Probar pares directos en tickers
            try:
                for pair in (f"{asset}/USDC", f"{asset}/USDT"):
                    t = tickers.get(pair)
                    if t and t.get('last'):
                        return float(t['last'])
            except Exception:
                pass
            # Fallback a precios en DB
            for pair in (f"{asset}/USDC", f"{asset}/USDT"):
                if prices.get(pair):
                    return float(prices.get(pair))
            return 0.0

        wallet_total_usdc = 0.0
        omitted_assets = []
        for asset, qty in balances_map.items():
            try:
                qty = float(qty)
            except Exception:
                continue
            if qty <= 0:
                continue
            price = get_price_usdc(asset)
            value = qty * price
            # Solo incluimos activos con valor superior a 1$
            if value > 1.0:
                wallet_total_usdc += value
                portfolio.append({"name": asset, "value": round(value, 2)})
            else:
                omitted_assets.append({"asset": asset, "qty": qty, "value": round(value, 2)})

        current_total_equity = round(wallet_total_usdc, 2)

        # Aseguramos que usdc_balance esté definido (para compatibilidad con la salida anterior)
        usdc_balance = float(balances_map.get('USDC', 0.0))

        # Preparar mapas auxiliares usados por la lógica de estrategias (compatibilidad)
        current_prices_map = {}
        holding_values = {}
        # Rellenamos current_prices_map y holding_values para los pares configurados (si existen tickers)
        try:
            for pair, tdata in (tickers or {}).items():
                if '/' in pair and tdata and tdata.get('last'):
                    current_prices_map[pair] = float(tdata.get('last'))
        except Exception:
            current_prices_map = {}

        for asset, qty in balances_map.items():
            try:
                qtyf = float(qty)
            except Exception:
                continue
            # Buscamos su valor en USDC a partir de precio directo
            price = get_price_usdc(asset)
            holding_values[f"{asset}/USDC"] = qtyf * price
            holding_values[f"{asset}/USDT"] = qtyf * price  # redundante pero útil para búsqueda


        # 1. Obtenim estadístiques de la SESSIÓ ACTUAL
        session_start_ts = bot_instance.global_start_time
        session_stats = db.get_stats(from_timestamp=session_start_ts)
        session_cash_flow = session_stats['per_coin_stats']['cash_flow']
        
        # 2. Obtenim estadístiques GLOBALS
        global_trades_stats = db.get_stats(from_timestamp=0) 
        
        # Calculamos uptime de sesión (si no hay session_start, usamos el arranque del servidor web como fallback)
        if session_start_ts:
            session_uptime_seconds = int(time.time() - session_start_ts)
        else:
            session_uptime_seconds = int(time.time() - SERVER_START_TS)
        session_uptime_str = format_uptime(session_uptime_seconds)
        first_run_ts = db.get_first_run_timestamp()
        total_uptime_str = format_uptime(time.time() - first_run_ts)
        total_uptime_seconds = int(time.time() - first_run_ts) if first_run_ts else 0

        pairs_to_check = []
        if bot_instance and bot_instance.config:
            pairs_to_check = [p['symbol'] for p in bot_instance.config.get('pairs', [])]

        strategies_data = []
        acc_global_pnl = 0.0
        acc_session_pnl = 0.0

        for symbol in pairs_to_check:
            try:
                pair_config = next((p for p in bot_instance.config['pairs'] if p['symbol'] == symbol), None)
                if not pair_config:
                    continue

                strat_conf = pair_config.get('strategy', {})
                is_enabled = pair_config.get('enabled', False)

                trades_count = global_trades_stats['per_coin_stats']['trades'].get(symbol, 0)
                curr_price = current_prices_map.get(symbol, 0.0)
                curr_val = holding_values.get(symbol, 0.0)
                
                # --- CÀLCUL PNL SESSIÓ ---
                cf_session = session_cash_flow.get(symbol, 0.0)
                qty_delta = session_stats['per_coin_stats']['qty_delta'].get(symbol, 0.0)
                strat_pnl_session = (qty_delta * curr_price) + cf_session

                # --- CÀLCUL PNL GLOBAL (SISTEMA CAIXA REGISTRADORA) ---
                accumulated_history = db.get_accumulated_pnl(symbol)
                strat_pnl_global = accumulated_history + strat_pnl_session
                # -------------------------

                acc_global_pnl += strat_pnl_global
                acc_session_pnl += strat_pnl_session

                if is_enabled or trades_count > 0 or curr_val > 1.0:
                    strategies_data.append({
                        "symbol": symbol,
                        "enabled": is_enabled,
                        "grids": strat_conf.get('grids_quantity', '-'),
                        "amount": strat_conf.get('amount_per_grid', '-'),
                        "spread": strat_conf.get('grid_spread', '-'),
                        "total_trades": trades_count,
                        "total_pnl": round(strat_pnl_global, 2),  
                        "session_pnl": round(strat_pnl_session, 2)
                    })
            except Exception as e:
                log.error(f"Error procesando stats {symbol}: {e}")

        return {
            "status": status_text,
            "service": "online",
            "active_pairs": bot_instance.active_pairs if bot_instance else [], 
            "balance_usdc": round(usdc_balance, 2),
            "total_usdc_value": round(current_total_equity, 2),
            "wallet_total_usdc": round(current_total_equity, 2),
            "portfolio_distribution": portfolio,
            "session_trades_distribution": session_stats['trades_distribution'],
            "global_trades_distribution": global_trades_stats['trades_distribution'],
            "strategies": strategies_data,
            "stats": {
                "session": {
                    "trades": session_stats['trades'],
                    "profit": round(acc_session_pnl, 2),
                    "best_coin": session_stats['best_coin'],
                    "uptime": session_uptime_str,
                    "uptime_seconds": session_uptime_seconds
                },
                "global": {
                    "trades": global_trades_stats['trades'],
                    "profit": round(acc_global_pnl, 2),
                    "best_coin": global_trades_stats['best_coin'],
                    "uptime": total_uptime_str,
                    "uptime_seconds": total_uptime_seconds
                }
            }
        }
    except Exception:
        # Registrar traza completa para depuración y devolver un campo de debug (temporal)
        log.exception("FATAL API ERROR en /api/status")
        return {
            "status": "Error", "service": "offline", "active_pairs": [], "balance_usdc": 0, "total_usdc_value": 0, "portfolio_distribution": [], "session_trades_distribution": [], "global_trades_distribution": [], "strategies": [],
            "stats": { "session": {"trades":0,"profit":0,"best_coin":"-","uptime":"-","uptime_seconds":0}, "global": {"trades":0,"profit":0,"best_coin":"-","uptime":"-","uptime_seconds":0} }
        }

@app.get("/api/history/balance")
def get_balance_history_api(exchange: str = None):
    try:
        # Si no se pasa `exchange` usamos el actual del bot (si existe)
        if not exchange and bot_instance and bot_instance.connector and bot_instance.connector.exchange and hasattr(bot_instance.connector.exchange, 'id'):
            exchange = bot_instance.connector.exchange.id
        full_hist = db.get_balance_history(from_timestamp=0, exchange=exchange)
        session_start = bot_instance.global_start_time if bot_instance else 0
        session_hist = [x for x in full_hist if x[0] >= session_start]
        def fmt(rows):
            return [[r[0]*1000, round(r[1], 2)] for r in rows]
        return { "global": fmt(full_hist), "session": fmt(session_hist) }
    except Exception as e:
        log.exception(f"Error getting balance history: {e}")
        return {"global": [], "session": []}

@app.post("/api/record_balance")
def record_balance_snapshot():
    """Registra un snapshot del balance actual (puede llamarse desde frontend)"""
    try:
        if not bot_instance or not bot_instance.connector:
            return {"success": False, "message": "Bot no inicializado"}
        
        # Calcular equity actual
        try:
            balance = bot_instance.connector.exchange.fetch_balance()
            total_usdc = 0.0
            
            # Sumar USDC directo
            if 'USDC' in balance['total']:
                total_usdc += balance['total']['USDC']
            if 'USDT' in balance['total']:
                total_usdc += balance['total']['USDT']
            
            # Convertir otras monedas a USDC
            tickers = bot_instance.connector.exchange.fetch_tickers()
            for asset, qty in balance['total'].items():
                if asset not in ['USDC', 'USDT'] and qty > 0:
                    symbol = f"{asset}/USDC"
                    if symbol in tickers:
                        price = tickers[symbol]['last']
                        total_usdc += qty * price
            
            # Registrar en DB
            ex_id = bot_instance.connector.exchange.id if hasattr(bot_instance.connector.exchange, 'id') else 'unknown'
            db.log_balance_snapshot(total_usdc, exchange=ex_id)
            
            return {"success": True, "balance": round(total_usdc, 2)}
        except Exception as e:
            log.warning(f"Error registrando balance: {e}")
            return {"success": False, "message": str(e)}
    except Exception as e:
        log.exception(f"Error registrando snapshot: {e}")
        return {"success": False, "message": "Error interno"}

@app.get("/api/top_strategies")
def get_top_strategies():
    """Retorna las estrategias/pares ordenadas por ROI anualizado"""
    try:
        # Obtener todos los trades agrupados por símbolo
        with db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, side, cost, fee_cost, amount, timestamp 
                FROM trade_history 
                ORDER BY timestamp ASC
            """)
            trades = cursor.fetchall()
        
        # Agrupar por símbolo
        symbol_stats = {}
        for symbol, side, cost, fee_cost, amount, timestamp in trades:
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    'symbol': symbol,
                    'pnl': 0.0,
                    'trades': 0,
                    'first_trade_time': timestamp,
                    'capital_invested': 0.0,
                    'sell_proceeds': 0.0,
                }
            
            stats = symbol_stats[symbol]
            stats['trades'] += 1
            
            if side == 'buy':
                stats['capital_invested'] += cost
            else:
                stats['sell_proceeds'] += (cost - fee_cost) if fee_cost else cost
            
            # PnL es lo que ganamos/perdemos
            if side == 'sell':
                stats['pnl'] += (cost - fee_cost) if fee_cost else cost
            else:
                stats['pnl'] -= cost
        
        # Calcular ROI anualizado para cada símbolo
        current_time = time.time()
        strategies_ranked = []
        
        for symbol, stats in symbol_stats.items():
            capital = stats['capital_invested']
            pnl = stats['pnl']
            days_active = max((current_time - stats['first_trade_time']) / 86400, 1)  # Al menos 1 día
            
            if capital > 0:
                roi_percent = (pnl / capital) * 100
                roi_annualized = roi_percent * (365 / days_active) if days_active > 0 else 0
            else:
                roi_percent = 0
                roi_annualized = 0
            
            strategies_ranked.append({
                'symbol': symbol,
                'pnl': round(pnl, 2),
                'roi_percent': round(roi_percent, 2),
                'roi_annualized': round(roi_annualized, 2),
                'capital_invested': round(capital, 2),
                'trades': stats['trades'],
                'days_active': round(days_active, 1)
            })
        
        # Ordenar por ROI anualizado descendente
        strategies_ranked.sort(key=lambda x: x['roi_annualized'], reverse=True)
        
        # Retornar top 5
        return {'strategies': strategies_ranked[:5]}
    except Exception as e:
        log.error(f"Error en /api/top_strategies: {e}")
        return {'strategies': []}

@app.get("/api/orders")
def get_all_orders():
    try:
        raw_orders = db.get_all_active_orders()
        prices = db.get_all_prices()
        enhanced_orders = []
        active_symbols = set()
        if bot_instance:
            active_symbols = set(bot_instance.active_pairs)
        for o in raw_orders:
            symbol = o['symbol']
            if bot_instance and bot_instance.is_running:
                if symbol not in active_symbols:
                    continue
            current_price = prices.get(symbol, 0.0)
            if current_price == 0 and bot_instance and bot_instance.is_running:
                 current_price = bot_instance.connector.fetch_current_price(symbol)
            o['current_price'] = current_price
            o['total_value'] = o['amount'] * o['price']
            o['entry_price'] = 0.0
            if o['side'] == 'sell' and bot_instance:
                try:
                    strat = bot_instance.pairs_map.get(symbol, {}).get('strategy', bot_instance.config['default_strategy'])
                    spread = strat['grid_spread']
                    o['entry_price'] = o['price'] / (1 + (spread / 100.0))
                except Exception as e:
                    log.debug(f"Error computing entry_price for {symbol}: {e}")
            enhanced_orders.append(o)
        return enhanced_orders
    except Exception as e:
        log.exception(f"Error building enhanced orders: {e}")
        return []
    try:
        balances = _get_cached_balance()
        if not balances:
            return []
        tickers = _get_cached_tickers()
        wallet_list = []
        items = balances.get('total', {}).items()
        for asset, total_qty in items:
            if total_qty <= 0:
                continue
            usdc_value = 0.0
            price = 0.0
            if asset == 'USDC':
                usdc_value = total_qty
                price = 1.0
            elif asset == 'USDT':
                usdc_value = total_qty
                price = 1.0
            else:
                symbol = f"{asset}/USDC"
                if symbol in tickers:
                    price = float(tickers[symbol]['last'])
                    usdc_value = total_qty * price
            if usdc_value >= 1.0:
                free_qty = balances.get(asset, {}).get('free', 0.0)
                used_qty = balances.get(asset, {}).get('used', 0.0)
                wallet_list.append({ "asset": asset, "free": free_qty, "locked": used_qty, "total": total_qty, "usdc_value": round(usdc_value, 2), "price": price })
        wallet_list.sort(key=lambda x: x['usdc_value'], reverse=True)
        return wallet_list
    except Exception as e:
        log.error(f"Error fetching wallet: {e}")
        return []

@app.post("/api/liquidate_asset")
def liquidate_asset_api(req: LiquidateRequest):
    if not bot_instance or not bot_instance.connector.exchange:
        raise HTTPException(status_code=503, detail="Bot no conectado")    
    asset = req.asset.upper()
    if asset == 'USDC':
        return {"status": "error", "message": "No se puede liquidar USDC."}
    symbol = f"{asset}/USDC"
    try:
        log.warning(f"LIQUIDACIÓN MANUAL: Cancelando órdenes de {symbol}...")
        bot_instance.connector.cancel_all_orders(symbol)
        time.sleep(1) 
        total_balance = bot_instance.connector.get_total_balance(asset)
        if total_balance > 0:
            log.warning(f"LIQUIDACIÓN MANUAL: Vendiendo {total_balance} {asset} a mercado...")
            order = bot_instance.connector.place_market_sell(symbol, total_balance)
            if order:
                msg = f"Activo {asset} liquidado a USDC."
                log.success(msg)
                send_msg(f"🔥 <b>LIQUIDACIÓN MANUAL</b>\nSe ha vendido todo el {asset} a USDC.")
                return {"status": "success", "message": msg}
            else:
                raise HTTPException(status_code=400, detail="Error al ejecutar la orden de venta.")
        else:
            return {"status": "warning", "message": "Saldo insuficiente para vender."}
    except Exception as e:
        log.error(f"Error liquidando {asset}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/history/clear")
def clear_history_api(req: ClearHistoryRequest):
    symbol = req.symbol
    keep_ids = []
    try:
        with open('config/config.json5', 'r') as f:
            config = json5.load(f)
        pair_conf = next((p for p in config['pairs'] if p['symbol'] == symbol), None)
        spread = pair_conf['strategy']['grid_spread'] if pair_conf else 1.0
        open_orders = []
        if bot_instance and bot_instance.connector.exchange:
            try:
                open_orders = bot_instance.connector.fetch_open_orders(symbol)
            except Exception:
                pass
        if not open_orders:
            data = db.get_pair_data(symbol)
            open_orders = data.get('open_orders', [])
        active_sells = [o for o in open_orders if o['side'] == 'sell']
        for o in active_sells:
            sell_price = float(o['price'])
            uuid = db.get_buy_trade_uuid_for_sell_order(symbol, sell_price, spread)
            if uuid:
                keep_ids.append(uuid)
    except Exception:
        pass
    try:
        count = db.delete_history_smart(symbol, keep_ids)
        return {"status": "success", "message": f"Historial limpiado. Borrados: {count}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/balance/adjust")
def adjust_balance_api(req: BalanceAdjustRequest):
    try:
        asset = req.asset.upper()
        amount = req.amount
        value_usdc = 0.0
        if asset == 'USDC' or asset == 'USDT':
            value_usdc = amount
        elif bot_instance and bot_instance.connector.exchange:
            symbol = f"{asset}/USDC"
            price = bot_instance.connector.fetch_current_price(symbol)
            value_usdc = amount * price
            db.adjust_coin_initial_balance(symbol, value_usdc)
        db.adjust_balance_history(value_usdc)
        tipo = "Ingrés" if amount > 0 else "Retirada"
        log.info(f"💰 AJUST CAPITAL: {tipo} de {amount} {asset} ({value_usdc:.2f} USDC)")
        send_msg(f"📝 <b>CAPITAL {tipo.upper()}</b>\nS'ha ajustat la comptabilitat: {amount} {asset}")
        return {"status": "success", "message": f"Comptabilitat ajustada ({value_usdc:.2f} USDC)."}
    except Exception as e:
        log.error(f"Error ajustant capital: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset_stats")
def reset_stats_api():
    try:
        db.reset_all_statistics()
        if bot_instance:
            bot_instance.global_start_time = time.time()
            bot_instance.levels = {} 
            initial_equity = bot_instance.calculate_total_equity()
            db.set_session_start_balance(initial_equity)
            db.set_global_start_balance_if_not_exists(initial_equity)
            if bot_instance.active_pairs:
                log.info("📸 Forçant snapshot inicial de preus per Reset...")
                bot_instance.capture_initial_snapshots()
        send_msg("⚠️ <b>RESET TOTAL</b>\nSe han borrado todas las estadísticas y reiniciado el punto 0.")
        return {"status": "success", "message": "Reset Total completado. PnL a 0."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/chart/global")
def reset_global_chart_api(exchange: str = None):
    try:
        # Si no se pasa exchange usamos el actual del bot (si existe)
        if not exchange and bot_instance and bot_instance.connector and bot_instance.connector.exchange and hasattr(bot_instance.connector.exchange, 'id'):
            exchange = bot_instance.connector.exchange.id
        db.clear_balance_history(exchange=exchange)
        if exchange:
            return {"status": "success", "message": f"Gráfica Global reiniciada para {exchange}."}
        return {"status": "success", "message": "Gráfica Global reiniciada (todas)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/chart/session")
def reset_session_chart_api():
    try:
        new_time = time.time()
        db.set_session_start_time(new_time)
        if bot_instance:
            bot_instance.global_start_time = new_time
            initial_equity = bot_instance.calculate_total_equity()
            db.set_session_start_balance(initial_equity)
        return {"status": "success", "message": "Gráfica/PnL Sesión reiniciados."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/balance/snapshot")
def snapshot_balance_api(exchange: str = None):
    """Forza una instantánea del balance actual y la guarda en `balance_history`.
    Útil para re-inicializar la gráfica después de borrar datos antiguos.
    """
    try:
        if not bot_instance:
            raise HTTPException(status_code=400, detail="Bot no está inicializado")
        # Determinamos exchange si no se provee
        if not exchange and bot_instance.connector and bot_instance.connector.exchange and hasattr(bot_instance.connector.exchange, 'id'):
            exchange = bot_instance.connector.exchange.id
        current = bot_instance.calculate_total_equity()
        if current <= 0:
            raise HTTPException(status_code=400, detail="Balance calculado inválido")
        db.log_balance_snapshot(current, exchange=exchange if exchange else 'unknown')
        log.info(f"📸 Instantánea guardada en balance_history ({exchange}): {current:.2f} USDC")
        return {"status": "success", "equity": round(current, 2), "exchange": exchange}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error guardando snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/pnl/global")
def reset_global_pnl_api():
    try:
        db.clear_all_trades_history()
        db.reset_global_pnl_history()
        return {"status": "success", "message": "Historial de PnL Global reiniciado a 0."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh_orders")
def refresh_orders_api():
    try:
        db.clear_orders_cache()
        return {"status": "success", "message": "Caché de órdenes limpiada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/coin/session")
def reset_coin_session_api(req: CoinResetRequest):
    try:
        db.set_coin_session_start(req.symbol, time.time())
        if bot_instance:
             try:
                base = req.symbol.split('/')[0]
                qty = bot_instance.connector.get_total_balance(base)
                price = bot_instance.connector.fetch_current_price(req.symbol)
                db.set_coin_initial_balance(req.symbol, qty * price)
             except Exception:
                pass
        return {"status": "success", "message": f"Sesión reiniciada para {req.symbol}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/coin/global")
def reset_coin_global_api(req: CoinResetRequest):
    try:
        db.delete_trades_for_symbol(req.symbol)
        if bot_instance:
             try:
                base = req.symbol.split('/')[0]
                qty = bot_instance.connector.get_total_balance(base)
                price = bot_instance.connector.fetch_current_price(req.symbol)
                db.set_coin_initial_balance(req.symbol, qty * price)
             except Exception:
                pass
        return {"status": "success", "message": f"Historial Global borrado para {req.symbol}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/strategy/analyze/")
def analyze_strategy(symbol: str, timeframe: str = '4h'):
    try:
        rsi = 50.0
        if bot_instance and bot_instance.connector.exchange:
            try:
                raw_candles = bot_instance.connector.fetch_candles(symbol, timeframe=timeframe, limit=500)
                if raw_candles:
                    rsi = _calculate_rsi(raw_candles)
            except Exception as e:
                log.debug(f"Error fetching candles for RSI calculation: {e}")
        base_s = {"conservative": 1.0, "moderate": 0.8, "aggressive": 0.5}
        if timeframe == '15m':
            base_s = {"conservative": 0.6, "moderate": 0.4, "aggressive": 0.25}
        elif timeframe == '1h':
            base_s = {"conservative": 0.8, "moderate": 0.6, "aggressive": 0.35}
        suggestions = {
            "rsi": rsi,
            "conservative": {"grids": 8, "spread": base_s["conservative"]},
            "moderate": {"grids": 10, "spread": base_s["moderate"]},
            "aggressive": {"grids": 12, "spread": base_s["aggressive"]}
        }
        if rsi < 35:
            suggestions["conservative"]["grids"] += 2
            suggestions["conservative"]["spread"] += 0.2
            suggestions["moderate"]["grids"] += 4
            suggestions["aggressive"]["grids"] += 6
            suggestions["aggressive"]["spread"] -= 0.1
        elif rsi > 65:
            suggestions["conservative"]["grids"] -= 3
            suggestions["conservative"]["spread"] += 0.5
            suggestions["moderate"]["grids"] -= 2
            suggestions["moderate"]["spread"] += 0.2
        for k in suggestions:
            if k != "rsi":
                suggestions[k]["spread"] = round(suggestions[k]["spread"], 2)
        return suggestions
    except Exception:
        return {"rsi": 50, "conservative": {"grids": 8, "spread": 1.0}, "moderate": {"grids": 10, "spread": 0.8}, "aggressive": {"grids": 12, "spread": 0.5}}

@app.post("/api/close_order")
def close_order_api(req: CloseOrderRequest):
    if not bot_instance:
        raise HTTPException(status_code=503, detail="Bot no inicializado")
    success = bot_instance.manual_close_order(req.symbol, req.order_id, req.side, req.amount)
    if success:
        return {"status": "success", "message": "Orden cerrada."}
    else:
        raise HTTPException(status_code=400, detail="Error cerrando orden.")

@app.get("/api/details/{symbol:path}")
def get_pair_details(symbol: str, timeframe: str = '15m'):
    try:
        data = db.get_pair_data(symbol)
        raw_candles = data.get('candles', [])
        if not raw_candles and bot_instance and bot_instance.is_running:
            try:
                raw_candles = bot_instance.connector.fetch_candles(symbol, timeframe=timeframe, limit=500)
            except Exception as e:
                log.debug(f"Error fetching candles for {symbol}: {e}")
        chart_data = []
        for candle in raw_candles:
            dt = datetime.fromtimestamp(candle[0]/1000).strftime('%Y-%m-%d %H:%M')
            chart_data.append([dt, candle[1], candle[4], candle[3], candle[2]])

        pnl_value_session = 0.0
        global_pnl = 0.0
        
        if bot_instance:
            current_price = data.get('price', 0.0)
            if current_price == 0 and bot_instance.is_running: 
                current_price = bot_instance.connector.fetch_current_price(symbol)

            if current_price > 0:
                # --- PnL SESSIÓ ---
                coin_session_ts = db.get_coin_session_start(symbol)
                if coin_session_ts == 0:
                    coin_session_ts = bot_instance.global_start_time
                session_stats = db.get_stats(from_timestamp=coin_session_ts)
                cf_session = session_stats['per_coin_stats']['cash_flow'].get(symbol, 0.0)
                qty_delta = session_stats['per_coin_stats']['qty_delta'].get(symbol, 0.0)
                pnl_value_session = (qty_delta * current_price) + cf_session

                # --- PnL GLOBAL ---
                accumulated_history = db.get_accumulated_pnl(symbol)
                global_pnl = accumulated_history + pnl_value_session

        return {
            "symbol": symbol,
            "price": data.get('price', 0.0), 
            "open_orders": data.get('open_orders', []),
            "trades": data.get('trades', []),
            "chart_data": chart_data,
            "grid_lines": data.get('grid_levels', []),
            "session_pnl": round(pnl_value_session, 2), 
            "global_pnl": round(global_pnl, 2)   
        }
    except Exception as e:
        log.error(f"Error details {symbol}: {e}")
        return {"symbol": symbol, "price": 0, "open_orders": [], "trades": [], "chart_data": [], "grid_lines": [], "session_pnl": 0, "global_pnl": 0}

@app.get("/api/config")
def get_config():
    try:
        with open('config/config.json5', 'r') as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
def save_config(config: ConfigUpdate):
    try:
        json5.loads(config.content)
        with open('config/config.json5', 'w') as f:
            f.write(config.content)
        if bot_instance:
            bot_instance.connector.check_and_reload_config()
            bot_instance.config = bot_instance.connector.config
            bot_instance._refresh_pairs_map()
        send_msg("💾 <b>CONFIGURACIÓN GUARDADA</b>\nSe han aplicado cambios desde la web.")
        return {"status": "success", "message": "Configuración guardada y aplicada."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error JSON5: {e}")

@app.post("/api/panic/stop")
def panic_stop_api():
    if bot_instance:
        bot_instance.panic_stop() 
        return {"status": "success", "message": "Bot PAUSADO."}
    return {"status": "error", "detail": "Bot no iniciado"}

@app.post("/api/panic/start")
def panic_start_api():
    if bot_instance:
        bot_instance.resume_bot()
        return {"status": "success", "message": "Bot REANUDADO."}
    return {"status": "error", "detail": "Bot no iniciado"}

@app.post("/api/panic/cancel_all")
def panic_cancel_all_api():
    if bot_instance:
        bot_instance.panic_cancel_all()
        return {"status": "success", "message": "Órdenes canceladas."}
    return {"status": "error", "detail": "Bot no iniciado"}

@app.post("/api/panic/sell_all")
def panic_sell_all_api():
    if bot_instance:
        bot_instance.panic_sell_all()
        return {"status": "success", "message": "Venta pánico ejecutada."}
    return {"status": "error", "detail": "Bot no iniciado"}

@app.post("/api/engine/on")
def engine_on_api():
    if bot_instance:
        if bot_instance.launch():
            return {"status": "success", "message": "Motor de trading ARRANCADO."}
        else:
            return {"status": "warning", "message": "El motor ya está corriendo."}
    return {"status": "error", "detail": "Error interno"}

@app.post("/api/engine/off")
def engine_off_api():
    if bot_instance:
        bot_instance.stop_logic()
        return {"status": "success", "message": "Motor de trading APAGADO."}
    return {"status": "error", "detail": "Error interno"}