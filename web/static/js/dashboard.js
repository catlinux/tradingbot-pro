/**
 * GridBot Pro Dashboard
 * Orquestación principal del panel web
 * Gestiona carga de datos, renderizado de gráficas e interacciones de usuario
 */

import { fmtUSDC, fmtPrice, fmtInt, fmtCrypto, fmtPct, updateColorValue } from './utils.js';
import { renderDonut, renderLineChart, renderCandleChart, renderEChart, resetChartZoom, destroyChart } from './charts.js';
import { loadConfigForm, saveConfigForm, toggleCard, changeRsiTf, applyStrategy, setManual, analyzeSymbol } from './config.js';

// --- ESTADO GLOBAL ---
let currentMode = 'home';
let currentTimeframe = '15m';
let currentChartType = 'candles'; 
let dataCache = {}; 
let fullGlobalHistory = []; 
let sessionUptimeInterval = null; 
let sessionUptimeBase = null; // segundos (del servidor)
let sessionOnlineState = null; // booleano


// --- EXPORTAR A WINDOW (requierido para onclick del HTML) ---
window.loadConfigForm = loadConfigForm;
window.saveConfigForm = saveConfigForm;
window.toggleCard = toggleCard;
window.changeRsiTf = changeRsiTf;
window.applyStrategy = applyStrategy;
window.setManual = setManual;
window.setMode = setMode;
window.setTimeframe = setTimeframe;
window.setChartType = setChartType;
window.resetZoom = resetZoom; 
window.loadWallet = loadWallet;
window.resetStatistics = resetStatistics;
window.panicStop = panicStop;
window.panicStart = panicStart;
window.panicCancel = panicCancel;
window.panicSell = panicSell;
window.startEngine = startEngine;
window.stopEngine = stopEngine;
window.clearHistory = clearHistory;
window.closeOrder = closeOrder;
window.filterHistory = filterHistory; 
window.liquidateAsset = liquidateAsset;
window.resetGlobalChart = resetGlobalChart;
window.resetSessionChart = resetSessionChart;
window.resetGlobalPnL = resetGlobalPnL;
window.refreshOrders = refreshOrders;
window.resetCoinSession = resetCoinSession;
window.resetCoinGlobal = resetCoinGlobal;
window.changeTheme = changeTheme;
window.openCapitalAdjustment = openCapitalAdjustment;
window.recordBalanceSnapshot = recordBalanceSnapshot;
window.loadTopStrategies = loadTopStrategies;

/**
 * Filtra picos en los datos de balance
 * Ignora variaciones >30% que duren <1 minuto
 */
function filterBalancePikes(history) {
    if (!Array.isArray(history) || history.length < 2) return history;
    
    // Detectar formato: array de [timestamp, balance] o array de objetos
    const isArrayFormat = Array.isArray(history[0]);
    
    const filtered = [history[0]];
    const spike_threshold = 0.30; // 30%
    const spike_duration_ms = 60000; // 1 minuto
    
    for (let i = 1; i < history.length; i++) {
        const prev = filtered[filtered.length - 1];
        const current = history[i];
        
        // Extraer valor de balance según formato
        const prevBalance = isArrayFormat ? prev[1] : prev.balance;
        const currBalance = isArrayFormat ? current[1] : current.balance;
        const prevTimestamp = isArrayFormat ? prev[0] : prev.timestamp;
        const currTimestamp = isArrayFormat ? current[0] : current.timestamp;
        
        // Calcular variación porcentual
        const change = Math.abs((currBalance - prevBalance) / Math.max(prevBalance, 0.01));
        
        if (change > spike_threshold) {
            // Posible pico - buscar si se recupera rápido
            let isPike = false;
            for (let j = i + 1; j < history.length; j++) {
                const next = history[j];
                const nextBalance = isArrayFormat ? next[1] : next.balance;
                const nextTimestamp = isArrayFormat ? next[0] : next.timestamp;
                
                const timeDiff = nextTimestamp - currTimestamp;
                const recoveryChange = Math.abs((nextBalance - currBalance) / Math.max(currBalance, 0.01));
                
                // Si en menos de 1 minuto se recupera significativamente, es un pico
                if (timeDiff < spike_duration_ms && recoveryChange > spike_threshold * 0.5) {
                    isPike = true;
                    break;
                }
                
                if (timeDiff >= spike_duration_ms) break;
            }
            
            // Si es pico, saltarlo; si no, incluirlo
            if (!isPike) {
                filtered.push(current);
            }
        } else {
            filtered.push(current);
        }
    }
    
    return filtered;
}

// --- FUNCIÓN PRINCIPAL DE INICIALIZACIÓN ---
/**
 * Inicializa el panel al cargar la página
 * Establece tema, valida librerías gráficas e inicia carga de datos
 */
