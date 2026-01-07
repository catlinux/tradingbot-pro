// Archivo: gridbot_binance/web/static/js/config.js
import { fmtUSDC } from './utils.js';

let currentConfigObj = null;
let strategyCache = {};
let rsiTimeframeCache = {};

export async function loadConfigForm() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        currentConfigObj = JSON5.parse(data.content);
        
        const sysCycle = document.getElementById('sys-cycle');
        if (sysCycle) sysCycle.value = currentConfigObj.system.cycle_delay;
        
        if (document.getElementById('sys-testnet')) {
            const isTest = currentConfigObj.system.use_testnet !== undefined ? currentConfigObj.system.use_testnet : true;
            document.getElementById('sys-testnet').checked = isTest;
        }

        if (document.getElementById('sys-telegram')) {
            const isTg = currentConfigObj.system.telegram_enabled !== undefined ? currentConfigObj.system.telegram_enabled : true;
            document.getElementById('sys-telegram').checked = isTg;
        }

        const container = document.getElementById('coins-config-container');
        if (!container) return;
        
        container.innerHTML = '';
        currentConfigObj.pairs.forEach((pair, index) => {
            const strategy = pair.strategy || currentConfigObj.default_strategy;
            const isEnabled = pair.enabled;
            // Cambio: Unificamos a 'card-disabled' por compatibilidad con CSS oscuro
            const cardClass = isEnabled ? '' : 'card-disabled'; 
            const checked = isEnabled ? 'checked' : '';
            
            const startMode = strategy.start_mode || 'wait';
            const profile = strategy.strategy_profile || 'manual';
            const trailing = strategy.trailing_enabled === true; 
            
            // ESTRUCTURA HTML ORIGINAL RESTAURADA
            const html = `
                <div class="col-md-6 col-xl-4 mb-4">
                    <div class="card h-100 coin-card ${cardClass}" id="card-pair-${index}">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <span class="fw-bold fs-5">${pair.symbol}</span>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" role="switch" id="enable-${index}" ${checked} onchange="toggleCard(${index})">
                                <label class="form-check-label fw-bold" for="enable-${index}" id="lbl-${index}">${isEnabled ? 'ON' : 'OFF'}</label>
                            </div>
                        </div>
                        
                        <div class="card-body">
                            <div class="mb-3 p-2 bg-light border rounded text-center" id="rsi-box-${index}">
                                <div class="spinner-border spinner-border-sm text-secondary" role="status"></div>
                                <small class="ms-2">Cargando RSI...</small>
                            </div>
                            <input type="hidden" id="profile-${index}" value="${profile}">
                            
                            <div class="mb-3">
                                <label class="form-label">Inversión por Línea (USDC)</label>
                                <div class="input-group"><span class="input-group-text">$</span><input type="number" class="form-control" id="amount-${index}" value="${strategy.amount_per_grid}"></div>
                            </div>
                            <div class="row">
                                <div class="col-6 mb-3"><label class="form-label">Nº Líneas</label><input type="number" class="form-control" id="qty-${index}" value="${strategy.grids_quantity}" oninput="setManual(${index})"></div>
                                <div class="col-6 mb-3"><label class="form-label">Spread (%)</label><div class="input-group"><input type="number" class="form-control" id="spread-${index}" value="${strategy.grid_spread}" step="0.1" oninput="setManual(${index})"><span class="input-group-text">%</span></div></div>
                            </div>

                            <div class="form-check form-switch mb-3 p-2 border rounded bg-white">
                                <input class="form-check-input ms-0 me-2" type="checkbox" role="switch" id="trailing-${index}" ${trailing ? 'checked' : ''} style="float:none;">
                                <label class="form-check-label fw-bold small text-primary" for="trailing-${index}"><i class="fa-solid fa-arrow-trend-up me-1"></i> Trailing Up</label>
                            </div>
                            
                            <hr class="text-muted">
                            
                            <label class="form-label fw-bold small text-muted"><i class="fa-solid fa-flag-checkered me-1"></i> MODALIDAD DE ARRANQUE</label>
                            <div class="d-flex justify-content-between mb-2">
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="startmode-${index}" id="sm-wait-${index}" value="wait" ${startMode=='wait'?'checked':''}>
                                    <label class="form-check-label small" for="sm-wait-${index}">🐢 Esperar</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="startmode-${index}" id="sm-buy1-${index}" value="buy_1" ${startMode=='buy_1'?'checked':''}>
                                    <label class="form-check-label small" for="sm-buy1-${index}">🐇 Compra 1</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="startmode-${index}" id="sm-buy2-${index}" value="buy_2" ${startMode=='buy_2'?'checked':''}>
                                    <label class="form-check-label small" for="sm-buy2-${index}">🐅 Carga x2</label>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
            container.innerHTML += html;
            setTimeout(() => analyzeSymbol(pair.symbol, index, profile), 500 + (index * 200));
        });
    } catch (e) { console.error(e); alert("Error leyendo la configuración."); }
}

export async function analyzeSymbol(symbol, index, currentProfile) {
    try {
        const savedTf = rsiTimeframeCache[index] || '4h';
        const res = await fetch(`/api/strategy/analyze/?symbol=${encodeURIComponent(symbol)}&timeframe=${savedTf}&_=${Date.now()}`);
        if (!res.ok) throw new Error("API Error");
        const data = await res.json();
        
        strategyCache[index] = data;
        const box = document.getElementById(`rsi-box-${index}`);
        if (!box) return;
        
        let rsiColor = 'text-muted';
        if (data.rsi < 35) rsiColor = 'text-success fw-bold';
        else if (data.rsi > 65) rsiColor = 'text-danger fw-bold';
        else rsiColor = 'text-primary';
        
        const btnCons = currentProfile === 'conservative' ? 'btn-success' : 'btn-outline-dark';
        const btnMod = currentProfile === 'moderate' ? 'btn-primary' : 'btn-outline-dark';
        const btnAgg = currentProfile === 'aggressive' ? 'btn-danger' : 'btn-outline-dark';
        const btnMan = currentProfile === 'manual' ? 'btn-secondary' : 'btn-outline-dark';
        
        const btn15m = savedTf === '15m' ? 'btn-secondary active' : 'btn-outline-secondary';
        const btn1h = savedTf === '1h' ? 'btn-secondary active' : 'btn-outline-secondary';
        const btn4h = savedTf === '4h' ? 'btn-secondary active' : 'btn-outline-secondary';

        box.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span class="small fw-bold">RSI: <span class="${rsiColor}">${data.rsi}</span></span>
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-sm ${btn15m}" style="padding: 0.1rem 0.4rem; font-size: 0.7rem;" onclick="changeRsiTf('${symbol}', ${index}, '${currentProfile}', '15m')">15m</button>
                    <button type="button" class="btn btn-sm ${btn1h}" style="padding: 0.1rem 0.4rem; font-size: 0.7rem;" onclick="changeRsiTf('${symbol}', ${index}, '${currentProfile}', '1h')">1h</button>
                    <button type="button" class="btn btn-sm ${btn4h}" style="padding: 0.1rem 0.4rem; font-size: 0.7rem;" onclick="changeRsiTf('${symbol}', ${index}, '${currentProfile}', '4h')">4h</button>
                </div>
            </div>
            <div class="d-flex justify-content-between gap-1">
                <button id="btn-cons-${index}" class="btn btn-sm ${btnCons} flex-fill" title="Conservadora" onclick="applyStrategy(${index}, 'conservative')">🛡️</button>
                <button id="btn-mod-${index}" class="btn btn-sm ${btnMod} flex-fill" title="Moderada" onclick="applyStrategy(${index}, 'moderate')">⚖️</button>
                <button id="btn-agg-${index}" class="btn btn-sm ${btnAgg} flex-fill" title="Agresiva" onclick="applyStrategy(${index}, 'aggressive')">🚀</button>
                <button id="btn-man-${index}" class="btn btn-sm ${btnMan} flex-fill" disabled style="opacity:1" title="Manual">🛠️</button>
            </div>
            <div class="mt-1 small text-muted text-start fst-italic" style="font-size:0.7rem">
               Estrategia: <strong>${currentProfile ? currentProfile.toUpperCase() : 'MANUAL'}</strong>
            </div>
        `;
    } catch (e) { const box = document.getElementById(`rsi-box-${index}`); if(box) box.innerHTML = '<small class="text-danger">Error RSI</small>'; }
}

