# Archivo: utils/auth.py
import hashlib
import secrets
import sqlite3
import os
from datetime import datetime, timedelta
from utils.logger import log

# Archivo de base de datos para usuarios
AUTH_DB = 'data/auth.db'

def init_auth_db():
    """Inicializa la base de datos de autenticación"""
    os.makedirs('data', exist_ok=True)
    
    conn = sqlite3.connect(AUTH_DB)
    cursor = conn.cursor()
    
    # Tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            security_question INTEGER NOT NULL,
            security_answer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    ''')
    
    # Tabla de sesiones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hashea una contraseña"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${password_hash.hex()}"

def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash"""
    try:
        salt, hash_part = password_hash.split('$')
        password_check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return password_check.hex() == hash_part
    except Exception:
        return False

def hash_answer(answer: str) -> str:
    """Encripta la respuesta de seguridad"""
    return hashlib.sha256(answer.lower().strip().encode()).hexdigest()

def verify_answer(answer: str, answer_hash: str) -> bool:
    """Verifica una respuesta de seguridad"""
    return hash_answer(answer) == answer_hash

def user_exists() -> bool:
    """Verifica si existe algún usuario en la BD"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False

def create_user(username: str, email: str, security_question: int, security_answer: str, password: str) -> dict:
    """Crea un nuevo usuario"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        # Verificar que no existe el usuario
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            return {"success": False, "message": "El usuario ya existe"}
        
        # Verificar que no existe otro usuario (solo se permite uno)
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] > 0:
            return {"success": False, "message": "Ya existe un usuario en el sistema"}
        
        # Insertar nuevo usuario
        now = datetime.now().isoformat()
        password_hash = hash_password(password)
        security_answer_hash = hash_answer(security_answer)
        
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, security_question, security_answer, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, email, password_hash, security_question, security_answer_hash, now))
        
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        log.info(f"✓ Usuario '{username}' creado exitosamente")
        
        # Crear sesión
        token = create_session(user_id)
        
        return {
            "success": True,
            "message": "Usuario creado exitosamente",
            "token": token,
            "username": username
        }
    except Exception as e:
        log.error(f"Error creando usuario: {e}")
        return {"success": False, "message": "Error al crear el usuario"}

def authenticate_user(username: str, password: str) -> dict:
    """Autentica un usuario"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return {"success": False, "message": "Usuario o contraseña inválidos"}
        
        user_id, password_hash = result
        
        if not verify_password(password, password_hash):
            return {"success": False, "message": "Usuario o contraseña inválidos"}
        
        # Actualizar último login
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (now, user_id))
        conn.commit()
        conn.close()
        
        # Crear sesión
        token = create_session(user_id)
        
        log.info(f"✓ Usuario '{username}' logueado exitosamente")
        
        return {
            "success": True,
            "message": "Login exitoso",
            "token": token,
            "username": username
        }
    except Exception as e:
        log.error(f"Error autenticando usuario: {e}")
        return {"success": False, "message": "Error al autenticar"}

def create_session(user_id: int) -> str:
    """Crea una sesión para un usuario"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        # Limpiar sesiones expiradas
        now = datetime.now().isoformat()
        cursor.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
        
        # Crear nueva sesión (válida por 30 días)
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        
        cursor.execute('''
            INSERT INTO sessions (user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, token, now, expires_at))
        
        conn.commit()
        conn.close()
        
        return token
    except Exception as e:
        log.error(f"Error creando sesión: {e}")
        return None

def verify_session(token: str) -> dict:
    """Verifica una sesión"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute('''
            SELECT u.id, u.username FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
        ''', (token, now))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {"success": True, "user_id": result[0], "username": result[1]}
        return {"success": False}
    except Exception:
        return {"success": False}


def get_user_by_id(user_id: int) -> dict:
    """Obtiene información básica del usuario (username, email) por user_id"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT username, email FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"success": True, "username": row[0], "email": row[1]}
        return {"success": False}
    except Exception as e:
        log.error(f"Error obteniendo usuario por id {user_id}: {e}")
        return {"success": False}
def get_security_question(username: str) -> dict:
    """Obtiene la pregunta de seguridad de un usuario"""
    questions = {
        1: "¿Cuál es el nombre de tu primer mascota?",
        2: "¿En qué ciudad naciste?",
        3: "¿Cuál es tu película favorita?",
        4: "¿Cuál es el apellido de tu madre?",
        5: "¿Cuál fue tu primer trabajo?"
    }
    
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        cursor.execute('SELECT security_question FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            q_num = result[0]
            return {
                "success": True,
                "question": questions.get(q_num, "Pregunta no encontrada"),
                "username": username
            }
        return {"success": False, "message": "Usuario no encontrado"}
    except Exception as e:
        log.error(f"Error obteniendo pregunta: {e}")
        return {"success": False, "message": "Error al obtener la pregunta"}

def reset_password(username: str, security_answer: str) -> dict:
    """Resetea la contraseña usando la pregunta de seguridad"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        cursor.execute('SELECT security_answer FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        
        if not result:
            return {"success": False, "message": "Usuario no encontrado"}
        
        if not verify_answer(security_answer, result[0]):
            return {"success": False, "message": "Respuesta de seguridad incorrecta"}
        
        # Generar nueva contraseña temporal
        temp_password = secrets.token_urlsafe(12)
        password_hash = hash_password(temp_password)
        
        cursor.execute('UPDATE users SET password_hash = ? WHERE username = ?', (password_hash, username))
        conn.commit()
        conn.close()
        
        log.info(f"✓ Contraseña de '{username}' reseteada")
        
        return {
            "success": True,
            "message": f"Tu nueva contraseña temporal es: {temp_password}\nCámbiala cuando inicies sesión."
        }
    except Exception as e:
        log.error(f"Error reseteando password: {e}")
        return {"success": False, "message": "Error al resetear la contraseña"}

def invalidate_session(token: str):
    """Invalida una sesión (logout)"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Error invalidando sesión: {e}")

def update_password(username: str, new_password: str) -> dict:
    """Actualiza la contraseña de un usuario"""
    try:
        conn = sqlite3.connect(AUTH_DB)
        cursor = conn.cursor()
        
        # Verificar que el usuario existe
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return {"success": False, "message": "Usuario no encontrado"}
        
        # Actualizar contraseña
        password_hash = hash_password(new_password)
        cursor.execute('UPDATE users SET password_hash = ? WHERE username = ?', (password_hash, username))
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "Contraseña actualizada correctamente"}
    except Exception as e:
        log.error(f"Error actualizando contraseña: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

