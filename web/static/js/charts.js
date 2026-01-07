/**
 * Módulo de Gráficas - GridBot Pro
 * Renderiza gráficas con librerías ECharts y Lightweight Charts
 */

import { fmtUSDC, fmtInt } from './utils.js';

// Caché para instancias de Lightweight Charts (gráficas de velas/líneas)
let chartInstances = {};

// --- GESTIÓN DE COLORES (TEMA) ---
/**
 * Obtiene colores del tema actual del usuario
 * @returns {Object} Configuración de colores para el tema
 */
function getThemeColors() {
    const theme = localStorage.getItem('gridbot_theme');
    const isDark = theme && theme !== 'default' && theme !== 'light';
    
    return isDark ? {
        bg: '#2c3038',   // Fondo oscuro
        text: '#b9b9c3', // Texto gris claro
        grid: '#3b4047', 
        border: '#3b4047',
        up: '#0ecb81',
        down: '#f6465d'
    } : {
        bg: '#ffffff',   // Blanco
        text: '#333333',
        grid: '#f0f3fa',
        border: '#d1d3e2',
        up: '#0ecb81',
        down: '#f6465d'
    };
}

// --- GRÁFICA DE DONA (ECharts) ---
/**
 * Renderiza gráfica de dona/pastel con comportamiento responsivo
 * @param {string} domId - ID del elemento DOM
 * @param {Array} data - Datos de la gráfica
 * @param {boolean} isCurrency - Si los datos representan valores en moneda
 */
export function renderDonut(domId, data, isCurrency = false) {
    const dom = document.getElementById(domId);
    if (!dom) return;
    
    if (typeof echarts === 'undefined') return;

    // 1. REUTILIZAR INSTANCIA: No destruimos si ya existe
    let chart = echarts.getInstanceByDom(dom);
    if (!chart) {
        chart = echarts.init(dom);
        // Afegim el resize automàtic només un cop al crear
        window.addEventListener('resize', () => chart.resize());
    }
    
    const chartData = (data && data.length > 0) ? data : [{value: 0, name: 'Sin Datos'}];
    const colors = getThemeColors();

    // 2. DETECCIÓN MÓVIL: Ajustem disseny segons pantalla
    const isMobile = window.innerWidth < 768; // Menys de 768px és mòbil/tablet vertical

    // Configuració dinàmica
    const option = {
        // El tooltip se mantiene igual
        color: ['#5b45f4', '#0ecb81', '#f6465d', '#ffc107', '#3b82f6', '#6b7280', '#a78bfa'],
        tooltip: { 
            trigger: 'item', 
            formatter: function(params) { 
                const val = isCurrency ? fmtUSDC(params.value) : fmtInt(params.value); 
                return `${params.name}: ${val} (${params.percent}%)`; 
            } 
        },
        // Leyenda: Al lado en PC, a bajo en Móvil (para evitar cortes)
        legend: { 
            show: true,
            orient: isMobile ? 'horizontal' : 'vertical', 
            left: isMobile ? 'center' : '0%', 
            top: isMobile ? 'bottom' : 'center', // A sota en mòbil
            itemGap: 10, 
            textStyle: { fontSize: 11, color: colors.text } 
        },
        series: [{ 
            type: 'pie', 
            // Radio y Centro ajustados para móvil
            radius: isMobile ? ['35%', '60%'] : ['40%', '80%'], 
            center: isMobile ? ['50%', '45%'] : ['60%', '50%'], 
            
            avoidLabelOverlap: false,
            label: { show: false, position: 'center' }, 
            emphasis: { 
                label: { 
                    show: true, 
                    fontSize: isMobile ? 14 : 16, // Texto un poco más pequeño para móvil
                    fontWeight: 'bold', 
                    color: colors.text 
                } 
            }, 
            // El borde del mismo color que el fondo hace efecto de separación más limpio
            itemStyle: { 
                borderColor: colors.bg, 
                borderWidth: 2 
            }, 
            data: chartData 
        }] 
    };
    
    // 3. ACTUALITZACIÓN SUAVE: setOption hace la mágia sense borrar
    chart.setOption(option);
    // Aseguramos que se redibuje inmediatamente
    setTimeout(() => chart.resize(), 50);
    
    // 3. ACTUALITZACIÓN SUAVE: setOption hace la mágia sin borrar
    chart.setOption(option);
}

// --- LIGHTWEIGHT CHARTS (Línia Balance) - REEMPLAZADO POR ECHARTS ---
// Esta función ahora es un alias que usa ECharts para mejor control de escala
export function renderLineChart(domId, data, color) {
    renderEChart(domId, data, color, 'Balance');
}

