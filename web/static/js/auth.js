// auth.js - Gestión de autenticación del bot

// Estado global de autenticación
let authState = {
    isLogged: false,
    username: null,
    token: null,
    loginTime: null  // Timestamp de login para tracking de sesión
};

// Variable global para almacenar la existencia de usuario
let userExists = false;

/**
 * Inicializa el estado de autenticación al cargar la página
 */
async function initAuthSystem() {
    try {
        // Verificar si hay usuario creado
        const checkResponse = await fetch('/api/auth/check-user');
        const checkData = await checkResponse.json();
        userExists = checkData.userExists;
        
        // Verificar si ya hay sesión activa en sessionStorage
        const storedToken = sessionStorage.getItem('auth_token');
        const storedUsername = sessionStorage.getItem('auth_username');
        const storedLoginTime = sessionStorage.getItem('auth_login_time');
        
        if (storedToken && storedUsername && storedLoginTime) {
            // Verificar si la sesión ha caducado (24 horas = 86400000 ms)
            const currentTime = Date.now();
            const sessionDuration = currentTime - parseInt(storedLoginTime);
            const SESSION_TIMEOUT = 24 * 60 * 60 * 1000; // 24 horas en milisegundos
            
            if (sessionDuration < SESSION_TIMEOUT) {
                // Sesión válida
                authState.isLogged = true;
                authState.username = storedUsername;
                authState.token = storedToken;
                authState.loginTime = parseInt(storedLoginTime);

                // Pedir al servidor la info del usuario (email real)
                try {
                    const statusResp = await fetch('/api/auth/status', {
                        headers: { 'Authorization': 'Bearer ' + storedToken }
                    });
                    const statusData = await statusResp.json();
                    if (statusData.logged) {
                        sessionStorage.setItem('auth_email', statusData.email || '');
                        authState.username = statusData.username || authState.username;
                    }
                } catch (e) {
                    console.warn('initAuthSystem: no se pudo obtener status del servidor', e);
                }

                updateAuthUI(userExists);
            } else {
                // Sesión caducada
                sessionStorage.removeItem('auth_token');
                sessionStorage.removeItem('auth_username');
                sessionStorage.removeItem('auth_login_time');
                updateAuthUI(userExists);
            }
        } else {
            // Sin sesión activa
            updateAuthUI(userExists);
        }
    } catch (error) {
        console.error('Error al inicializar autenticación:', error);
        updateAuthUI(false);
    }
}

/**
 * Actualiza la interfaz de usuario según el estado de autenticación
 */
