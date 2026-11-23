"""Original Pycom LoPy diagnostic entry point."""
import sys
if '/flash/lib' not in sys.path:
    sys.path.append('/flash/lib')
import config
if config.MODEL_FLAVOR == 'burst':
    from tg_burst_device import main
elif config.MODEL_FLAVOR == 'v4_6':
    from tg_v46_device import main
else:
    raise RuntimeError('Unsupported model flavor')
main()