async function init() {
    try {
        
        // Forzar tema claro por defecto
        const savedTheme = 'light';
        localStorage.setItem('gridbot_theme', 'light');
        changeTheme('light', false);

        // Verificar disponibilidad de librerías gráficas
        const libsMissing = [];
        if (typeof echarts === 'undefined') libsMissing.push('echarts');
        if (typeof LightweightCharts === 'undefined') libsMissing.push('lightweight-charts');
        if (libsMissing.length) {
            console.error('Librerías gráficas faltantes:', libsMissing.join(', '));
            const container = document.querySelector('.main-content') || document.body;
            const warn = document.createElement('div');
            warn.className = 'alert alert-warning fw-bold';
            warn.innerText = 'Atención: faltan librerías gráficas en el cliente: ' + libsMissing.join(', ') + '. Revisa la consola del navegador.';
            container.prepend(warn);
        } else {
            
        }

        // Limpiar caché antigua
        localStorage.removeItem('gridbot_vip_last_update');

        
        const res = await fetch('/api/status');
        
        if (!res.ok) {
            console.error("❌ Error fetching status:", res.status);
            return;
        }
        const data = await res.json();
        
        if (data.active_pairs) {
            
            syncTabs(data.active_pairs);
        }
        
        // Registrar snapshot de balance cada 30 segundos para historial de gráficas
        setInterval(recordBalanceSnapshot, 30000);
        
        
        loadHome();
    } catch (e) { console.error("❌ Error init:", e); }
}

function syncTabs(activePairs) {
    if (!activePairs) return;
    const tabList = document.getElementById('mainTabs');
    const safeSymbols = activePairs.map(s => s.replace('/', '_'));
    const existingTabs = Array.from(tabList.querySelectorAll('li.nav-item button.nav-link'));
    existingTabs.forEach(btn => {
        const targetId = btn.getAttribute('data-bs-target').replace('#content-', '');
        // Permitimos también la pestaña 'dashboard' que es la nueva vista principal
        if (!['home', 'config', 'wallet', 'dashboard'].includes(targetId) && !safeSymbols.includes(targetId)) {
            btn.parentElement.remove();
            const contentDiv = document.getElementById(`content-${targetId}`);
            if (contentDiv) contentDiv.remove();
        }
    });
    activePairs.forEach(sym => ensureTabExists(sym));
}

function ensureTabExists(symbol) {
    const safe = symbol.replace('/', '_');
    if (document.getElementById(`content-${safe}`)) return;
    
    const baseCoin = symbol.split('/')[0].toLowerCase();
    const iconUrl = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/128/color/${baseCoin}.png`;

    const tabList = document.getElementById('mainTabs');
    
    const li = document.createElement('li');
    li.className = 'nav-item';
    
    li.innerHTML = `
        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#content-${safe}" type="button" onclick="setMode('${symbol}')">
            <img src="${iconUrl}" class="coin-icon" id="coin-icon-${safe}">
            <i class="fa-brands fa-bitcoin coin-fallback d-none" id="coin-fallback-${safe}"></i>
            <span>${symbol}</span>
        </button>`;
    
    // Agregar manejador de error para la imagen
    const img = li.querySelector(`#coin-icon-${safe}`);
    img.addEventListener('error', function() {
        this.classList.add('d-none');
        document.getElementById(`coin-fallback-${safe}`).classList.remove('d-none');
    });
    
    tabList.appendChild(li);

    const btnCandlesActive = currentChartType === 'candles' ? 'active' : '';
    const btnLineActive = currentChartType === 'line' ? 'active' : '';

    const div = document.createElement('div');
    div.className = 'tab-pane fade';
    div.id = `content-${safe}`;
    div.innerHTML = `
        <div class="row">
            <div class="col-lg-8 mb-3">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            <span class="d-none d-sm-inline me-2">Gráfico</span>
                            <div class="btn-group me-2 tf-controls">
                                <button class="btn btn-outline-secondary btn-sm tf-btn" onclick="setTimeframe('1m')">1m</button>
                                <button class="btn btn-outline-secondary btn-sm tf-btn" onclick="setTimeframe('5m')">5m</button>
                                <button class="btn btn-outline-secondary btn-sm tf-btn active" onclick="setTimeframe('15m')">15m</button>
                                <button class="btn btn-outline-secondary btn-sm tf-btn" onclick="setTimeframe('1h')">1h</button>
                                <button class="btn btn-outline-secondary btn-sm tf-btn" onclick="setTimeframe('4h')">4h</button>
                            </div>
                            <div class="btn-group">
                                <button class="btn btn-outline-secondary btn-sm ${btnCandlesActive}" data-chart-type="candles" onclick="setChartType('candles')" title="Velas"><i class="fa-solid fa-chart-simple"></i></button>
                                <button class="btn btn-outline-secondary btn-sm ${btnLineActive}" data-chart-type="line" onclick="setChartType('line')" title="Línea"><i class="fa-solid fa-chart-line"></i></button>
                            </div>
                            <button class="btn btn-outline-secondary btn-sm ms-2" onclick="resetZoom('${symbol}')" title="Reset Zoom"><i class="fa-solid fa-compress"></i></button>
                        </div>
                        <div class="d-flex align-items-center">
                            <div class="btn-group btn-group-sm me-3">
                                <button class="btn btn-outline-danger" onclick="resetCoinSession('${symbol}')" title="Reset Sesión">Rst. Sesión</button>
                                <button class="btn btn-outline-danger" onclick="resetCoinGlobal('${symbol}')" title="Reset Global">Rst. Global</button>
                            </div>
                            <span class="fs-5 fw-bold text-primary" id="price-${safe}">--</span>
                        </div>
                    </div>
                    <div class="card-body p-1"><div id="chart-${safe}" class="chart-container"></div></div>
                </div>
            </div>
            <div class="col-lg-4 mb-3">
                <div class="card h-100">
                    <div class="card-header">Estado Grid</div>
                    <div class="card-body">
                        <div class="row g-2 text-center mb-4">
                            <div class="col-6"><div class="bg-buy p-3 rounded"><small class="d-block fw-bold mb-1">COMPRAS</small><b class="fs-3" id="count-buy-${safe}">0</b></div></div>
                            <div class="col-6"><div class="bg-sell p-3 rounded"><small class="d-block fw-bold mb-1">VENTAS</small><b class="fs-3" id="count-sell-${safe}">0</b></div></div>
                        </div>
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item d-flex justify-content-between align-items-center mt-3 bg-light">
                                <strong>Balance Sesión</strong>
                                <div class="d-flex align-items-center gap-2">
                                    <b id="sess-pnl-${safe}">--</b>
                                    <button class="btn btn-xs btn-outline-danger" onclick="resetCoinSession('${symbol}')"><i class="fa-solid fa-rotate-right"></i></button>
                                </div>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center bg-light">
                                <strong>Balance Global</strong>
                                <div class="d-flex align-items-center gap-2">
                                    <b id="glob-pnl-${safe}">--</b>
                                    <button class="btn btn-xs btn-outline-danger" onclick="resetCoinGlobal('${symbol}')"><i class="fa-solid fa-trash-can"></i></button>
                                </div>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6 mb-3"><div class="card h-100"><div class="card-header">Órdenes</div><div class="card-body p-0 table-responsive" style="max-height:300px"><table class="table table-custom table-striped mb-0"><thead class="table-light"><tr><th>Tipo</th><th>Precio</th><th>Vol</th></tr></thead><tbody id="orders-${safe}"></tbody></table></div></div></div>
            <div class="col-md-6 mb-3">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Historial</span>
                        <button class="btn btn-sm btn-outline-secondary" onclick="clearHistory('${symbol}')"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                    <div class="card-body p-0 table-responsive" style="max-height:300px"><table class="table table-custom table-hover mb-0"><thead class="table-light"><tr><th>ID</th><th>Hora</th><th>Op</th><th>Precio</th><th>Total</th></tr></thead><tbody id="trades-${safe}"></tbody></table></div>
                </div>
            </div>
        </div>`;
    document.getElementById('mainTabsContent').appendChild(div);
}

