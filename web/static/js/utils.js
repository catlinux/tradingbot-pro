// Archivo: gridbot_binance/web/static/js/utils.js

export const fmtUSDC = (num) => { 
    if (num === undefined || num === null) return '--'; 
    return parseFloat(num).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); 
};

export const fmtPrice = (num) => {
    if (num === undefined || num === null) return '--';
    const val = parseFloat(num);
    if (val < 1.0) return val.toLocaleString('es-ES', { minimumFractionDigits: 5, maximumFractionDigits: 5 });
    if (val < 10.0) return val.toLocaleString('es-ES', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
    if (val >= 1000) return val.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    return val.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export const fmtInt = (num) => { 
    if (num === undefined || num === null) return '--'; 
    return parseInt(num).toLocaleString('es-ES'); 
};

export const fmtCrypto = (num) => { 
    if (!num) return '-'; 
    const val = parseFloat(num);
    let dec = val < 1 ? 5 : 2;
    return val.toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec });
};

export const fmtPct = (num) => {
    if (!num) return '0,00%';
    return parseFloat(num).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
};

export const updateColorValue = (elementId, value, suffix = '') => {
    const el = document.getElementById(elementId);
    if (!el) return;
    const newText = fmtUSDC(value) + suffix;
    if (el.innerText === newText) return;
    el.innerText = newText;
    el.classList.remove('text-success', 'text-danger', 'text-dark');
    if (value >= 0) el.classList.add('text-success');
    else el.classList.add('text-danger');
};
