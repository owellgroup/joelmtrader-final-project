MT5 BRIDGE - INSTALL ONCE, RUNS FOREVER
=======================================
1. Keep this folder together. Double-click INSTALL.bat and click Yes.
   (It installs Python if missing, sets up the bridge, and makes it start
   automatically every time you log in to Windows. No window stays open.)
2. Open MetaTrader 5, log in, and make sure Algo Trading is GREEN
   (Tools > Options > Expert Advisors > Allow algorithmic trading).
3. In the app press Connect MT5 (once). Done.

Check it works:  double-click VIEW-LOG.bat, you should see
"Connected to the server."
Remove it:       UNINSTALL.bat

Important: it starts when you LOG IN to Windows (MT5 is a desktop program and
needs your desktop session). To make it fully automatic after a power cut or
restart, set Windows to log in by itself: press Win+R, type netplwiz, untick
"Users must enter a user name and password", press OK. Also set
Settings > Power > Sleep to "Never" while plugged in.