function setMode(m) {
    currentMode = m; dataCache = {};
    if(m==='home') loadHome();
    else if(m==='wallet') loadWallet();
    else if(m!=='config') loadSymbol(m);
}

// --- ACCIONES ---

function setTimeframe(tf) {
    currentTimeframe = tf;
    document.querySelectorAll('.tf-btn').forEach(b => { b.classList.remove('active'); if(b.innerText.toLowerCase()===tf) b.classList.add('active'); });
    if(currentMode !== 'home' && currentMode !== 'config' && currentMode !== 'wallet') {
        const safe = currentMode.replace('/', '_');
        destroyChart(safe); 
        loadSymbol(currentMode);
    }
}

function setChartType(type) {
    currentChartType = type;
    document.querySelectorAll('button[data-chart-type]').forEach(btn => {
        btn.classList.remove('active');
        if(btn.getAttribute('data-chart-type') === type) {
            btn.classList.add('active');
        }
    });
    if(currentMode!=='home' && currentMode!=='config' && currentMode!=='wallet') {
        const safe = currentMode.replace('/', '_');
        destroyChart(safe);
        loadSymbol(currentMode);
    }
}

function resetZoom(symbol) {
    const safe = symbol.replace('/', '_');
    resetChartZoom(safe); 
    loadSymbol(symbol); 
}

async function recordBalanceSnapshot() {
    /**Registra un snapshot del balance para generar historial de gráficas*/
    try {
        const res = await fetch('/api/record_balance', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            // Recargar gráficas después de registrar
            loadBalanceCharts();
        }
    } catch (e) {
        // Silencioso - esto se ejecuta en background
    }
}

function filterHistory(hours) {
    if (!fullGlobalHistory || fullGlobalHistory.length === 0) return;

    let filteredData = [];
    if (hours === 'all') {
        filteredData = fullGlobalHistory;
    } else {
        const now = Date.now();
        const cutoff = now - (hours * 3600 * 1000);
        filteredData = fullGlobalHistory.filter(d => d[0] >= cutoff);
    }

    renderLineChart('balanceChartGlobal', filteredData, '#3b82f6');
    // Actualizamos también el histórico del espacio 1 usando ECharts
    renderEChart('balanceChartHistory', filteredData, '#3b82f6', 'Balance total');
    // Actualizamos también el histórico del espacio 1
    renderLineChart('balanceChartHistory', filteredData, '#3b82f6');
}

