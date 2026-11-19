"""Original Pycom LoPy: diagnostics for v4.6 ONLY. No GPIO alarms."""
import sys
if '/flash/lib' not in sys.path:
    sys.path.append('/flash/lib')
import config
if config.MODEL_FLAVOR != 'v4_6':
    raise RuntimeError('Only model flavor v4_6 is supported by this firmware')
from tg_v46_device import main
main()
