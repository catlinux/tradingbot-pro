# Scripts

Development helper scripts:

- `start-dev.ps1` (PowerShell): activa el virtualenv y ejecuta `scripts/watcher_restart.py` que reinicia `python main.py` cuando detecta cambios en archivos `.py`, `.json`, `.json5`, `.html`, `.css`, `.js` en los directorios `.` `core` `web` `utils` `config` `data`.

  Uso (PowerShell):
  ```powershell
  . .\.venv\Scripts\Activate.ps1
  ./scripts/start-dev.ps1
  ```

- `start-dev.bat` (CMD): hace lo mismo para entornos CMD.

- `watcher_restart.py`: watcher en Python (usa `watchdog`) que lanza `python main.py` y lo reinicia al detectar cambios. Se puede pasar un comando alternativo con `--cmd`.

Dependencias:
- `watchdog` (añadido a `requirements.txt`)

Notas:
- Evita usar `--reload --workers > 1` si confías en variables globales para estado del bot.
- El watcher intenta ignorar `.venv`, `.git` y `__pycache__`.
