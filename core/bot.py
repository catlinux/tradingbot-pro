"""Módulo principal del bot GridBot Pro.
Orquesta la lógica de trading en grid con gestión de base de datos e integración con Binance.
"""
from core.exchange import BinanceConnector
from core.database import BotDatabase
from utils.logger import log
from utils.telegram import send_msg 
import time
import math
import threading
from datetime import datetime
from colorama import Fore, Style

class GridBot:
    def __init__(self):
        self.connector = BinanceConnector()
        self.db = BotDatabase()
        self.config = self.connector.config
        self.pairs_map = {}
        self._refresh_pairs_map()
        self.levels = {} 
        self.is_running = False
        self.is_paused = False 
        self.reserved_inventory = {} 
        self.global_start_time = 0
        self.bot_thread = None
        
        self.processed_trade_ids = set()
        self.session_trades_count = {} 
        
        self.last_prune_time = 0
        self.last_daily_report_date = None
        self.last_backup_time = 0  # Temporizador para copia de seguridad de PnL

    def _refresh_pairs_map(self):
        self.pairs_map = {p['symbol']: p for p in self.config['pairs'] if p['enabled']}
        self.active_pairs = list(self.pairs_map.keys())

    def _calculate_rsi(self, candles, period=14):
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
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    def _data_collector_loop(self):
        while self.is_running:
            # Si está en pausa, no hacemos nada; si está desconectado seguimos ejecutando para poder tomar snapshots de exchanges configurados
            if self.is_paused:
                time.sleep(1)
                continue
            
            # --- MANTENIMIENTO DE BASE DE DATOS (Cada 24h) ---
            if time.time() - self.last_prune_time > 86400:
                try:
                    log.info("🧹 Ejecutando mantenimiento de Base de Datos...")
                    d_trades, d_bal = self.db.prune_old_data(days_keep=30)
                    if d_trades > 0 or d_bal > 0:
                        log.success(f"DB optimizada: Borrados {d_trades} trades y {d_bal} registros antiguos.")
                    self.last_prune_time = time.time()
                except Exception as e:
                    log.error(f"Error en mantenimiento DB: {e}")
            
            # --- COPIA DE SEGURIDAD DE PnL (Cada ~30s) ---
            # Guardamos el PnL de la sesión actual en la tabla de seguridad
            if time.time() - self.last_backup_time > 30:
                try:
                    self._backup_current_session_pnl()
                    self.last_backup_time = time.time()
                except Exception:
                    pass

            now = datetime.now()
            current_date_str = now.strftime("%Y-%m-%d")
            
            if now.hour == 8 and self.last_daily_report_date != current_date_str:
                try:
                    log.info("📊 Generando informe diario...")
                    stats_24h = self.db.get_stats(from_timestamp=time.time() - 86400)
                    total_profit = sum(stats_24h['per_coin_stats']['cash_flow'].values())
                    total_trades = stats_24h['trades']
                    best_coin = stats_24h['best_coin']
                    
                    icon = "🟢" if total_profit >= 0 else "🔴"
                    msg = (f"📅 <b>INFORME DIARIO (24h)</b>\n"
                           f"--------------------------------\n"
                           f"{icon} <b>Beneficio: {total_profit:+.2f} USDC</b>\n"
                           f"🔢 Operaciones: {total_trades}\n"
                           f"🏆 Top Moneda: {best_coin}\n"
                           f"--------------------------------\n"
                           f"<i>Sistema funcionando correctamente.</i>")
                    
                    send_msg(msg)
                    self.last_daily_report_date = current_date_str
                    log.success("Informe diario enviado a Telegram.")
                except Exception as e:
                    log.error(f"Error enviando informe diario: {e}")

            current_pairs = list(self.active_pairs)
            for symbol in current_pairs:
                try:
                    price = self.connector.fetch_current_price(symbol)
                    candles = self.connector.fetch_candles(symbol, limit=500) 
                    self.db.update_market_snapshot(symbol, price, candles)

                    open_orders = self.connector.fetch_open_orders(symbol) or []
                    grid_levels = self.levels.get(symbol, [])
                    self.db.update_grid_status(symbol, open_orders, grid_levels)

                    trades = self.connector.fetch_my_trades(symbol, limit=10)
                    self.db.save_trades(trades)
                    
                    self._check_and_alert_trades(symbol, trades)
                except Exception:
                    pass
                time.sleep(1) 
            
            # Snapshots programados:
            # - Exchange conectado: cada 60s
            # - Exchanges desconectados: cada 180s (3 minutos) para reducir uso de rate limits
            now_ts = int(time.time())
            # 1) Exchange activo: cada 60s
            if now_ts % 60 == 0:
                try:
                    total_equity = self.calculate_total_equity()
                    if total_equity > 0:
                        ex_id = 'unknown'
                        try:
                            if hasattr(self, 'active_exchange_name') and self.active_exchange_name:
                                ex_id = self.active_exchange_name
                                if getattr(self, 'active_exchange_use_testnet', False):
                                    ex_id = f"{ex_id}-testnet"
                            else:
                                # Fallback: usar id interno de ccxt si está disponible
                                if self.connector and self.connector.exchange and hasattr(self.connector.exchange, 'id'):
                                    ex_id = self.connector.exchange.id
                        except Exception:
                            pass
                        # Snapshot del exchange activo
                        self.db.log_balance_snapshot(total_equity, exchange=ex_id)
                except Exception:
                    pass

            # 2) Exchanges desconectados: cada 180s
            if now_ts % 180 == 0:
                try:
                    exchanges = self.db.get_exchanges()
                    for e in exchanges:
                        name = e.get('name')
                        use_testnet = e.get('use_testnet', False)
                        ex_key = f"{name}-testnet" if use_testnet else name

                        # Saltar si es el exchange activo (ya fue procesado cada 60s)
                        try:
                            active_id = 'unknown'
                            if hasattr(self, 'active_exchange_name') and self.active_exchange_name:
                                active_id = self.active_exchange_name
                                if getattr(self, 'active_exchange_use_testnet', False):
                                    active_id = f"{active_id}-testnet"
                            elif self.connector and self.connector.exchange and hasattr(self.connector.exchange, 'id'):
                                active_id = self.connector.exchange.id
                        except Exception:
                            active_id = 'unknown'

                        if ex_key == active_id:
                            continue

                        taken = False
                        # Intentar obtener credenciales y hacer fetch real
                        try:
                            creds = self.db.get_exchange_credentials(name)
                            if creds.get('success') and creds.get('api_key') and creds.get('secret_key'):
                                fetched = BinanceConnector.fetch_balance_snapshot_static(creds.get('api_key'), creds.get('secret_key'), creds.get('passphrase'), use_testnet, exchange_type=e.get('type', 'binance'))
                                if fetched and fetched > 0:
                                    self.db.log_balance_snapshot(fetched, exchange=ex_key)
                                    log.debug(f"Snapshot real para {ex_key}: {fetched:.2f} USDC")
                                    taken = True
                                    # pequeña espera para no pisar rate limits
                                    time.sleep(0.5)
                        except Exception as inner_e:
                            log.debug(f"No se pudo obtener snapshot real para {ex_key}: {inner_e}")

                        if taken:
                            continue

                        # Fallback: carry-forward si existe última snapshot
                        try:
                            last = self.db.get_last_balance_snapshot(ex_key)
                            if last:
                                last_equity = float(last[1])
                                self.db.log_balance_snapshot(last_equity, exchange=ex_key)
                                log.debug(f"Carry-forward snapshot para {ex_key}: {last_equity:.2f} USDC")
                        except Exception:
                            pass
                except Exception:
                    pass
    
    def _backup_current_session_pnl(self):
        """Calcula el PnL actual de la sesión y lo guarda en copia de seguridad"""
        if not self.global_start_time:
            return
        
        # Obtenemos estadísticas desde el inicio de la sesión
        stats = self.db.get_stats(from_timestamp=self.global_start_time)
        cash_flows = stats['per_coin_stats']['cash_flow']
        qty_deltas = stats['per_coin_stats']['qty_delta']
        
        # Obtenemos precios actuales para calcular valor latente
        prices = self.db.get_all_prices()
        
        for symbol in self.active_pairs:
            try:
                cf = cash_flows.get(symbol, 0.0)
                qty_delta = qty_deltas.get(symbol, 0.0)
                price = prices.get(symbol, 0.0)
                if price == 0:
                     price = self.connector.fetch_current_price(symbol)
                
                # PnL Sesión = CashFlow + (QtyDelta * Price)
                session_pnl = cf + (qty_delta * price)
                
                self.db.update_pnl_backup(symbol, session_pnl)
            except Exception:
                pass

    def _check_and_alert_trades(self, symbol, trades):
        if not trades:
            return
        strat = self.pairs_map.get(symbol, {}).get('strategy', self.config['default_strategy'])
        spread_pct = strat.get('grid_spread', 1.0)

        if symbol not in self.session_trades_count:
            self.session_trades_count[symbol] = 0

        for t in trades:
            tid = t['id']
            side = t['side'].upper()
            
            buy_id_assigned = None
            if side == 'BUY':
                 buy_id_assigned = self.db.assign_id_to_trade_if_missing(tid)

            if tid in self.processed_trade_ids:
                continue
            
            if t['timestamp'] < (self.global_start_time * 1000):
                self.processed_trade_ids.add(tid)
                continue

            self.processed_trade_ids.add(tid)
            self.session_trades_count[symbol] += 1
            
            price = float(t['price'])
            amount = float(t['amount'])
            cost = float(t['cost'])
            
            fee_cost = 0.0
            fee_currency = ""
            if 'fee' in t and t['fee']:
                fee_cost = float(t['fee'].get('cost', 0.0))
                fee_currency = t['fee'].get('currency', '')
            
            # Normalitzem comissió
            fee_in_usdc = fee_cost
            if fee_currency != 'USDC' and fee_currency != 'USDT':
                fee_in_usdc = fee_cost * price

            # Forzamos una copia de seguridad inmediatamente después de una operación importante
            try:
                self._backup_current_session_pnl()
            except Exception:
                pass

            msg = ""
            if side == 'BUY':
                header_id = f"(ID #{buy_id_assigned})" if buy_id_assigned else ""
                if self.session_trades_count[symbol] == 1:
                    header = f"🚀 🟢 <b>ENTRADA {header_id}</b>"
                else:
                    header = f"🟢 <b>COMPRA {header_id}</b>"
                msg = (f"{header}\nPar: <b>{symbol}</b>\nPrecio: {price:.4f}\nCantidad: {amount}\nCoste Total: {cost:.2f} USDC")
            
            else:  # SELL
                linked_id = self.db.find_linked_buy_id(symbol, price, spread_pct)
                if linked_id:
                    self.db.set_trade_buy_id(tid, linked_id)

                id_text = f"#{linked_id}" if linked_id else "?"
                buy_price_ref = price / (1 + (spread_pct / 100))
                gross_profit = (price - buy_price_ref) * amount
                total_fees_est = fee_in_usdc * 2 
                net_profit = gross_profit - total_fees_est
                if net_profit < 0:
                    net_profit = 0.0
                percent_profit = (net_profit / cost) * 100 if cost > 0 else 0.0
                
                msg = (f"🔴 <b>VENTA (Cierra ID {id_text})</b>\n"
                       f"Par: <b>{symbol}</b>\n"
                       f"Precio Venta: {price:.4f}\n"
                       f"Total Recibido: {cost:.2f} USDC\n"
                       f"------------------\n"
                       f"💰 <b>Beneficio Neto Est.: +{net_profit:.3f} USDC</b>\n"
                       f"📈 <i>Rentabilidad Op.: {percent_profit:.2f}%</i>")

            send_msg(msg)

    def _get_params(self, symbol):
        pair_config = self.pairs_map.get(symbol, {})
        return pair_config.get('strategy', self.config['default_strategy'])

    def _generate_fixed_levels(self, symbol, current_price):
        params = self._get_params(symbol)
        quantity = params['grids_quantity']
        spread_percent = params['grid_spread'] / 100 
        log.info(f"Calculando rejilla {symbol} ({current_price})...")
        levels = []
        for i in range(1, int(quantity / 2) + 1):
            levels.append(current_price * (1 - (spread_percent * i))) 
            levels.append(current_price * (1 + (spread_percent * i))) 
        levels.sort()
        clean_levels = []
        for p in levels:
            try:
                p_str = self.connector.exchange.price_to_precision(symbol, p)
                clean_levels.append(float(p_str))
            except Exception:
                clean_levels.append(p)
        return clean_levels

    def _get_amount_for_level(self, symbol, price):
        params = self._get_params(symbol)
        amount_usdc = params['amount_per_grid']
        base_amount = amount_usdc / price 
        market = self.connector.exchange.market(symbol)
        min_amount = market['limits']['amount']['min']
        if base_amount < min_amount:
            return 0.0
        try:
            amt_str = self.connector.exchange.amount_to_precision(symbol, base_amount)
            return float(amt_str)
        except Exception:
            return 0.0

    def _ensure_grid_consistency(self, symbol):
        current_price = self.connector.fetch_current_price(symbol)
        if current_price == 0:
            return

        params = self._get_params(symbol)
        base_asset = symbol.split('/')[0]
        balance_base = self.connector.get_total_balance(base_asset)
        amount_buy_usdc = params['amount_per_grid']
        
        if not self.db.get_symbol_setup_done(symbol):
            mode = params.get('start_mode', 'wait')
            
            if mode == 'buy_1' or mode == 'buy_2':
                multiplier = 2 if mode == 'buy_2' else 1
                total_invest = amount_buy_usdc * multiplier
                log.warning(f"🚀 ARRANQUE {mode.upper()}: Comprando {total_invest} USDC de {symbol}...")
                
                buy_order = self.connector.place_market_buy(symbol, total_invest)
                
                if buy_order:
                    log.success(f"✅ Compra inicial ({mode}) ejecutada.")
                    send_msg(f"🚀 <b>ARRANQUE RÁPIDO ({mode.upper()})</b>\nCompra a mercado ejecutada en {symbol}.")
                    time.sleep(2)
                else:
                    log.error(f"❌ Falló la compra inicial de {symbol}.")
            
            self.db.set_symbol_setup_done(symbol, True)
            return 
        
        value_held = balance_base * current_price
        
        if value_held < 5.0:
            log.warning(f"⚠️ {symbol}: Sin inventario ({value_held:.2f} $). Ejecutando COMPRA INICIAL...")
            usdc_balance = self.connector.get_asset_balance('USDC')
            if usdc_balance > amount_buy_usdc:
                buy_order = self.connector.place_market_buy(symbol, amount_buy_usdc)
                if buy_order:
                    log.success(f"✅ Compra inicial ejecutada para {symbol}.")
                    time.sleep(2) 
                    return 
            else:
                log.error(f"Falta USDC para compra inicial de {symbol}.")

        open_orders = self.connector.fetch_open_orders(symbol)
        
        if symbol not in self.levels:
            self.levels[symbol] = self._generate_fixed_levels(symbol, current_price)

        my_levels = self.levels[symbol]
        
        if params.get('trailing_enabled', False) and my_levels:
             my_levels.sort()
             max_level = my_levels[-1]
             spread_val = params['grid_spread'] / 100
             trigger_price = max_level * (1 + (spread_val * 0.2))
             
             if current_price > trigger_price:
                 log.warning(f"🚀 TRAILING UP: {symbol} ha roto techo ({max_level}). Moviendo rejilla...")
                 lowest_level = my_levels.pop(0)
                 for o in open_orders:
                     if math.isclose(o['price'], lowest_level, rel_tol=1e-5):
                         log.info(f"🗑️ Cancelando orden inferior {o['id']} ({lowest_level}) para liberar grid.")
                         self.connector.cancel_order(o['id'], symbol)
                         break
                 new_top = max_level * (1 + spread_val)
                 try:
                    p_str = self.connector.exchange.price_to_precision(symbol, new_top)
                    new_top = float(p_str)
                 except Exception:
                    pass
                 my_levels.append(new_top)
                 self.levels[symbol] = sorted(my_levels)
                 send_msg(f"🧗 <b>TRAILING UP {symbol}</b>\nEl precio ha subido. Grid desplazado hacia arriba.\nNuevo techo: {new_top}")
                 return 

        base_asset, quote_asset = symbol.split('/')
        spread_val = params['grid_spread'] / 100
        margin = current_price * (spread_val * 0.1) 

        for level_price in my_levels:
            target_side = None
            if level_price > current_price + margin:
                target_side = 'sell'
            elif level_price < current_price - margin:
                target_side = 'buy'
            else:
                continue 

            if target_side == 'sell':
                last_buy_price = self.db.get_last_buy_price(symbol)
                min_sell_price = last_buy_price * (1 + (spread_val * 0.5))
                if level_price < min_sell_price:
                    continue

            exists = False
            for o in open_orders:
                if math.isclose(o['price'], level_price, rel_tol=1e-5):
                    if o['side'] == target_side:
                        exists = True
                    else:
                        self.connector.exchange.cancel_order(o['id'], symbol)
                        exists = False
                    break
            if exists:
                continue 

            amount = self._get_amount_for_level(symbol, level_price)
            if amount == 0:
                continue

            if target_side == 'buy':
                balance = self.connector.get_asset_balance(quote_asset)
                if balance < amount * level_price:
                    continue
            else: 
                balance = self.connector.get_asset_balance(base_asset)
                reserved = self.reserved_inventory.get(base_asset, 0.0)
                if (balance - reserved) < amount * 0.99:
                    continue
                if balance < amount and balance > amount * 0.9:
                    try:
                        amount = float(self.connector.exchange.amount_to_precision(symbol, balance))
                    except Exception:
                        pass

            log.warning(f"[{symbol}] Creando orden {target_side} @ {level_price}")
            self.connector.place_order(symbol, target_side, amount, level_price)

        for o in open_orders:
            match_found = False
            for lvl in my_levels:
                if math.isclose(o['price'], lvl, rel_tol=1e-5):
                    match_found = True
                    break
            if not match_found:
                log.info(f"🧹 Limpiando orden huérfana {o['id']} ({o['price']}) - Fuera de rango.")
                self.connector.cancel_order(o['id'], symbol)

    def _handle_smart_reload(self):
        print() 
        log.warning("🔄 CONFIGURACIÓN ACTUALIZADA: Analizando cambios...")
        old_testnet = self.config.get('system', {}).get('use_testnet', True)
        new_config = self.connector.config 
        new_testnet = new_config.get('system', {}).get('use_testnet', True)
        self.config = new_config
        self._refresh_pairs_map()
        
        if old_testnet != new_testnet:
            network_name = "TESTNET" if new_testnet else "REAL"
            log.warning(f"🚨 CAMBIO DE RED DETECTADO A: {network_name}. Reiniciando sistema...")
            send_msg(f"🔄 <b>CAMBIO DE RED</b>\nEl bot ha pasado a modo: <b>{network_name}</b>")
            self.levels = {}
            self.reserved_inventory = {}
            self.db.reset_all_statistics()
            self.processed_trade_ids.clear()
            self.session_trades_count = {} 
            log.info("Recalculando patrimonio en la nueva red...")
            initial_equity = self.calculate_total_equity()
            self.db.set_session_start_balance(initial_equity)
            self.db.set_global_start_balance_if_not_exists(initial_equity)
            self.capture_initial_snapshots()
            self.global_start_time = time.time()
            log.success(f"✅ Sistema reiniciado en modo {network_name}.")
            return

        new_symbols = set(self.pairs_map.keys())
        active_running_symbols = set(self.levels.keys())
        
        removed = active_running_symbols - new_symbols
        for symbol in removed:
            log.info(f"⛔ Deteniendo {symbol}. Cancelando órdenes...")
            self.connector.cancel_all_orders(symbol)
            if symbol in self.levels:
                del self.levels[symbol]
            if symbol in self.reserved_inventory:
                del self.reserved_inventory[symbol.split('/')[0]]
            
        added = new_symbols - active_running_symbols
        for symbol in added:
            log.success(f"✨ Activando {symbol}.")
        
        log.info("✅ Recarga completada.")
        send_msg("⚙️ <b>CONFIGURACIÓN ACTUALIZADA</b>\nNuevos parámetros aplicados.")

    def manual_close_order(self, symbol, order_id, side, amount):
        print()
        log.warning(f"MANUAL: Cerrando orden {order_id} ({side}) en {symbol}...")
        self.connector.cancel_order(order_id, symbol)
        if side == 'buy':
            log.success(f"Orden {order_id} cancelada. USDC recuperados.")
            send_msg(f"🗑️ <b>ORDEN CANCELADA (Manual)</b>\n{symbol} - {side}")
            return True
        elif side == 'sell':
            time.sleep(0.5)
            market_order = self.connector.place_market_sell(symbol, amount)
            if market_order:
                log.success("Activo vendido a mercado (Market Sell) correctamente.")
                send_msg(f"🔥 <b>VENTA A MERCADO (Manual)</b>\n{symbol} - {amount}")
                return True
            else:
                log.error("No se ha podido ejecutar el Market Sell.")
                return False

    def calculate_total_equity(self):
        total_usdc = 0.0
        try:
            total_usdc += self.connector.get_total_balance('USDC')
        except Exception:
            pass
        for symbol in self.active_pairs:
            base = symbol.split('/')[0]
            try:
                qty = self.connector.get_total_balance(base)
                if qty > 0:
                    price = self.connector.fetch_current_price(symbol)
                    total_usdc += (qty * price)
            except Exception:
                pass
        return total_usdc

    def capture_initial_snapshots(self):
        for symbol in self.active_pairs:
            base = symbol.split('/')[0]
            try:
                qty = self.connector.get_total_balance(base)
                price = self.connector.fetch_current_price(symbol)
                initial_value = qty * price
                self.db.set_coin_initial_balance(symbol, initial_value)
            except Exception as e:
                log.error(f"Error snapshot {symbol}: {e}")

    def panic_stop(self):
        print()
        log.warning("⛔ ACCIÓN DE USUARIO: PAUSANDO BOT...")
        self.is_paused = True
        send_msg("⏸️ <b>BOT PAUSADO</b>\nSe han detenido todas las operaciones.")
        return True

    def resume_bot(self):
        print()
        log.success("▶️ ACCIÓN DE USUARIO: REANUDANDO BOT...")
        self.is_paused = False
        send_msg("▶️ <b>BOT REANUDADO</b>\nContinuando operaciones.")
        return True

    def panic_cancel_all(self):
        print()
        log.warning("⛔ ACCIÓN DE PÁNICO: Cancelando todas las órdenes...")
        send_msg("🗑️ <b>PÁNICO: CANCELAR TODO</b>\nBorrando todas las órdenes del exchange...")
        count = 0
        for symbol in self.active_pairs:
            self.connector.cancel_all_orders(symbol)
            grid_levels = self.levels.get(symbol, [])
            self.db.update_grid_status(symbol, [], grid_levels)
            count += 1
        return count

    def panic_sell_all(self):
        print()
        log.warning("🔥 ACCIÓN DE PÁNICO: VENDIENDO TODO A USDC...")
        send_msg("🔥 <b>PÁNICO: VENDER TODO</b>\nLiquidando cartera a USDC...")
        sold_count = 0
        self.panic_cancel_all()
        time.sleep(2) 

        for symbol in self.active_pairs:
            try:
                base_asset = symbol.split('/')[0]
                amount = self.connector.get_asset_balance(base_asset)
                price = self.connector.fetch_current_price(symbol)
                value_usdc = amount * price
                
                if value_usdc > 2.0: 
                    log.warning(f"Vendiendo {amount} {base_asset} a mercado...")
                    self.connector.place_market_sell(symbol, amount)
                    sold_count += 1
                    time.sleep(0.5) 
            except Exception as e:
                log.error(f"Error Panic Sell {symbol}: {e}")
        
        send_msg(f"🔥 <b>PÁNICO FINALIZADO</b>\nSe han liquidado {sold_count} posiciones.")
        return sold_count

    def start_logic(self):
        log.info(f"{Fore.CYAN}--- INICIANDO GRIDBOT PROFESSIONAL ---{Style.RESET_ALL}")
        
        self.connector.check_and_reload_config()
        self.config = self.connector.config 
        self.connector.validate_connection()
        
        log.info("Calculando patrimonio inicial...")
        initial_equity = self.calculate_total_equity()
        log.info(f"💰 Patrimonio Inicial Total: {Fore.GREEN}{initial_equity:.2f} USDC{Fore.RESET}")
        
        self.db.set_session_start_balance(initial_equity)
        self.db.set_global_start_balance_if_not_exists(initial_equity)
        self.capture_initial_snapshots()
        
        # --- LOGICA NOVA DE SESSIONS ---
        # Abans de començar una sessió nova, arxivamos la vella si existeix
        if self.db.archive_session_stats():
            log.success("Sessió anterior arxivada correctament a l'històric.")
        
        self.global_start_time = time.time()
        self.processed_trade_ids.clear()

        send_msg(f"🚀 <b>MOTOR INICIADO</b>\nPatrimonio inicial: {initial_equity:.2f} USDC")

        log.warning("Limpiando órdenes antiguas iniciales...")
        for symbol in self.active_pairs:
            self.connector.cancel_all_orders(symbol)
        
        log.info("Arrancando motores...")
        time.sleep(2)
        
        self.is_running = True
        self.is_paused = False 
        
        data_thread = threading.Thread(target=self._data_collector_loop, daemon=True)
        data_thread.start()
        
        try:
            self._monitoring_loop()
        except KeyboardInterrupt:
            self._shutdown()

    def launch(self):
        if self.is_running:
            log.warning("El bot ya está corriendo!")
            return False
        
        self.bot_thread = threading.Thread(target=self.start_logic, daemon=True)
        self.bot_thread.start()
        return True

    def stop_logic(self):
        if not self.is_running:
            return
        log.warning("Deteniendo lógica del bot...")
        self.is_running = False
        
        # Forcem un últim backup abans de parar
        try:
            self._backup_current_session_pnl()
        except Exception:
            pass

        send_msg("🛑 <b>MOTOR DETENIDO</b>\nEl bot se ha apagado.")
        log.success("Bot detenido.")

    def _monitoring_loop(self):
        delay = self.config['system']['cycle_delay']
        spin_chars = ["|", "/", "-", "\\"]
        idx = 0
        while self.is_running:
            if self.is_paused:
                log.status(f"{Fore.YELLOW}PAUSADO{Fore.RESET} - Esperando comando... {spin_chars[idx]}")
                idx = (idx + 1) % 4
                time.sleep(1)
                continue
            
            if not self.connector.exchange:
                if self.connector.check_and_reload_config():
                    self._handle_smart_reload()
                log.status(f"{Fore.RED}SIN CONEXIÓN{Fore.RESET} - Revisa API Keys / Red... {spin_chars[idx]}")
                idx = (idx + 1) % 4
                time.sleep(1)
                continue

            if self.connector.check_and_reload_config():
                self._handle_smart_reload()
            
            for symbol in self.active_pairs:
                self._ensure_grid_consistency(symbol)
            
            display_status = f"{Fore.GREEN}EN MARCHA{Fore.RESET} | Monitorizando {len(self.active_pairs)} pares | {spin_chars[idx]}"
            log.status(display_status)
            idx = (idx + 1) % 4
            time.sleep(delay)

    def _shutdown(self):
        self.is_running = False
        # Forcem un últim backup en sortir per Ctrl+C
        try:
            self._backup_current_session_pnl()
        except Exception:
            pass
        print()
        log.warning("--- DETENIENDO GRIDBOT ---")
        log.success("Bot detenido.")