export function changeRsiTf(symbol, index, profile, tf) {
    rsiTimeframeCache[index] = tf;
    const box = document.getElementById(`rsi-box-${index}`);
    if(box) box.innerHTML = '<div class="spinner-border spinner-border-sm text-secondary"></div>';
    analyzeSymbol(symbol, index, profile);
}

export function updateButtons(index, activeProfile) {
    const hiddenInput = document.getElementById(`profile-${index}`);
    if(hiddenInput) hiddenInput.value = activeProfile;

    const bC = document.getElementById(`btn-cons-${index}`);
    const bM = document.getElementById(`btn-mod-${index}`);
    const bA = document.getElementById(`btn-agg-${index}`);
    const bMan = document.getElementById(`btn-man-${index}`);
    
    // Reset clases
    if(bC) bC.className = `btn btn-sm flex-fill ${activeProfile==='conservative' ? 'btn-success' : 'btn-outline-dark'}`;
    if(bM) bM.className = `btn btn-sm flex-fill ${activeProfile==='moderate' ? 'btn-primary' : 'btn-outline-dark'}`;
    if(bA) bA.className = `btn btn-sm flex-fill ${activeProfile==='aggressive' ? 'btn-danger' : 'btn-outline-dark'}`;
    if(bMan) bMan.className = `btn btn-sm flex-fill ${activeProfile==='manual' ? 'btn-secondary' : 'btn-outline-dark'}`;
}

