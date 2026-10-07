"""Python driver for the WCH CH9329F UART-to-USB HID chip.

The package is split into isolated subpackages, one per serial mode:

- :mod:`ch9329f.cfg0`: protocol mode (CFG0). Keyboard/mouse control for work
  modes 0-2 (standard USB HID) plus read-only configuration access.
- :mod:`ch9329f.cfg2`: transparent mode (CFG2). Raw byte pipe for work mode 3
  (custom HID); planned, not implemented yet.

Subpackages never import each other; import the one you need explicitly::

    from ch9329f.cfg0 import CH9329F
"""

__version__ = "0.1.0"