// --- LIGHTWEIGHT CHARTS (Velas / Principal) ---
export function renderCandleChart(safeSym, data, gridLines, activeOrders = [], chartType = 'candles') {
    if (typeof LightweightCharts === 'undefined') return;

    const domId = `chart-${safeSym}`;
    const dom = document.getElementById(domId);
    if(!dom) return;
    if (!data || data.length === 0) {
        dom.innerHTML = '<div class="empty-chart text-center text-muted" style="padding:40px 10px">Sin datos disponibles</div>';
        return;
    }

    dom.style.position = 'relative';
    const colors = getThemeColors();

    // 1. CREACIÓN O RECUPERACIÓN DE LA INSTANCIA
    if (!chartInstances[domId]) {
        dom.innerHTML = '';
        const chart = LightweightCharts.createChart(dom, {
            layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
            grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            leftPriceScale: { visible: true, borderColor: colors.border, scaleMargins: { top: 0.15, bottom: 0.15 } },
            rightPriceScale: { visible: true, borderColor: colors.border, textColor: 'rgba(255, 255, 255, 0)', scaleMargins: { top: 0.15, bottom: 0.15 } },
            timeScale: { borderColor: colors.border, timeVisible: true, secondsVisible: false, rightOffset: 2 },
        });

        const mainSeries = chart.addCandlestickSeries({
            upColor: colors.up, downColor: colors.down, 
            borderUpColor: colors.up, borderDownColor: colors.down, 
            wickUpColor: colors.up, wickDownColor: colors.down,
            priceScaleId: 'right' 
        });

        const axisSeries = chart.addLineSeries({
            color: 'rgba(0,0,0,0)', lineWidth: 1, priceScaleId: 'left', crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false
        });

        chartInstances[domId] = { 
            chart, mainSeries, axisSeries, activeType: 'candles', activeLines: [], initialZoomDone: false 
        };

        new ResizeObserver(entries => {
            if (entries.length === 0 || !entries[0].contentRect) return;
            const { width, height } = entries[0].contentRect;
            chart.applyOptions({ width, height });
        }).observe(dom);
    } else {
        // Actualizamos colores
        chartInstances[domId].chart.applyOptions({
            layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
            grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
            leftPriceScale: { borderColor: colors.border },
            rightPriceScale: { borderColor: colors.border },
            timeScale: { borderColor: colors.border }
        });
    }

    const { chart, axisSeries } = chartInstances[domId];

    // Cambio de tipo
    if (chartInstances[domId].activeType !== chartType) {
        chart.removeSeries(chartInstances[domId].mainSeries);
        let newSeries;
        if (chartType === 'line') {
            newSeries = chart.addAreaSeries({ lineColor: '#2962FF', topColor: 'rgba(41, 98, 255, 0.3)', bottomColor: 'rgba(41, 98, 255, 0)', lineWidth: 2, priceScaleId: 'right' });
        } else {
            newSeries = chart.addCandlestickSeries({ upColor: colors.up, downColor: colors.down, borderUpColor: colors.up, borderDownColor: colors.down, wickUpColor: colors.up, wickDownColor: colors.down, priceScaleId: 'right' });
        }
        chartInstances[domId].mainSeries = newSeries;
        chartInstances[domId].activeType = chartType;
        chartInstances[domId].activeLines = [];
    }

    // Limpiar líneas anteriores
    const mainSeries = chartInstances[domId].mainSeries;

    // Dibujar Grid (Líneas punteadas)
    const formattedData = data.map(d => {
        const dateParts = d[0].split(/[- :]/); 
        const dateObj = new Date(dateParts[0], dateParts[1]-1, dateParts[2], dateParts[3], dateParts[4]);
        return { time: dateObj.getTime() / 1000, open: parseFloat(d[1]), high: parseFloat(d[4]), low: parseFloat(d[3]), close: parseFloat(d[2]), value: parseFloat(d[2]) };
    });

    // Dibujar Órdenes Activas
    const uniqueData = [];
    const seenTimes = new Set();
    formattedData.sort((a, b) => a.time - b.time);
    formattedData.forEach(item => {
        if (!seenTimes.has(item.time)) { seenTimes.add(item.time); uniqueData.push(item); }
    });

    mainSeries.setData(uniqueData);
    axisSeries.setData(uniqueData.map(d => ({ time: d.time, value: d.close })));

    // Calcular rango de precios para forzar escala dinámica
    let minPrice = Infinity, maxPrice = -Infinity;
    uniqueData.forEach(d => {
        if (d.low < minPrice) minPrice = d.low;
        if (d.high > maxPrice) maxPrice = d.high;
    });
    
    

    // Líneas
    chartInstances[domId].activeLines.forEach(line => mainSeries.removePriceLine(line));
    chartInstances[domId].activeLines = [];

    activeOrders.forEach(o => {
        const isBuy = o.side === 'buy';
        const line = mainSeries.createPriceLine({
            price: parseFloat(o.price), color: isBuy ? colors.up : colors.down, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: (isBuy ? 'C' : 'V') + ` ${fmtInt(o.amount)}`,
        });
        chartInstances[domId].activeLines.push(line);
    });
    
    // Zoom Inicial y Ajuste de Escala
    if (!chartInstances[domId].initialZoomDone) {
        const visibleRange = 100;
        const totalData = uniqueData.length;
        if (totalData > visibleRange) {
            chart.timeScale().setVisibleLogicalRange({ from: totalData - visibleRange, to: totalData });
        } else {
            chart.timeScale().fitContent();
        }
        chartInstances[domId].initialZoomDone = true;
    } else {
        // En actualizaciones posteriores, siempre hacer fitContent para ajustar escala
        chart.timeScale().fitContent();
    }
    
    // Forzar que las escalas de precio se auto-ajusten a los datos
    setTimeout(() => {
        if (chartInstances[domId] && chartInstances[domId].chart) {
            try {
                chartInstances[domId].chart.timeScale().fitContent();
            } catch(e) { /* silent */ }
        }
    }, 100);
}

