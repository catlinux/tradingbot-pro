import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bot_data.db')
DB_PATH = os.path.abspath(DB_PATH)

if not os.path.exists(DB_PATH):
    print(f"DB no encontrada en: {DB_PATH}")
    sys.exit(0)

print(f"Conectando a DB: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def safe_delete(table):
    try:
        cur.execute(f"SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if cur.fetchone()[0] == 0:
            print(f"Tabla {table} no existe, saltando")
            return
        cur.execute(f"DELETE FROM {table}")
        print(f"Borradas filas de {table}")
    except Exception as e:
        print(f"Error borrando {table}: {e}")

# Tablas a limpiar (dejamos solo trade_history)
safe_delete('balance_history')
safe_delete('exchanges')
# Limpiar tablas auxiliares que no queremos en la instalación limpia
safe_delete('market_data')
safe_delete('grid_status')
safe_delete('bot_info')
# NOTA: No borramos 'trade_history' porque la queremos conservar como ejemplo (Top Operaciones)

conn.commit()
print("Commit realizado. Ejecutando VACUUM...")
try:
    cur.execute('VACUUM')
    conn.commit()
    print('VACUUM completado')
except Exception as e:
    print('VACUUM falló:', e)

conn.close()
print('Operación completada')
