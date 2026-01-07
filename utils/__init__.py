# Aquest arxiu fa que la carpeta 'utils' sigui un paquet de Python.
# Importem el logger aquí per facilitar l'accés des d'altres mòduls.

from .logger import log

__all__ = ["log"]