// ECHARTS: Gráfico de línea con markers y leyenda (Balance Histórico)
export function renderEChart(domId, data, color = '#3b82f6', name = 'Balance total') {
    if (typeof echarts === 'undefined') return;
    const dom = document.getElementById(domId);
    if (!dom) return;
    if (!data || data.length === 0) {
        dom.innerHTML = '<div class="empty-chart text-center text-muted" style="padding:60px 10px">Sin datos disponibles</div>';
        return;
    }

    // Formateo de datos
    const labels = data.map(d => {
        const dt = new Date(d[0]);
        return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });
    const vals = data.map(d => d[1]);

    const colors = getThemeColors();

    // Calcular min/max y margen para escalar correctamente
    const numericVals = vals.map(v => Number(v));
    let min = Math.min(...numericVals);
    let max = Math.max(...numericVals);
    if (!isFinite(min) || !isFinite(max)) { min = 0; max = 0; }
    let diff = max - min;
    if (diff === 0) { diff = Math.abs(max) * 0.01 || 1; min -= diff; max += diff; }
    const margin = Math.max(diff * 0.05, diff === 0 ? 1 : 0.01);
    const yMin = Math.max(0, min - margin);
    const yMax = max + margin;
    

    if (!chartInstances[domId]) {
        dom.innerHTML = '';
        const chart = echarts.init(dom);
        const option = {
            color: [color],
            title: { show: false },
            tooltip: { trigger: 'axis', formatter: params => { const p = params[0]; return p.axisValue + '<br/><b>' + (p.seriesName || '') + ': </b>' + p.value; } },
            legend: { show: false },
            grid: { left: '6%', right: '6%', bottom: '8%', top: '18%' },
            xAxis: { type: 'category', data: labels, boundaryGap: false, axisLine: { lineStyle: { color: colors.grid } }, axisTick: { show: false }, axisLabel: { color: colors.text } },
            yAxis: { type: 'value', min: yMin, max: yMax, axisLine: { show: false }, splitLine: { lineStyle: { type: 'dashed', color: colors.grid } }, axisLabel: { color: colors.text } },
            series: [{
                name: '',
                type: 'line',
                data: vals,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2 },
                itemStyle: { color },
                areaStyle: { color: color, opacity: 0.06 }
            }]
        };
        chart.setOption(option);
        chartInstances[domId] = { echart: chart, option };
        new ResizeObserver(entries => { if (entries.length === 0 || !entries[0].contentRect) return; chart.resize(); }).observe(dom);
        window.addEventListener('resize', () => chart.resize());
    } else {
        const chart = chartInstances[domId].echart;
        chart.setOption({ xAxis: { data: labels }, yAxis: { min: yMin, max: yMax }, series: [{ data: vals, name }] });
        chart.resize();
    }
}

// Reset Zoom
export function resetChartZoom(safeSym) {
    const domId = `chart-${safeSym}`;
    if (chartInstances[domId]) {
        chartInstances[domId].initialZoomDone = false; 
    }
}

// Destrucción total
export function destroyChart(safeSym) {
    const domId = `chart-${safeSym}`;
    if (chartInstances[domId]) {
        try {
            chartInstances[domId].chart.remove();
            delete chartInstances[domId];
            const dom = document.getElementById(domId);
            if(dom) dom.innerHTML = '';
        } catch(e) { /* silent */ }
    }
}
