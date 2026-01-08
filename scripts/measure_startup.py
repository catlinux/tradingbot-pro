import time
from core.bot import GridBot

start = time.time()
bot = GridBot()
end = time.time()
print('Instanciación GridBot en segundos:', round(end - start, 3))
print('Tiene exchange?:', bool(bot.connector.exchange))
print('Markets loaded:', getattr(bot.connector, '_markets_loaded', False))
