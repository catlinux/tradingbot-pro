// auth.js - Gestión de autenticación del bot

// Estado global de autenticación
let authState = {
    isLogged: false,
    username: null,
    token: null
};

/**
 * Inicializa el estado de autenticación al cargar la página
 */
async function initAuthSystem() {
    try {
        // Verificar si ya hay sesión activa en sessionStorage
        const storedToken = sessionStorage.getItem('auth_token');
        const storedUsername = sessionStorage.getItem('auth_username');
        
        if (storedToken && storedUsername) {
            authState.isLogged = true;
            authState.username = storedUsername;
            authState.token = storedToken;
            updateAuthUI();
        } else {
            // Verificar si hay usuario creado
            const checkResponse = await fetch('/api/auth/check-user');
            const checkData = await checkResponse.json();
            updateAuthUI(checkData.userExists);
        }
    } catch (error) {
        console.error('Error al inicializar autenticación:', error);
        updateAuthUI(false);
    }
}

/**
 * Actualiza la interfaz de usuario según el estado de autenticación
 */
function updateAuthUI(userExists = null) {
    const btnLogin = document.getElementById('btn-login');
    const btnCreateUser = document.getElementById('btn-create-user');
    const btnRecovery = document.getElementById('btn-recovery');
    const authLogged = document.getElementById('auth-logged');
    const loggedUsername = document.getElementById('logged-username');
    const configUsername = document.getElementById('config-username');
    const configLoginStatus = document.getElementById('config-login-status');
    
    if (authState.isLogged) {
        // Usuario logueado
        if (btnLogin) btnLogin.classList.add('d-none');
        if (btnCreateUser) btnCreateUser.classList.add('d-none');
        if (btnRecovery) btnRecovery.classList.add('d-none');
        if (authLogged) authLogged.classList.add('active');
        if (loggedUsername) loggedUsername.textContent = authState.username;
        
        // Actualizar tarjeta de usuario
        if (configUsername) configUsername.textContent = authState.username;
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
            // Usuario existe pero no está logueado
            if (btnLogin) {
                btnLogin.classList.remove('d-none');
            }
            if (btnCreateUser) btnCreateUser.classList.add('d-none');
            if (btnRecovery) {
                btnRecovery.classList.remove('d-none');
            }
            
            // Actualizar tarjeta de usuario
            if (configUsername) configUsername.textContent = 'Sin sesión iniciada';
            if (configLoginStatus) {
                configLoginStatus.textContent = 'No logueado';
                configLoginStatus.style.color = '#f59e0b';
            }
        } else {
            // No existe usuario - mostrar crear
            if (btnLogin) btnLogin.classList.add('d-none');
            if (btnCreateUser) {
                btnCreateUser.classList.remove('d-none');
            }
            if (btnRecovery) btnRecovery.classList.add('d-none');
            
            // Actualizar tarjeta de usuario
            if (configUsername) configUsername.textContent = 'No hay usuario creado';
            if (configLoginStatus) {
                configLoginStatus.textContent = '--';
                configLoginStatus.style.color = '#6b7280';
            }
        }
        
        // Ocultar pestañas sensibles
        hideRestrictedTabs();
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
 * REGLA POTENTE Y MODULAR: Controla automáticamente la visibilidad de elementos
 * basándose en el estado de login del usuario
 * 
 * Uso: Añade la clase "auth-required" a cualquier elemento que quieras ocultar
 * cuando el usuario NO esté logueado. Se mostrará automáticamente cuando inicie sesión.
 */
function updateConfigSectionsVisibility() {
    // Obtener todos los elementos que requieren autenticación
    const authRequiredElements = document.querySelectorAll('[data-auth-required="true"]');
    
    if (authState.isLogged) {
        // Usuario logueado: mostrar elementos sensibles
        authRequiredElements.forEach(element => {
            element.classList.remove('d-none');
        });
    } else {
        // Usuario NO logueado: ocultar elementos sensibles
        authRequiredElements.forEach(element => {
            element.classList.add('d-none');
        });
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
            
            // Guardar en sessionStorage
            sessionStorage.setItem('auth_token', data.token);
            sessionStorage.setItem('auth_username', username);
            
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
            
            // Guardar en sessionStorage
            sessionStorage.setItem('auth_token', data.token);
            sessionStorage.setItem('auth_username', username);
            
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
                
                // Limpiar sessionStorage
                sessionStorage.removeItem('auth_token');
                sessionStorage.removeItem('auth_username');
                
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
    document.getElementById('tab-operaciones').parentElement.classList.remove('d-none');
    document.getElementById('tab-wallet').parentElement.classList.remove('d-none');
    document.getElementById('tab-estrategias').parentElement.classList.remove('d-none');
}

/**
 * Oculta las pestañas restringidas (usuario no logueado)
 */
function hideRestrictedTabs() {
    document.getElementById('tab-operaciones').parentElement.classList.add('d-none');
    document.getElementById('tab-wallet').parentElement.classList.add('d-none');
    document.getElementById('tab-estrategias').parentElement.classList.add('d-none');
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
