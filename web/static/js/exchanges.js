/**
 * Módulo de gestión de exchanges
 */

let currentExchange = null;

/**
 * Inicializa los exchanges desde la BD al cargar la página
 */
async function initializeExchanges() {
    try {
        const response = await fetch('/api/exchanges/list');
        const data = await response.json();
        
        if (data.success && data.exchanges && data.exchanges.length > 0) {
            const select = document.getElementById('exchange-select');
            select.innerHTML = '<option value="" disabled selected>-- Elige un exchange --</option>';
            
            // Añadir cada exchange desde la BD
            data.exchanges.forEach(exch => {
                const option = document.createElement('option');
                option.value = exch.name.toLowerCase();
                let label = exch.name.charAt(0).toUpperCase() + exch.name.slice(1);
                if (exch.use_testnet) label += ' (Testnet)';
                option.textContent = label;
                select.appendChild(option);
            });
            
            // Habilitar el select si hay exchanges
            select.disabled = false;

            // Si ya hay un exchange conectado en el servidor, seleccionarlo
            try {
                const infoRes = await fetch('/api/exchange/info');
                if (infoRes.ok) {
                    const info = await infoRes.json();
                    if (info.connected && info.exchange) {
                        // info.exchange puede contener el sufijo -TESTNET; lo eliminamos para coincidir con las opciones
                        let ex = info.exchange.toLowerCase();
                        if (ex.endsWith('-testnet')) ex = ex.replace(/-testnet$/, '');
                        select.value = ex;
                        // Llamar a onExchangeSelected para conectar/mostrar cartera
                        await onExchangeSelected();
                    }
                }
            } catch(e) { /* no-op */ }
        } else {
            // Sin exchanges, mantener deshabilitado
            document.getElementById('exchange-select').disabled = true;
        }
    } catch (error) {
        console.error('Error cargando exchanges:', error);
        document.getElementById('exchange-select').disabled = true;
    }
}

/**
 * Se ejecuta cuando el usuario selecciona un exchange del dropdown
 */