export function applyStrategy(index, type) {
    const data = strategyCache[index];
    if (!data || !data[type]) { alert("Datos no disponibles"); return; }
    const s = data[type];
    if(confirm(`¿Aplicar estrategia ${type.toUpperCase()}?\n\nLíneas: ${s.grids}\nSpread: ${s.spread}%`)) {
        document.getElementById(`qty-${index}`).value = s.grids;
        document.getElementById(`spread-${index}`).value = s.spread;
        updateButtons(index, type);
    }
}

export function setManual(index) { updateButtons(index, 'manual'); }

export function toggleCard(index) {
    const checkbox = document.getElementById(`enable-${index}`);
    const card = document.getElementById(`card-pair-${index}`);
    const label = document.getElementById(`lbl-${index}`);
    
    if (checkbox.checked) { 
        card.classList.remove('card-disabled'); 
        if(label) label.innerText = "ON";
    } else { 
        card.classList.add('card-disabled'); 
        if(label) label.innerText = "OFF";
    }
}

export async function saveConfigForm() {
    if (!currentConfigObj) return;
    const sysCycle = document.getElementById('sys-cycle');
    if(sysCycle) currentConfigObj.system.cycle_delay = parseInt(sysCycle.value);
    
    const tNet = document.getElementById('sys-testnet'); if(tNet) currentConfigObj.system.use_testnet = tNet.checked;
    const tTg = document.getElementById('sys-telegram'); if(tTg) currentConfigObj.system.telegram_enabled = tTg.checked;

    currentConfigObj.pairs.forEach((pair, index) => {
        const isEnabled = document.getElementById(`enable-${index}`).checked;
        const amount = parseFloat(document.getElementById(`amount-${index}`).value);
        const qty = parseInt(document.getElementById(`qty-${index}`).value);
        const spread = parseFloat(document.getElementById(`spread-${index}`).value);
        
        const profileInput = document.getElementById(`profile-${index}`);
        const profile = profileInput ? profileInput.value : 'manual';
        
        const trailingCheck = document.getElementById(`trailing-${index}`);
        const trailing = trailingCheck ? trailingCheck.checked : false;
        
        let startMode = 'wait';
        if (document.getElementById(`sm-buy1-${index}`).checked) startMode = 'buy_1';
        if (document.getElementById(`sm-buy2-${index}`).checked) startMode = 'buy_2';

        pair.enabled = isEnabled;
        if (!pair.strategy) pair.strategy = {};
        pair.strategy.amount_per_grid = amount;
        pair.strategy.grids_quantity = qty;
        pair.strategy.grid_spread = spread;
        pair.strategy.start_mode = startMode;
        pair.strategy.strategy_profile = profile; 
        pair.strategy.trailing_enabled = trailing;
    });

    const jsonString = JSON.stringify(currentConfigObj, null, 2);
    const msgBox = document.getElementById('config-alert');
    
    try {
        const res = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: jsonString }) });
        const data = await res.json();
        
        if(msgBox) msgBox.style.display = 'block';
        if (res.ok) { 
            if(msgBox) {
                msgBox.className = 'alert alert-success'; msgBox.innerHTML = '<i class="fa-solid fa-check-circle"></i> Guardado! Recargando...'; 
            }
            setTimeout(() => { location.reload(); }, 1500); 
        } else { 
            if(msgBox) {
                msgBox.className = 'alert alert-danger'; msgBox.innerText = 'Error: ' + data.detail; 
            }
        }
    } catch (e) { alert("Error al guardar."); }
}

// EXPORTAMOS FUNCIONES A WINDOW PARA QUE FUNCIONEN LOS ONCLICK
window.loadConfigForm = loadConfigForm;
window.saveConfigForm = saveConfigForm;
window.toggleCard = toggleCard;
window.applyStrategy = applyStrategy;
window.setManual = setManual;
window.changeRsiTf = changeRsiTf;
