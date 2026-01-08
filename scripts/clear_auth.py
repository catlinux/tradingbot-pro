import sqlite3
import os

AUTH_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'auth.db')
AUTH_DB = os.path.abspath(AUTH_DB)

if not os.path.exists(AUTH_DB):
    print(f"Auth DB no encontrada en: {AUTH_DB}")
    raise SystemExit(0)

print(f"Conectando a Auth DB: {AUTH_DB}")
conn = sqlite3.connect(AUTH_DB)
cur = conn.cursor()

# Vaciar users y sessions
for t in ('sessions', 'users'):
    try:
        cur.execute(f"SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name=?", (t,))
        if cur.fetchone()[0] == 0:
            print(f"Tabla {t} no existe, saltando")
        else:
            cur.execute(f"DELETE FROM {t}")
            print(f"Borradas filas de {t}")
    except Exception as e:
        print(f"Error borrando {t}: {e}")

conn.commit()
conn.close()
print('Operación completada')
