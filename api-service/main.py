"""ClassFox executable entry point; importing this module starts no services."""

from classfox.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
