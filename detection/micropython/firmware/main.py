"""Pycom LoPy: this file is automatically executed from /flash/main.py."""
import sys
if '/flash/lib' not in sys.path:
    sys.path.append('/flash/lib')

from tg_device import main
main()
