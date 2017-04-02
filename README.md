# /r/placestart defender

To run this painter bot, you must have python and pip installed.

0. Make sure Python3 and pip are installed

    `python --version` should output python 3.x
    `pip --version` should output whatever, just not an error

1. Download the bot folder and open a terminal inside it.

2. Install the requirements:

    `pip install -r requirements.txt`

3. Run the bot in permanent maintenance mode

    `python monitor.py --username youruser --password yourpass maintenance`

Don't worry, the bot respects the indicated cooldown between drawings.
The code is contained in a single file, so you can see that I won't send your credentials anywhere except Reddit's API. Also, there's no self-updating component except it tries to update the `target.png` at every run.
