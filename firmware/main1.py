import machine
import time
import pycom

# Wyłączenie migającej diody i opóźnienie na złapanie konsoli (zmniejszyłem do 2 sekund)
time.sleep(2)  
pycom.heartbeat(False)
pycom.rgbled(0x000000)

print("\n--- Start programu LoPy ---")

# Odczyt taktowania (bez jego zmiany)
current_freq = machine.freq() // 1000000
print("Taktowanie procesora: {} MHz".format(current_freq))

# Testowanie Light Sleep (Płytki sen)
print("Wchodzę w Light Sleep na 3 sekundy...")
time.sleep(0.1) 

machine.sleep(3000) # Usypia na 3000 ms
print("Wybudzono z Light Sleep!")

# Testowanie Deep Sleep (Głęboki sen)
print("Wchodzę w Deep Sleep na 5 sekund...")
time.sleep(0.1)

# Płytka po wybudzeniu z deepsleep wykona twardy reset
machine.deepsleep(5000) 

print("Tego tekstu nigdy nie zobaczysz")