function updateAuthUI(userExistsParam = null) {
    // Actualizar la variable global si se proporciona
    if (userExistsParam !== null) {
        userExists = userExistsParam;
    }
    
    const btnLogin = document.getElementById('btn-login');
    const btnCreateUser = document.getElementById('btn-create-user');
    const btnRecovery = document.getElementById('btn-recovery');
    const authLogged = document.getElementById('auth-logged');
    const loggedUsername = document.getElementById('logged-username');
    const configUsername = document.getElementById('config-username');
    const configEmail = document.getElementById('config-email');
    const configLoginStatus = document.getElementById('config-login-status');
    
    if (authState.isLogged) {
        // Usuario logueado: ocultar banner
        updateAuthBanner(false);
        
        // Usuario logueado
        if (btnLogin) btnLogin.classList.add('d-none');
        if (btnCreateUser) btnCreateUser.classList.add('d-none');
        if (btnRecovery) btnRecovery.classList.add('d-none');
        if (authLogged) authLogged.classList.add('active');
        if (loggedUsername) loggedUsername.textContent = authState.username;
        
        // Actualizar tarjeta de usuario
        if (configUsername) configUsername.textContent = authState.username;
        // Obtener email del usuario desde la sesión (si está disponible)
        const userEmail = sessionStorage.getItem('auth_email');
        if (configEmail) {
            configEmail.textContent = userEmail || '--';
        }
        if (configLoginStatus) {
            configLoginStatus.textContent = 'Sesión activa';
            configLoginStatus.style.color = '#16a34a';
        }
        
        // Mostrar todas las pestañas
        showAllTabs();
    } else {
        // Usuario no logueado
        if (authLogged) authLogged.classList.remove('active');
        
        if (userExists) {
            // Usuario existe pero no está logueado: mostrar banner
            updateAuthBanner(true, 'user-not-logged');
            
            if (btnLogin) {
                btnLogin.classList.remove('d-none');
            }
            if (btnCreateUser) btnCreateUser.classList.add('d-none');
            if (btnRecovery) {
                btnRecovery.classList.remove('d-none');
            }
            
            // Actualizar tarjeta de usuario
            if (configUsername) configUsername.textContent = 'Sin sesión iniciada';
            if (configEmail) configEmail.textContent = '--';
            if (configLoginStatus) {
                configLoginStatus.textContent = 'No logueado';
                configLoginStatus.style.color = '#f59e0b';
            }
        } else {
            // No existe usuario - mostrar crear y banner
            updateAuthBanner(true, 'no-user');
            
            if (btnLogin) btnLogin.classList.add('d-none');
            if (btnCreateUser) {
                btnCreateUser.classList.remove('d-none');
            }
            if (btnRecovery) btnRecovery.classList.add('d-none');
            
            // Actualizar tarjeta de usuario
            if (configUsername) configUsername.textContent = 'No hay usuario creado';
            if (configEmail) configEmail.textContent = '--';
            if (configLoginStatus) {
                configLoginStatus.textContent = '--';
                configLoginStatus.style.color = '#6b7280';
            }
        }
        
        // Ocultar pestañas sensibles
        hideRestrictedTabs();
        
        // Cargar contenido dummy si no está logueado
        loadDummyContent();
    }
    
    // REGLA POTENTE: Controlar visibilidad de secciones según estado de login
    updateConfigSectionsVisibility();
    
    // Actualizar tarjeta superior de exchange
    const exchangeCard = document.getElementById('config-exchange-name');
    if (exchangeCard) {
        updateExchangeName();
    }
}

/**
 * Actualiza el banner de autenticación con mensajes dinámicos
 */
function updateAuthBanner(show = true, bannerType = 'user-not-logged') {
    const banner = document.getElementById('auth-banner');
    const bannerText = document.getElementById('auth-banner-text');
    
    if (!banner || !bannerText) return;
    
    if (!show) {
        // Ocultar banner
        banner.style.display = 'none';
        return;
    }
    
    // Mostrar banner con mensaje correspondiente
    banner.style.display = 'flex';
    
    if (bannerType === 'no-user') {
        bannerText.innerHTML = '<strong>⚙️ Configuración requerida:</strong> No hay usuario creado. Para acceder a todas las funciones de GridBot Pro, necesitas crear una cuenta. Haz clic en el botón <strong>"Crear Usuario"</strong> para comenzar.';
    } else if (bannerType === 'user-not-logged') {
        bannerText.innerHTML = '<strong>🔐 Acceso limitado:</strong> Tu sesión ha expirado o no estás autenticado. Por favor, inicia sesión para disfrutar de todas las funciones de GridBot Pro.';
    }
}

/**
 * Oculta/muestra valores sensibles en el dashboard
 * Usa un intervalo para mantener los valores ocultos continuamente
 */
/**
 * REGLA POTENTE Y MODULAR: Controla automáticamente la visibilidad de elementos
 * basándose en el estado de login del usuario
 * 
 * Uso: Añade la clase "auth-required" a cualquier elemento que quieras ocultar
 * cuando el usuario NO esté logueado. Se mostrará automáticamente cuando inicie sesión.
 */