async function onExchangeSelected() {
    const select = document.getElementById('exchange-select');
    const exchangeName = select.value;
    
    if (!exchangeName) {
        document.getElementById('exchange-form-container').innerHTML = 
            '<p class="text-muted text-center py-4">Selecciona un exchange para consultar</p>';
        return;
    }


    
    currentExchange = exchangeName;

    // Mostrar estado de conexión mientras intentamos conectar
    // Asegurar que el Dashboard (home) está visible para que las gráficas se rendericen correctamente
    if (typeof setMode === 'function') setMode('home');
    document.getElementById('exchange-form-container').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status"><span class="visually-hidden">Cargando...</span></div>
            <div class="mt-2">Conectando a <strong>${exchangeName.toUpperCase()}</strong>...</div>
        </div>
    `;

    try {
        const res = await fetch(`/api/exchanges/connect/${exchangeName}`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json().catch(()=>({detail:'Error desconocido'}));
            document.getElementById('exchange-form-container').innerHTML = `<div class="alert alert-danger">No se pudo conectar: ${err.detail || 'Error'}</div>`;
            return;
        }

        const d = await res.json();

        // Mostrar info básica y botón desconectar / eliminar
        document.getElementById('exchange-form-container').innerHTML = `
            <div class="p-3 text-center">
                <div>Conectado a <strong>${exchangeName.toUpperCase()}</strong> ✅</div>
                <div class="mt-2">
                    <button id="btn-disconnect-exchange" class="btn btn-sm btn-outline-danger">Desconectar</button>
                    <button id="btn-delete-exchange" class="btn btn-sm btn-danger ms-2">Eliminar configuración</button>
                </div>
            </div>
        `;

        document.getElementById('btn-disconnect-exchange').addEventListener('click', async () => {
            await fetch('/api/exchanges/disconnect', { method: 'POST' });
            document.getElementById('exchange-form-container').innerHTML = '<p class="text-muted text-center py-4">Exchange desconectado</p>';
            await initializeExchanges();
            await loadHome();
        });

        document.getElementById('btn-delete-exchange').addEventListener('click', async () => {
            await deleteExchangeConfig(exchangeName);
            document.getElementById('exchange-form-container').innerHTML = '<p class="text-muted text-center py-4">Selecciona un exchange para consultar</p>';
            await loadHome();
            // Programamos limpieza de caché tras 5s
            if (window.scheduleCacheClear) window.scheduleCacheClear(null, 5000);
        });

        // Si se ha conectado correctamente, forzamos snapshot inmediato para poblar la gráfica
        if (d.connected) {
            try {
                Swal.fire({title: '📸 Guardando snapshot inicial...', html: 'Obteniendo balance actual... por favor espere', allowOutsideClick: false, showConfirmButton: false, didOpen: () => Swal.showLoading()});
                const snapRes = await fetch('/api/record_balance', { method: 'POST' });
                const snapData = await snapRes.json().catch(()=>({}));
                Swal.close();
                if (snapRes.ok && snapData && snapData.success) {
                    Swal.fire({toast: true, position: 'top-end', icon: 'success', title: `Snapshot: ${snapData.balance} USDC`, showConfirmButton: false, timer: 1500});
                } else {
                    Swal.fire({toast: true, position: 'top-end', icon: 'warning', title: 'No se pudo guardar snapshot', showConfirmButton: false, timer: 1500});
                }
            } catch (e) {
                Swal.close();
                Swal.fire({toast: true, position: 'top-end', icon: 'error', title: 'Error al guardar snapshot', showConfirmButton: false, timer: 1500});
            }
        }

        // Recargar datos del dashboard para mostrar cartera del exchange
        if (typeof loadHome === 'function') await loadHome();

        // Programamos la limpieza de caché y recarga completa tras 5s (por si hay otros paneles activos)
        // Usamos solo la tarea programada para evitar recargas dobles
        if (window.scheduleCacheClear) window.scheduleCacheClear(exchangeName.toLowerCase(), 5000);

    } catch (error) {
        console.error('Error conectando:', error);
        document.getElementById('exchange-form-container').innerHTML = `<div class="alert alert-danger">Error de conexión: ${error.message}</div>`;
    }
}

/**
 * Abre el modal para añadir un nuevo exchange
 */
function openAddExchangeModal() {
    const modal = new bootstrap.Modal(document.getElementById('addExchangeModal'));
    document.getElementById('add-exchange-error').classList.add('d-none');
    document.getElementById('addExchangeForm').reset();
    modal.show();
}

/**
 * Guarda un nuevo exchange en la BD
 */
async function performAddExchange() {
    const exchangeName = document.getElementById('new-exchange-name').value.trim().toUpperCase();
    const apiKey = document.getElementById('new-exchange-api-key').value.trim();
    const secretKey = document.getElementById('new-exchange-secret-key').value.trim();
    const passphrase = document.getElementById('new-exchange-passphrase').value.trim();
    const useTestnet = document.getElementById('new-exchange-testnet').checked;
    const errorDiv = document.getElementById('add-exchange-error');
    
    errorDiv.classList.add('d-none');
    
    // Validaciones
    if (!exchangeName || !apiKey || !secretKey) {
        errorDiv.textContent = 'Completa todos los campos requeridos (Exchange, API Key, Secret Key)';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    try {
        const params = new URLSearchParams();
        params.append('exchange_name', exchangeName.toLowerCase());
        params.append('api_key', apiKey);
        params.append('secret_key', secretKey);
        if (passphrase) {
            params.append('passphrase', passphrase);
        }
        if (useTestnet) {
            params.append('use_testnet', '1');
        }
        
        const response = await fetch('/api/exchanges/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: params.toString()
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.validated === false) {
                const suggestion = (data.message && data.message.toLowerCase().includes('invalid api')) ? '\n\nSugerencias:\n- Asegúrate de pegar la API Key en el campo "API Key" y la Secret Key en "Secret Key".\n- Comprueba que la opción "Usar Testnet" esté marcada si usas testnet.\n- Revisa restricciones de IP o permisos en la API (lectura de balance).\n' : '';
                const res = await Swal.fire({
                    title: 'Advertencia',
                    text: `La validación de claves ha fallado: ${data.message || 'Sin detalles'}.${suggestion}¿Deseas mantener la configuración guardada?`,
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Mantener',
                    cancelButtonText: 'Eliminar'
                });

                if (!res.isConfirmed) {
                    // Usuario eligió eliminar la entrada guardada
                    await deleteExchangeConfig(exchangeName.toLowerCase());
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addExchangeModal'));
                    if (modal) modal.hide();
                    await initializeExchanges();
                    return;
                }
            } else {
                await Swal.fire({
                    title: 'Éxito',
                    text: `Exchange ${exchangeName} añadido correctamente`,
                    icon: 'success',
                    confirmButtonText: 'Aceptar'
                });
            }
            
            // Cerrar modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('addExchangeModal'));
            if (modal) modal.hide();
            
            // Recargar lista de exchanges
            await initializeExchanges();
            // Seleccionar automáticamente el exchange añadido y cargar su panel
            const select = document.getElementById('exchange-select');
            if (select) {
                select.value = exchangeName.toLowerCase();
                await onExchangeSelected();
            }
        } else {
            errorDiv.textContent = data.message || 'Error al guardar el exchange';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error:', error);
        errorDiv.textContent = 'Error de conexión: ' + error.message;
        errorDiv.classList.remove('d-none');
    }
}

/**
 * Elimina la configuración de un exchange
 */
async function deleteExchangeConfig(exchangeName) {
    const confirm = await Swal.fire({
        title: '¿Eliminar?',
        text: `Se eliminará la configuración de ${exchangeName}`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Sí, eliminar',
        cancelButtonText: 'Cancelar'
    });
    
    if (!confirm.isConfirmed) return;
    
    try {
        const response = await fetch(`/api/exchanges/delete/${exchangeName}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            await Swal.fire({
                title: 'Eliminado',
                text: 'Exchange eliminado correctamente',
                icon: 'success',
                confirmButtonText: 'Aceptar'
            });
            
            // Limpiar formulario y recargar lista
            document.getElementById('exchange-select').value = '';
            await initializeExchanges();
            document.getElementById('exchange-form-container').innerHTML = 
                '<p class="text-muted text-center py-4">Selecciona un exchange para configurar</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        Swal.fire('Error', 'No se pudo eliminar el exchange', 'error');
    }
}
