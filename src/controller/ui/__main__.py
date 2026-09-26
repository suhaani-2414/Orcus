"""`python -m controller.ui` — run the live status dashboard in demo mode.

Also works in a browser: `textual serve "python -m controller.ui"`.
"""

from controller.ui.status import StatusApp

if __name__ == "__main__":
    StatusApp(demo=True).run()