function updateConfigSectionsVisibility() {
    // Obtener todos los elementos que requieren autenticación
    const authRequiredElements = document.querySelectorAll('[data-auth-required="true"]');
    const dummyCardsRow = document.getElementById('dummy-cards-row');
    const dummyChartsRow = document.getElementById('dummy-charts-row');

    // Debug: mostrar estado y conteos
    try {
        console.debug('updateConfigSectionsVisibility - isLogged:', authState.isLogged, 'authRequiredCount:', authRequiredElements.length, 'dummyCardsRow:', !!dummyCardsRow, 'dummyChartsRow:', !!dummyChartsRow);
    } catch (e) {
        // no-op
    }
    
    if (authState.isLogged) {
        // Usuario logueado: mostrar elementos sensibles, ocultar dummy
        authRequiredElements.forEach(element => {
            element.classList.remove('d-none');
        });
        if (dummyCardsRow) {
            dummyCardsRow.classList.add('d-none');
        }
        if (dummyChartsRow) {
            dummyChartsRow.classList.add('d-none');
        }
    } else {
        // Usuario NO logueado: ocultar elementos sensibles, mostrar dummy
        authRequiredElements.forEach(element => {
            element.classList.add('d-none');
        });
        if (dummyCardsRow) {
            dummyCardsRow.classList.remove('d-none');
        }
        if (dummyChartsRow) {
            dummyChartsRow.classList.remove('d-none');
        }
    }

    // Validación post-acción: comprobar discrepancias visibles y reportarlas
    try {
        if (authState.isLogged) {
            authRequiredElements.forEach(el => {
                if (el.classList.contains('d-none')) {
                    console.warn('Visibility mismatch: element with data-auth-required still hidden while logged in', el);
                }
            });
            if (dummyCardsRow && !dummyCardsRow.classList.contains('d-none')) {
                console.warn('Visibility mismatch: dummy-cards-row should be hidden when logged in');
            }
            if (dummyChartsRow && !dummyChartsRow.classList.contains('d-none')) {
                console.warn('Visibility mismatch: dummy-charts-row should be hidden when logged in');
            }
        } else {
            authRequiredElements.forEach(el => {
                if (!el.classList.contains('d-none')) {
                    console.warn('Visibility mismatch: element with data-auth-required visible while NOT logged in', el);
                }
            });
            if (dummyCardsRow && dummyCardsRow.classList.contains('d-none')) {
                console.warn('Visibility mismatch: dummy-cards-row should be visible when NOT logged in');
            }
            if (dummyChartsRow && dummyChartsRow.classList.contains('d-none')) {
                console.warn('Visibility mismatch: dummy-charts-row should be visible when NOT logged in');
            }
        }
    } catch (err) {
        console.warn('Error during visibility validation', err);
    }
}

/**
 * Abre modal de login
 */
function openLoginModal() {
    const modal = new bootstrap.Modal(document.getElementById('loginModal'));
    document.getElementById('login-error').classList.add('d-none');
    document.getElementById('loginForm').reset();
    modal.show();
}

/**
 * Abre modal de crear usuario
 */
function openCreateUserModal() {
    const modal = new bootstrap.Modal(document.getElementById('createUserModal'));
    document.getElementById('create-error').classList.add('d-none');
    document.getElementById('createUserForm').reset();
    modal.show();
}

/**
 * Abre modal de recuperar contraseña
 */
function openRecoveryModal() {
    const modal = new bootstrap.Modal(document.getElementById('recoveryModal'));
    document.getElementById('recovery-error').classList.add('d-none');
    document.getElementById('recoveryForm').reset();
    document.getElementById('recovery-question').classList.add('d-none');
    document.getElementById('recovery-next-btn').classList.remove('d-none');
    document.getElementById('recovery-submit-btn').classList.add('d-none');
    modal.show();
}

/**
 * Realiza el login
 */
async function performLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorDiv = document.getElementById('login-error');
    
    if (!username || !password) {
        errorDiv.textContent = 'Por favor completa todos los campos';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            authState.isLogged = true;
            authState.username = username;
            authState.token = data.token;
            authState.loginTime = Date.now();
            
            // Guardar en sessionStorage incluyendo timestamp y email
            sessionStorage.setItem('auth_token', data.token);
            sessionStorage.setItem('auth_username', username);
            sessionStorage.setItem('auth_login_time', authState.loginTime.toString());
            // Temporalmente guardar email vacío; lo obtendremos del servidor
            sessionStorage.setItem('auth_email', '');
            
            // Debug: confirmar estado antes de actualizar UI
            console.debug('performLogin: authState set ->', JSON.parse(JSON.stringify(authState)));
            
            // Obtener email desde servidor de sesión
            try {
                const statusResp = await fetch('/api/auth/status', {
                    headers: { 'Authorization': 'Bearer ' + data.token }
                });
                const statusData = await statusResp.json();
                if (statusData.logged && statusData.email) {
                    sessionStorage.setItem('auth_email', statusData.email);
                }
            } catch (e) {
                console.warn('performLogin: no se pudo obtener email del servidor', e);
            }

            updateAuthUI();
            
            // Cerrar modal
            bootstrap.Modal.getInstance(document.getElementById('loginModal')).hide();
            
            // Mostrar alerta de éxito
            Swal.fire({
                icon: 'success',
                title: 'Sesión iniciada',
                text: `Bienvenido ${username}`,
                timer: 2000
            });
        } else {
            errorDiv.textContent = data.detail || 'Credenciales inválidas';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        errorDiv.textContent = 'Error al conectar con el servidor';
        errorDiv.classList.remove('d-none');
        console.error('Error en login:', error);
    }
}

