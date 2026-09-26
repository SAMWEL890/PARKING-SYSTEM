# Smart Parking System - Desktop Edition

A single-file desktop app that shows a real window (GUI) instead of
requiring a browser, curl, or a running server. Built with Tkinter,
which ships with Python - there is nothing extra to install.

## How to run

```
python parking_system.py
```

That's it. A window opens with:

1. **Bay Availability** — a live table of all bays and their status
2. **Vehicle Entry** — type a plate number, click "Record Entry" to allocate a bay
3. **Exit / Fee Quote** — type a plate number, click "Get Quote" to see the fee owed
4. **Payment** — pick a payment method, confirm the amount, click to "pay" and free the bay

A `parking.db` SQLite file is created automatically the first time you
run it, seeded with 4 sample bays and the same tiered pricing rules as
the original spec (free under 30 min, Kshs 50 up to 2 hrs, up to Kshs
500 beyond 6 hrs).

## Requirements

- Python 3.8+ with Tkinter (included in the standard Windows/Mac installer;
  on some Linux distros you may need `sudo apt install python3-tk`)

No pip installs, no database server, no browser needed.

## Starting over with a clean database

Delete `parking.db` from the folder and run the app again — it
regenerates itself with fresh sample data.