async function loadTopStrategies() {
    /**Carga y muestra el ranking de operaciones grid trading*/
    try {
        const res = await fetch('/api/top_strategies');
        const data = await res.json();
        const container = document.getElementById('top-strategies-container');
        
        if (!container) return;
        
        if (!data.strategies || data.strategies.length === 0) {
            container.innerHTML = '<p class="text-muted text-center small py-5">Sin operaciones registradas aún</p>';
            return;
        }
        
        container.innerHTML = data.strategies.map((s, idx) => {
            const pnlClass = s.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            const pnlSign = s.pnl >= 0 ? '+' : '';
            const roiClass = s.roi_annualized >= 0 ? 'text-success' : 'text-danger';
            
            return `
                <div class="strategy-item">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div style="display: flex; align-items: center;">
                            <div class="strategy-rank">${idx + 1}</div>
                            <div>
                                <div class="strategy-symbol">${s.symbol}</div>
                                <div class="strategy-roi ${roiClass}">ROI: ${s.roi_annualized.toFixed(1)}% anual</div>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div class="${pnlClass} fw-bold">${pnlSign}$${Math.abs(s.pnl).toFixed(2)}</div>
                        </div>
                    </div>
                    <div class="strategy-metrics">
                        <div class="strategy-metric">
                            <span class="strategy-metric-label">Capital:</span>
                            <span class="strategy-metric-value">$${s.capital_invested.toFixed(0)}</span>
                        </div>
                        <div class="strategy-metric">
                            <span class="strategy-metric-label">ROI:</span>
                            <span class="strategy-metric-value">${s.roi_percent.toFixed(1)}%</span>
                        </div>
                        <div class="strategy-metric">
                            <span class="strategy-metric-label">Trades:</span>
                            <span class="strategy-metric-value">${s.trades}</span>
                        </div>
                        <div class="strategy-metric">
                            <span class="strategy-metric-label">Días:</span>
                            <span class="strategy-metric-value">${s.days_active.toFixed(0)}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Error loading top strategies:", e);
    }
}

// --- NOU: GESTIÓ D'INGRESSOS I RETIRADES ---
async function openCapitalAdjustment() {
    const { value: formValues } = await Swal.fire({
        title: 'Gestió de Capital',
        html:
            '<p class="small text-muted">Registra ingressos o retirades per no afectar al càlcul de beneficis (PnL).</p>' +
            '<input id="swal-asset" class="swal2-input" placeholder="Actiu (ex: USDC)" value="USDC">' +
            '<input id="swal-amount" type="number" step="any" class="swal2-input" placeholder="Quantitat (+ Ingrés / - Retirada)">',
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Registrar',
        cancelButtonText: 'Cancel·lar',
        preConfirm: () => {
            return [
                document.getElementById('swal-asset').value,
                document.getElementById('swal-amount').value
            ]
        }
    });

    if (formValues) {
        const asset = formValues[0];
        const amount = parseFloat(formValues[1]);
        
        if (!asset || isNaN(amount)) {
            Swal.fire('Error', 'Dades invàlides', 'error');
            return;
        }

        try {
            const res = await fetch('/api/balance/adjust', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ asset: asset, amount: amount })
            });
            const data = await res.json();
            
            if (res.ok) {
                Swal.fire('Registrat', data.message, 'success');
                loadHome(); // Recarreguem per veure canvis
            } else {
                Swal.fire('Error', data.detail, 'error');
            }
        } catch (e) {
            Swal.fire('Error', 'Error de connexió', 'error');
        }
    }
}

// --- WALLET ---
async function loadHome() {
    try {
        
        const res = await fetch('/api/status');
        
        if (!res.ok) {
            console.error("❌ Error fetching status:", res.status);
            return;
        }
        const data = await res.json();
        
        if (data.active_pairs) syncTabs(data.active_pairs);
        
        let engineBtn = document.getElementById('btn-engine-toggle');
        if (engineBtn) engineBtn.remove(); 
        
        const isStopped = data.status === 'Stopped';
        document.querySelectorAll('.tf-controls').forEach(el => { 
            if (isStopped) {
                el.classList.add('d-none');
            } else {
                el.classList.remove('d-none');
            }
        });

        updateColorValue('dash-profit-session', data.stats.session.profit, ' $');
        updateColorValue('dash-profit-total', data.stats.global.profit, ' $');

        const tradesSessionEl = document.getElementById('dash-trades-session');
        if (tradesSessionEl) tradesSessionEl.innerText = fmtInt(data.stats.session.trades);

        const coinSessionEl = document.getElementById('dash-coin-session');
        if (coinSessionEl) coinSessionEl.innerText = data.stats.session.best_coin;

        const uptimeSessionEl = document.getElementById('dash-uptime-session');
        if (uptimeSessionEl) uptimeSessionEl.innerText = data.stats.session.uptime;

        const tradesTotalEl = document.getElementById('dash-trades-total');
        if (tradesTotalEl) tradesTotalEl.innerText = fmtInt(data.stats.global.trades);

        const coinTotalEl = document.getElementById('dash-coin-total');
        if (coinTotalEl) coinTotalEl.innerText = data.stats.global.best_coin;

        const uptimeTotalEl = document.getElementById('dash-uptime-total');
        if (uptimeTotalEl) uptimeTotalEl.innerText = data.stats.global.uptime;

        renderDonut('pieChart', data.portfolio_distribution, true);
        renderDonut('sessionTradesChart', data.session_trades_distribution, false);
        renderDonut('globalTradesChart', data.global_trades_distribution, false);
        
        // Rellenar tarjetas del nuevo Dashboard (si existen)
        const elStatus = document.getElementById('summary-status');
        const serviceOnline = data.service === 'online';
        const uptimeSec = data.stats?.session?.uptime_seconds ?? null;

        if (elStatus) {
            const status = String(data.status || '--');
            let statusClass = 'offline';
            let label = status;
            if (serviceOnline) { statusClass = 'running'; label = 'running'; }
            else if (status === 'Running') { statusClass = 'running'; label = 'running'; }
            else if (status === 'Paused') { statusClass = 'paused'; label = 'paused'; }
            else if (status === 'Stopped') { statusClass = 'stopped'; label = 'stopped'; }
            else if (status === 'Offline') { statusClass = 'offline'; label = 'offline'; }

            elStatus.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="dashboard-status-text">${label}</div>
                    <span class="status-dot ${statusClass}"></span>
                </div>
                <div id="summary-uptime" class="dashboard-status-uptime">Uptime: --</div>
            `;

            const elUp = document.getElementById('summary-uptime');

            // Si el servicio está online, mostramos uptime con formato HH:MM o DD:HH y actualizamos cada 3 minutos
            if (serviceOnline && uptimeSec !== null) {
                // Solo reiniciamos el intervalo si ha habido un cambio significativo o cambio de estado
                const needReset = (sessionOnlineState !== true) || (sessionUptimeBase === null) || (Math.abs(uptimeSec - sessionUptimeBase) > 120);
                if (needReset) {
                    if (sessionUptimeInterval) { clearInterval(sessionUptimeInterval); sessionUptimeInterval = null; }
                    sessionUptimeBase = uptimeSec;
                    if (elUp) elUp.innerText = `Uptime: ${formatServiceUptime(sessionUptimeBase)}`;
                    // Actualizar cada 3 minutos
                    sessionUptimeInterval = setInterval(() => {
                        sessionUptimeBase += 180; // 3 minutos
                        const e = document.getElementById('summary-uptime');
                        if (e) e.innerText = `Uptime: ${formatServiceUptime(sessionUptimeBase)}`;
                    }, 180000);
                } else {
                    // Actualizamos visualmente con el valor exacto proporcionado por el servidor
                    sessionUptimeBase = uptimeSec;
                    if (elUp) elUp.innerText = `Uptime: ${formatServiceUptime(sessionUptimeBase)}`;
                }
                sessionOnlineState = true;
            } else {
                // Si no está online, limpiamos intervalos y mostramos el texto legacy
                if (sessionUptimeInterval) { clearInterval(sessionUptimeInterval); sessionUptimeInterval = null; }
                sessionUptimeBase = null;
                sessionOnlineState = false;
                if (elUp) elUp.innerText = `Uptime: ${data.stats?.session?.uptime || '--'}`;
            }
        }

        const elBalance = document.getElementById('summary-balance');
        if (elBalance) elBalance.innerText = `${fmtUSDC(data.total_usdc_value)} US$`;

        // PnL sesión (colorizado si procede)
        updateColorValue('summary-pnl-session', data.stats?.session?.profit || 0, ' $');

        // PnL grid (suma de strategies) - usar updateColorValue para colorear según signo
        const totalGridPnl = (data.strategies || []).reduce((acc, s) => acc + (s.total_pnl || 0), 0);
        updateColorValue('summary-pnl-grid', totalGridPnl, ' $');

        // Operaciones totales (suma de trades de todas las estrategias)
        const totalOperations = (data.strategies || []).reduce((acc, s) => acc + (s.total_trades || 0), 0);
        const elTotalOps = document.getElementById('summary-total-operations');
        if (elTotalOps) elTotalOps.innerText = totalOperations.toString();
        
        const available = data.balance_usdc || 0;
        const orders = Math.max((data.total_usdc_value || 0) - available, 0);
        const elBalAvailable = document.getElementById('bal-available');
        const elBalOrders = document.getElementById('bal-orders');
        if (elBalAvailable) elBalAvailable.innerText = `${fmtUSDC(available)} US$`;
        if (elBalOrders) elBalOrders.innerText = `${fmtUSDC(orders)} US$`;

        loadBalanceCharts();
        loadGlobalOrders();

        const stTable = document.getElementById('strategies-table-body');
        if(stTable) {
            stTable.innerHTML = data.strategies.map(s => {
                const safe = s.symbol.replace('/', '_');
                return `<tr><td class="fw-bold">${s.symbol}</td><td><span class="badge bg-success bg-opacity-25 text-success">Activo</span></td><td><small>${s.grids} Líneas @ ${s.amount}$ (${s.spread}%)</small></td><td class="fw-bold">${s.total_trades}</td><td class="${s.total_pnl>=0?'text-success':'text-danger'} fw-bold">${fmtUSDC(s.total_pnl)} $</td><td class="${s.session_pnl>=0?'text-success':'text-danger'} fw-bold">${fmtUSDC(s.session_pnl)} $</td><td class="text-end"><button class="btn btn-sm btn-outline-primary" onclick="document.querySelector('[data-bs-target=\\'#content-${safe}\\']').click()"><i class="fa-solid fa-chart-line"></i></button></td></tr>`;
            }).join('');
        }
    } catch(e) { console.error(e); }
    
    // Cargar ranking de operaciones
    loadTopStrategies();
}

// --- FUNCIONES CONTROL SISTEMA ---
function formatUptimeSeconds(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${mins}m`;
    return `${hours}h ${mins}m`;
}

function pad2(n){ return n < 10 ? '0'+n : ''+n; }

function formatServiceUptime(seconds){
    seconds = Math.max(0, Math.floor(seconds));
    if (seconds < 86400){
        const hh = Math.floor(seconds / 3600);
        const mm = Math.floor((seconds % 3600) / 60);
        return `${pad2(hh)}:${pad2(mm)}`; // HH:MM
    } else {
        const dd = Math.floor(seconds / 86400);
        const hh = Math.floor((seconds % 86400) / 3600);
        return `${dd}d:${pad2(hh)}h`; // DD:HH
    }
}

async function loadSymbol(symbol) {
    const safe = symbol.replace('/', '_');
    try {
        const res = await fetch(`/api/details/${symbol}?timeframe=${currentTimeframe}&_=${Date.now()}`);
        if (!res.ok) {
            console.error(`Error fetchin /api/details/${symbol}:`, res.status);
            return;
        }
        const data = await res.json();
        
        // Validar que los datos existan y sean válidos
        if (!data || !data.chart_data) {
            console.warn(`No hay chart_data para ${symbol}`);
            const chartDom = document.getElementById(`chart-${safe}`);
            if (chartDom) chartDom.innerHTML = '<div class="empty-chart text-center text-muted" style="padding:40px 10px">Sin datos disponibles</div>';
            return;
        }
        
        
        
        document.getElementById(`price-${safe}`).innerText = `${fmtPrice(data.price)} USDC`;
        
        renderCandleChart(safe, data.chart_data, data.grid_lines || [], data.open_orders || [], currentChartType);
        
        document.getElementById(`count-buy-${safe}`).innerText = data.open_orders.filter(o => o.side === 'buy').length;
        document.getElementById(`count-sell-${safe}`).innerText = data.open_orders.filter(o => o.side === 'sell').length;
        updateColorValue(`sess-pnl-${safe}`, data.session_pnl, ' $');
        updateColorValue(`glob-pnl-${safe}`, data.global_pnl, ' $');
        
        const allOrders = [...data.open_orders].sort((a,b) => b.price - a.price);
        document.getElementById(`orders-${safe}`).innerHTML = allOrders.map(o => `<tr><td><b class="${o.side=='buy'?'text-buy':'text-sell'}">${o.side.toUpperCase()}</b></td><td>${fmtPrice(o.price)}</td><td>${fmtCrypto(o.amount)}</td></tr>`).join('');
        
        document.getElementById(`trades-${safe}`).innerHTML = data.trades.map(t => {
            let idBadge = t.buy_id || '-';
            if(t.side === 'sell' && t.buy_id) idBadge = '⮑ ' + t.buy_id; 
            return `<tr><td><span class="badge bg-secondary">${idBadge}</span></td><td>${new Date(t.timestamp).toLocaleTimeString()}</td><td><span class="badge ${t.side=='buy'?'bg-buy':'bg-sell'}">${t.side.toUpperCase()}</span></td><td>${fmtPrice(t.price)}</td><td>${fmtUSDC(t.cost)}</td></tr>`;
        }).join('');

// --- MANTENIMIENTO ---
    } catch(e) { console.error(`Error en loadSymbol(${symbol}):`, e); }
}

async function loadWallet() { 
    // --- LÒGICA D'ACTUALITZACIÓ INFO COMPTE ---
    // Forcem la visibilitat inicial per assegurar que es veu alguna cosa
    const badgeContainer = document.getElementById('account-info-badge');
    if(badgeContainer && badgeContainer.classList.contains('d-none')) {
        badgeContainer.classList.remove('d-none');
        document.getElementById('acc-tier').innerText = 'Cargando...';
        document.getElementById('acc-fees').innerText = '...';
    }

    // Cridem de forma asíncrona (no bloqueja la taula)
    fetchAccountInfo();

    const tbody = document.getElementById('wallet-table-body'); 
    if(!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>'; 
    try { 
        const res = await fetch('/api/wallet'); 
        const data = await res.json(); 
        if(data.length===0) { tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Sin activos</td></tr>'; return; } 
        tbody.innerHTML = data.map(item => { 
            const freeVal = item.free * item.price; 
            const lockedVal = item.locked * item.price; 
            let btn = (item.asset!=='USDC' && item.asset!=='USDT') ? `<button class="btn btn-sm btn-outline-danger" onclick="liquidateAsset('${item.asset}')">Vender</button>` : '<span class="text-muted small">Base</span>'; 
            return `<tr><td class="fw-bold">${item.asset}</td><td>${fmtCrypto(item.free)} <small class="text-muted">(${fmtUSDC(freeVal)}$)</small></td><td class="${item.locked>0?'text-danger':''}">${fmtCrypto(item.locked)} <small class="text-muted">(${fmtUSDC(lockedVal)}$)</small></td><td>${fmtCrypto(item.total)}</td><td class="fw-bold">${fmtUSDC(item.usdc_value)}$</td><td class="text-end">${btn}</td></tr>`; 
        }).join(''); 
    } catch(e) { 
        if(tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error cargando cartera</td></tr>'; 
    } 
}

async function fetchAccountInfo() {
    try {
        const resInfo = await fetch('/api/account/info');
        if(resInfo.ok) {
            const info = await resInfo.json();
            // Guardem a localStorage (per si un cas)
            localStorage.setItem('gridbot_vip_info', JSON.stringify(info));
            localStorage.setItem('gridbot_vip_last_update', Date.now().toString());
            updateAccountBadge(info);
        } else {
            console.warn("API Account Info Error");
            // Si falla, mostrem N/A però mantenim visible
            updateAccountBadge({ tier: 'N/A', maker: 0, taker: 0 });
        }
    } catch(e) { 
        console.error("Error loading account info", e);
        updateAccountBadge({ tier: 'Error', maker: 0, taker: 0 });
    }
}

function updateAccountBadge(info) {
    const tierBadge = document.getElementById('acc-tier');
    const feesBadge = document.getElementById('acc-fees');
    const badgeContainer = document.getElementById('account-info-badge');
    
    if (tierBadge && feesBadge && info) {
        tierBadge.innerText = info.tier || 'N/A';
        const maker = info.maker !== undefined ? info.maker.toFixed(3) : '--';
        const taker = info.taker !== undefined ? info.taker.toFixed(3) : '--';
        feesBadge.innerText = `Maker: ${maker}% | Taker: ${taker}%`;
        badgeContainer.classList.remove('d-none');
    }
}

async function loadGlobalOrders() { try { const res = await fetch('/api/orders'); const orders = await res.json(); const tbody = document.getElementById('global-orders-table'); if(orders.length === 0) { tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3">No hay órdenes</td></tr>'; return; } orders.sort((a,b) => a.symbol.localeCompare(b.symbol) || b.price - a.price); tbody.innerHTML = orders.map(o => { const isBuy = o.side === 'buy'; let pnlDisplay = '-', pnlClass = ''; if(!isBuy && o.entry_price > 0) { const pnl = ((o.current_price - o.entry_price)/o.entry_price)*100; pnlDisplay = fmtPct(pnl); pnlClass = pnl>=0 ? 'text-success fw-bold':'text-danger fw-bold'; } return `<tr><td class="fw-bold">${o.symbol}</td><td><span class="badge ${isBuy?'bg-success':'bg-danger'}">${isBuy?'COMPRA':'VENTA'}</span></td><td>${fmtPrice(o.price)}</td><td class="text-muted">${isBuy?'-':fmtPrice(o.entry_price)}</td><td>${fmtPrice(o.current_price)}</td><td class="${pnlClass}">${pnlDisplay}</td><td>${fmtUSDC(o.total_value)}</td><td class="text-end"><button class="btn btn-sm btn-outline-secondary" onclick="closeOrder('${o.symbol}','${o.id}','${o.side}',${o.amount})"><i class="fa-solid fa-times"></i></button></td></tr>`; }).join(''); } catch(e) {} }
async function loadBalanceCharts() { 
    try { 
        
        const res = await fetch('/api/history/balance'); 
        
        if (!res.ok) {
            console.error("❌ Error fetching balance history:", res.status);
            return;
        }
        const data = await res.json(); 
        
        // Aplicar filtro de pikes: ignorar variaciones >30% en <1 minuto
        fullGlobalHistory = filterBalancePikes(data.global); 
        
        // Solo renderizar con ECharts (mucho mejor control de escala)
        renderEChart('balanceChartSession', data.session, '#0ecb81', 'Balance Sesión');
        renderEChart('balanceChartHistory', fullGlobalHistory, '#3b82f6', 'Balance Total');
        renderEChart('balanceChartGlobal', fullGlobalHistory, '#3b82f6', 'Balance Global');
        
        
    } catch(e) { 
        console.error("❌ Error loading charts:", e); 
    } 
}
async function closeOrder(s, i, side, a) { const result = await Swal.fire({ title: '¿Cancelar Orden?', text: `${side.toUpperCase()} ${s} - Cantidad: ${a}`, icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', cancelButtonColor: '#3085d6', confirmButtonText: 'Sí, cancelar' }); if (result.isConfirmed) { postAction('/api/close_order', { symbol: s, order_id: i, side: side, amount: a }); } }
async function liquidateAsset(a) { const result = await Swal.fire({ title: `¿Liquidar ${a}?`, text: "Se cancelarán las órdenes y se venderá todo a mercado.", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Sí, vender todo' }); if (result.isConfirmed) { postAction('/api/liquidate_asset', { asset: a }, loadWallet); } }
async function clearHistory(s) { const result = await Swal.fire({ title: '¿Borrar Historial?', text: `Se eliminarán los trades antiguos de ${s} de la base de datos.`, icon: 'question', showCancelButton: true, confirmButtonText: 'Sí, borrar' }); if (result.isConfirmed) { postAction('/api/history/clear', { symbol: s }); } }
async function resetStatistics() { const result = await Swal.fire({ title: '¿RESET TOTAL?', text: "ESTO ES IRREVERSIBLE. Borrará todo el historial y gráficas.", icon: 'error', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Sí, reiniciar todo' }); if (result.isConfirmed) { postAction('/api/reset_stats', {}, () => location.reload()); } }

// --- FUNCIONES MODIFICADAS PARA ESPERAR CAMBIO DE ESTADO ---
async function panicStop() { 
    const result = await Swal.fire({ title: '¿Pausar Operaciones?', text: "El bot dejará de analizar el mercado.", icon: 'warning', showCancelButton: true, confirmButtonText: 'Pausar' }); 
    if (result.isConfirmed) executeEngineAction('/api/panic/stop', 'Pausando...', 'Paused'); 
}
async function panicStart() { 
    executeEngineAction('/api/panic/start', 'Reanudando...', 'Running');
}
async function startEngine() { 
    const result = await Swal.fire({ title: '¿Arrancar Motor?', text: "Iniciará la operativa automática.", icon: 'question', showCancelButton: true, confirmButtonText: 'Arrancar' }); 
    if (result.isConfirmed) executeEngineAction('/api/engine/on', 'Iniciando Motor...', 'Running'); 
}
async function stopEngine() { 
    const result = await Swal.fire({ title: '¿Detener Motor?', text: "Se detendrá el análisis de mercado.", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Detener' }); 
    if (result.isConfirmed) executeEngineAction('/api/engine/off', 'Deteniendo Motor...', 'Stopped'); 
}
// ----------------------------------------------------------

async function panicCancel() { const result = await Swal.fire({ title: '¿CANCELAR TODO?', text: "Se borrarán todas las órdenes del Exchange.", icon: 'error', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Sí, cancelar todo' }); if (result.isConfirmed) postAction('/api/panic/cancel_all'); }
async function panicSell() { const result = await Swal.fire({ title: '¿VENDER TODO?', text: "PELIGRO: Se venderán todas las posiciones a mercado.", icon: 'error', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Sí, vender todo' }); if (result.isConfirmed) postAction('/api/panic/sell_all'); }
async function resetGlobalChart() { const result = await Swal.fire({ title: '¿Borrar Gráfica Global?', text: "Se eliminará el historial visual del balance.", icon: 'question', showCancelButton: true, confirmButtonText: 'Borrar' }); if (result.isConfirmed) postAction('/api/reset/chart/global'); }
async function resetSessionChart() { const result = await Swal.fire({ title: '¿Reiniciar Sesión?', text: "Se reiniciará la gráfica de sesión y el contador de PnL de sesión.", icon: 'question', showCancelButton: true, confirmButtonText: 'Reiniciar' }); if (result.isConfirmed) postAction('/api/reset/chart/session'); }
async function resetGlobalPnL() { const result = await Swal.fire({ title: '¿Borrar Historial PnL?', text: "Se eliminarán todos los registros de trades pasados.", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Borrar' }); if (result.isConfirmed) postAction('/api/reset/pnl/global'); }
async function refreshOrders() { postAction('/api/refresh_orders'); }
async function resetCoinSession(symbol) { const result = await Swal.fire({ title: `¿Reiniciar Sesión ${symbol}?`, text: "Solo afectará al contador de esta moneda.", icon: 'question', showCancelButton: true, confirmButtonText: 'Reiniciar' }); if (result.isConfirmed) postAction('/api/reset/coin/session', { symbol: symbol }); }
async function resetCoinGlobal(symbol) { const result = await Swal.fire({ title: `¿Borrar Historial ${symbol}?`, text: "Se eliminarán los trades antiguos de esta moneda.", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', confirmButtonText: 'Borrar' }); if (result.isConfirmed) postAction('/api/reset/coin/global', { symbol: symbol }); }

async function postAction(url, body={}, cb=null) { try { const res = await fetch(url, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) }); const d = await res.json(); if(res.ok) { if(cb) await cb(); else { dataCache={}; await loadHome(); } Swal.fire({title:'Éxito', text:d.message, icon:'success', timer:1500, showConfirmButton:false}); } else Swal.fire('Error', d.detail, 'error'); } catch(e) { Swal.fire('Error', 'Conexión', 'error'); } }

// --- NUEVA LÓGICA DE ESPERA ACTIVA (POLLING DE ESTADO) ---
async function executeEngineAction(url, actionTitle, targetStatus) {
    // 1. Mostrar Loading (Sin botón de cerrar)
    Swal.fire({
        title: actionTitle,
        html: 'Esperando cambio de estado...<br><i class="fa-solid fa-spinner fa-spin fa-2x mt-3"></i>',
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false
    });

    try {
        // 2. Ejecutar Acción
        const res = await fetch(url, { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: '{}' 
        });
        const d = await res.json();

        if (!res.ok) {
            Swal.fire('Error', d.detail || 'Error en la petición', 'error');
            return;
        }

        // 3. Polling hasta confirmar estado en /api/status
        let attempts = 0;
        const maxAttempts = 15; // 15 intentos (aprox 20s)
        let finished = false; // Bandera para evitar múltiples alertas
        
        // Intervalo aumentado de 1.5s a 2.5s para no saturar
        const checkInterval = setInterval(async () => {
            if (finished) { clearInterval(checkInterval); return; } // Doble seguridad
            
            attempts++;
            try {
                // Consultamos estado silenciosamente
                const sRes = await fetch('/api/status');
                const sData = await sRes.json();
                
                // Si el estado ya coincide con el objetivo (Running/Stopped/Paused)
                if (sData.status === targetStatus) {
                    finished = true;
                    clearInterval(checkInterval);
                    
                    // Recargamos la UI completa ahora que sabemos que ha cambiado
                    await loadHome();
                    
                    Swal.fire({
                        title: 'Operación Finalizada',
                        text: `El sistema está: ${targetStatus.toUpperCase()}`,
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false
                    });
                } else if (attempts >= maxAttempts) {
                    finished = true;
                    clearInterval(checkInterval);
                    
                    // Timeout
                    Swal.fire({
                        title: 'Tiempo de espera agotado',
                        text: 'El estado no se ha actualizado a tiempo, revisa los logs.',
                        icon: 'warning'
                    });
                }
            } catch(e) {
                console.error("Polling error", e);
            }
        }, 2500); // Check cada 2.5s (más lento para evitar BAN)

    } catch (e) {
        Swal.fire('Error', 'Error de conexión', 'error');
    }
}

function changeTheme(themeName, reloadData = true) {
    // Tema unificado: siempre usamos el único CSS consolidado
    const link = document.getElementById('theme-stylesheet');
    link.href = "/static/css/style.css";
    localStorage.setItem('gridbot_theme', 'light');

    if (reloadData) {
        setTimeout(() => {
            if (currentMode === 'home') loadHome();
            else if (currentMode !== 'config' && currentMode !== 'wallet') loadSymbol(currentMode);
        }, 100);
    }
}

// Loop principal
init();
setInterval(() => {
    if(currentMode === 'home') { loadHome(); } 
    else if(currentMode !== 'config' && currentMode !== 'wallet') loadSymbol(currentMode);
}, 4000);