/**
 * Realiza la creación de usuario
 */
async function performCreateUser() {
    const username = document.getElementById('create-username').value.trim();
    const email = document.getElementById('create-email').value.trim();
    const securityQuestion = document.getElementById('create-security-question').value;
    const securityAnswer = document.getElementById('create-security-answer').value.trim();
    const password = document.getElementById('create-password').value;
    const passwordConfirm = document.getElementById('create-password-confirm').value;
    const errorDiv = document.getElementById('create-error');
    
    // Validaciones
    if (!username || !email || !securityQuestion || !securityAnswer || !password) {
        errorDiv.textContent = 'Por favor completa todos los campos';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    if (username.length < 4) {
        errorDiv.textContent = 'El usuario debe tener al menos 4 caracteres';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    if (!/^[a-zA-Z0-9_]+$/.test(username)) {
        errorDiv.textContent = 'El usuario solo puede contener letras, números y guiones bajos';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    if (password.length < 8) {
        errorDiv.textContent = 'La contraseña debe tener al menos 8 caracteres';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    if (!/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[!@#$%^&*]/.test(password)) {
        errorDiv.textContent = 'La contraseña debe contener mayúscula, número y símbolo (!@#$%^&*)';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    if (password !== passwordConfirm) {
        errorDiv.textContent = 'Las contraseñas no coinciden';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    try {
        const response = await fetch('/api/auth/create-user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username,
                email,
                security_question: parseInt(securityQuestion),
                security_answer: securityAnswer,
                password
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            authState.isLogged = true;
            authState.username = username;
            authState.token = data.token;
            authState.loginTime = Date.now();
            
            // Guardar en sessionStorage incluyendo timestamp y email
            sessionStorage.setItem('auth_token', data.token);
            sessionStorage.setItem('auth_username', username);
            sessionStorage.setItem('auth_login_time', authState.loginTime.toString());
            sessionStorage.setItem('auth_email', email); // Guardar email del usuario creado
            
            // Debug: confirmar estado antes de actualizar UI
            console.debug('performCreateUser: authState set ->', JSON.parse(JSON.stringify(authState)));
            
            updateAuthUI();
            
            // Cerrar modal
            bootstrap.Modal.getInstance(document.getElementById('createUserModal')).hide();
            
            // Mostrar alerta de éxito
            Swal.fire({
                icon: 'success',
                title: 'Usuario creado',
                text: `Bienvenido ${username}`,
                timer: 2000
            });
        } else {
            errorDiv.textContent = data.detail || 'Error al crear usuario';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        errorDiv.textContent = 'Error al conectar con el servidor';
        errorDiv.classList.remove('d-none');
        console.error('Error en creación:', error);
    }
}

/**
 * Obtiene la pregunta de seguridad
 */
async function recoveryGetQuestion() {
    const username = document.getElementById('recovery-username').value.trim();
    const errorDiv = document.getElementById('recovery-error');
    
    if (!username) {
        errorDiv.textContent = 'Por favor ingresa el nombre de usuario';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    try {
        const response = await fetch(`/api/auth/security-question/${username}`);
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('recovery-q-label').textContent = data.question;
            document.getElementById('recovery-question').classList.remove('d-none');
            document.getElementById('recovery-next-btn').classList.add('d-none');
            document.getElementById('recovery-submit-btn').classList.remove('d-none');
            errorDiv.classList.add('d-none');
        } else {
            errorDiv.textContent = data.detail || 'Usuario no encontrado';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        errorDiv.textContent = 'Error al conectar con el servidor';
        errorDiv.classList.remove('d-none');
        console.error('Error en recuperación:', error);
    }
}

/**
 * Realiza la recuperación de contraseña
 */
async function performRecovery() {
    const username = document.getElementById('recovery-username').value.trim();
    const answer = document.getElementById('recovery-answer').value.trim();
    const errorDiv = document.getElementById('recovery-error');
    
    if (!answer) {
        errorDiv.textContent = 'Por favor responde la pregunta de seguridad';
        errorDiv.classList.remove('d-none');
        return;
    }
    
    try {
        const response = await fetch('/api/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, answer })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Mostrar nueva contraseña o enviar por email
            Swal.fire({
                icon: 'success',
                title: 'Contraseña Resetada',
                html: data.message.replace(/\n/g, '<br>'),
                confirmButtonText: 'Aceptar'
            });
            
            bootstrap.Modal.getInstance(document.getElementById('recoveryModal')).hide();
        } else {
            errorDiv.textContent = data.detail || 'Respuesta de seguridad incorrecta';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        errorDiv.textContent = 'Error al conectar con el servidor';
        errorDiv.classList.remove('d-none');
        console.error('Error en reseteo:', error);
    }
}

/**
 * Cierra sesión
 */
async function logout() {
    Swal.fire({
        title: '¿Cerrar sesión?',
        text: 'Se cerrará tu sesión actual',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Sí, cerrar',
        cancelButtonText: 'Cancelar'
    }).then(async (result) => {
        if (result.isConfirmed) {
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
                authState.isLogged = false;
                authState.username = null;
                authState.token = null;
                authState.loginTime = null;
                
                // Limpiar sessionStorage
                sessionStorage.removeItem('auth_token');
                sessionStorage.removeItem('auth_username');
                sessionStorage.removeItem('auth_login_time');
                
                // Debug
                console.debug('logout - authState set to false');
                
                // Forzar refresco del visibility toggle
                try {
                    updateConfigSectionsVisibility();
                } catch (e) {
                    console.warn('logout: updateConfigSectionsVisibility failed', e);
                }
                
                // Después de logout, el usuario sigue existiendo en BD
                updateAuthUI(true);
                
                Swal.fire({
                    icon: 'success',
                    title: 'Sesión cerrada',
                    timer: 1500
                });
            } catch (error) {
                console.error('Error al cerrar sesión:', error);
            }
        }
    });
}

/**
 * Muestra todas las pestañas (usuario logueado)
 */
function showAllTabs() {
    ['tab-operaciones','tab-wallet','tab-estrategias'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.parentElement) {
            el.parentElement.classList.remove('d-none');
        } else {
            console.debug('showAllTabs: tab element missing', id);
        }
    });
}

/**
 * Oculta las pestañas restringidas (usuario no logueado)
 */
function hideRestrictedTabs() {
    ['tab-operaciones','tab-wallet','tab-estrategias'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.parentElement) {
            el.parentElement.classList.add('d-none');
        } else {
            console.debug('hideRestrictedTabs: tab element missing', id);
        }
    });
}

// Actualizar ping cada 10 segundos
setInterval(updatePing, 10000);

/**
 * Actualiza el ping del exchange
 */
async function updatePing() {
    try {
        const response = await fetch('/api/exchange/ping', {
            method: 'GET',
            signal: AbortSignal.timeout(5000) // Timeout de 5 segundos
        });
        
        const data = await response.json();
        
        if (response.ok) {
            updatePingUI(data.ping);
        } else {
            updatePingUI(null);
        }
    } catch (error) {
        console.warn('Error en ping:', error);
        updatePingUI(null);
    }
}

/**
 * Actualiza la UI del ping
 */
function updatePingUI(ping) {
    const pingValue = document.getElementById('config-ping-value');
    const pingIndicator = document.getElementById('config-ping-indicator');
    
    if (pingValue && pingIndicator) {
        // Remover todas las clases de estado
        pingIndicator.classList.remove('ping-good', 'ping-warning', 'ping-danger', 'ping-offline');
        
        if (ping === null || ping === undefined) {
            pingValue.textContent = '-- ms';
            pingIndicator.classList.add('ping-offline');
        } else {
            pingValue.textContent = `${ping} ms`;
            
            if (ping < 300) {
                pingIndicator.classList.add('ping-good');
            } else if (ping < 500) {
                pingIndicator.classList.add('ping-warning');
            } else {
                pingIndicator.classList.add('ping-danger');
            }
        }
    }
}

// Actualizar exchange name
async function updateExchangeName() {
    try {
        const response = await fetch('/api/exchange/info');
        const data = await response.json();
        
        const exchangeName = document.getElementById('config-exchange-name');
        if (exchangeName) {
            exchangeName.textContent = data.exchange || 'Binance';
        }
    } catch (error) {
        console.warn('Error al obtener exchange:', error);
    }
}

// Inicializar al cargar
document.addEventListener('DOMContentLoaded', () => {
    initAuthSystem();
    updateExchangeName();
    updatePing();
    // Cargar contenido dummy en la carga inicial
    setTimeout(() => loadDummyContent(), 500);
});

/**
 * Funciones para mostrar/ocultar secciones de configuración
 * Mantiene el código intacto pero solo cambia la visibilidad
 */
function toggleConfigSection(sectionId, show = true) {
    const element = document.getElementById(sectionId);
    if (element) {
        if (show) {
            element.classList.remove('d-none');
        } else {
            element.classList.add('d-none');
        }
    }
}

// Funciones específicas para cada sección
function showSistemaGlobal() { toggleConfigSection('section-sistema-global', true); }
function hideSistemaGlobal() { toggleConfigSection('section-sistema-global', false); }

function showControlOperaciones() { toggleConfigSection('section-control-operaciones', true); }
function hideControlOperaciones() { toggleConfigSection('section-control-operaciones', false); }

function showGestionDatos() { toggleConfigSection('section-gestion-datos', true); }
function hideGestionDatos() { toggleConfigSection('section-gestion-datos', false); }

function showConfigMoneda() { 
    toggleConfigSection('section-config-moneda-title', true);
    toggleConfigSection('section-config-moneda', true);
}
function hideConfigMoneda() { 
    toggleConfigSection('section-config-moneda-title', false);
    toggleConfigSection('section-config-moneda', false);
}

function showZonaPeligro() { toggleConfigSection('section-zona-peligro', true); }
function hideZonaPeligro() { toggleConfigSection('section-zona-peligro', false); }

// Mostrar todas las secciones de configuración
function showAllConfigSections() {
    showSistemaGlobal();
    showControlOperaciones();
    showGestionDatos();
    showConfigMoneda();
    showZonaPeligro();
}

// Ocultar todas las secciones de configuración
function hideAllConfigSections() {
    hideSistemaGlobal();
    hideControlOperaciones();
    hideGestionDatos();
    hideConfigMoneda();
    hideZonaPeligro();
}

/**
 * Filtra picos en los datos de balance
 * Ignora variaciones >30% que duren <1 minuto
 */
function filterBalancePikes(history) {
    if (history.length < 2) return history;
    
    const filtered = [history[0]];
    const spike_threshold = 0.30; // 30%
    const spike_duration_ms = 60000; // 1 minuto
    
    for (let i = 1; i < history.length; i++) {
        const prev = filtered[filtered.length - 1];
        const current = history[i];
        
        // Calcular variación porcentual
        const change = Math.abs((current.balance - prev.balance) / prev.balance);
        
        if (change > spike_threshold) {
            // Posible pico - buscar si se recupera rápido
            let isPike = false;
            for (let j = i + 1; j < history.length; j++) {
                const next = history[j];
                const timeDiff = new Date(next.timestamp) - new Date(current.timestamp);
                const recoveryChange = Math.abs((next.balance - current.balance) / current.balance);
                
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

/**
 * Carga el gráfico dummy (para usuarios no logueados)
 * Crea un gráfico ficticio sin valores sensibles
 */
async function loadDummyBalanceChart() {
    try {
        const dummyChartEl = document.getElementById('dummyBalanceChartHistory');
        if (!dummyChartEl) return;
        
        // Asegurar que el elemento está visible y tiene dimensiones
        if (dummyChartEl.offsetParent === null) {
            console.warn('dummyBalanceChartHistory: elemento no visible');
            return;
        }
        
        const dummyChart = echarts.init(dummyChartEl, 'light', { renderer: 'canvas' });
        
        // Crear datos ficticios para el gráfico demo
        const demoTimestamps = [];
        const demoBalances = [];
        const baseValue = 100;
        
        // Generar 50 puntos de datos ficticios
        for (let i = 0; i < 50; i++) {
            const hour = Math.floor(i / 2);
            const minute = (i % 2) * 30;
            demoTimestamps.push(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
            
            // Generar variación aleatoria pero suave
            const randomChange = (Math.random() - 0.5) * 15;
            const balance = baseValue + randomChange + Math.sin(i / 10) * 20;
            demoBalances.push(Math.max(60, Math.min(140, balance)).toFixed(2));
        }
        
        const option = {
            tooltip: { trigger: 'axis', show: false },
            xAxis: {
                type: 'category',
                data: demoTimestamps,
                boundaryGap: false,
                axisLine: { lineStyle: { color: '#ddd' } },
                axisLabel: { show: true, fontSize: 10, interval: 8 }
            },
            yAxis: {
                type: 'value',
                axisLine: { lineStyle: { color: '#ddd' } },
                axisLabel: { show: false },
                splitLine: { lineStyle: { color: 'rgba(0,0,0,0.05)' } }
            },
            grid: { left: '8%', right: '5%', top: '5%', bottom: '5%', containLabel: false },
            series: [{
                data: demoBalances,
                type: 'line',
                smooth: true,
                lineStyle: { color: 'rgba(255, 121, 7, 0.6)', width: 2.5 },
                itemStyle: { color: 'rgba(255, 121, 7, 0.4)' },
                areaStyle: { color: 'rgba(255, 121, 7, 0.12)' },
                symbolSize: 0,
                symbol: 'none'
            }],
            animation: true
        };
        
        dummyChart.setOption(option);
        window.addEventListener('resize', () => dummyChart.resize());
    } catch (e) {
        console.warn('Error loading dummy balance chart:', e);
    }
}

/**
 * Carga la tabla de operaciones dummy (para usuarios no logueados)
 * Muestra operaciones pero sin valores sensibles (PnL, Capital)
 */
async function loadDummyTopStrategies() {
    try {
        const res = await fetch('/api/top_strategies');
        const data = await res.json();
        const container = document.getElementById('dummyTopStrategiesContainer');
        
        if (!container) return;
        
        if (!data.strategies || data.strategies.length === 0) {
            container.innerHTML = '<p class="text-muted text-center small py-5">Sin operaciones registradas aún</p>';
            return;
        }
        
        container.innerHTML = data.strategies.map((s, idx) => {
            const roiClass = s.roi_annualized >= 0 ? 'text-success' : 'text-danger';
            const pnlSign = s.pnl >= 0 ? '+' : '';
            
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
                            <div class="text-muted small" style="letter-spacing: 2px; font-weight: 600;">${pnlSign}$••••••</div>
                        </div>
                    </div>
                    <div class="strategy-metrics">
                        <div class="strategy-metric">
                            <span class="strategy-metric-label">Capital:</span>
                            <span class="strategy-metric-value text-muted" style="letter-spacing: 1px;">$•••••</span>
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
        console.error("Error loading dummy top strategies:", e);
    }
}

/**
 * Carga dummies cuando el usuario no está logueado
 */
function loadDummyContent() {
    if (!authState.isLogged) {
        loadDummyBalanceChart();
        loadDummyTopStrategies();
    }
}

// Helper temporal para pruebas: permite forzar el estado de autenticación desde la consola
window.__debugToggleAuth = function(forceLogged) {
    console.debug('__debugToggleAuth called with', forceLogged);
    authState.isLogged = !!forceLogged;
    // Forzar visibilidad inmediatamente
    updateConfigSectionsVisibility();
    updateAuthUI();
};
