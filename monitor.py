import logging
import PIL.Image
import random
import requests.adapters
import time
import urllib.request
import json

import fire

from colors import colormap, mapcolor, codemap, mapcode, pallete


class PlacestartMonitor:
    def __init__(self, debug=False):
        logging.basicConfig(level=logging.INFO if not debug else logging.DEBUG)
        with open('config.json') as user_config:    
            data = json.load(user_config)
        self._username = data['username']
        self._password = data['password']
        self._board = None
        self._target = None
        self._diff = []
        self._wait = None

    def update_template(self):
        template_url = "https://raw.githubusercontent.com/PlaceStart/placestart/master/template.png"
        urllib.request.urlretrieve(template_url, "template.png")
        return

    def load_target(self):
        self._target = PIL.Image.open('template.png').convert('RGB')
        width, height = self._target.size

        target_pixels = self._target.load()
        for i in range(width):
            for j in range(height):
                pixel = target_pixels[i,j]
                if pixel not in colormap.values():
                    raise RuntimeError("Target pixel not expected: {} at {}".format(pixel, (i,j)))
        return

    def get_board(self):
        board_url = 'https://www.reddit.com/api/place/board-bitmap'
        board_bytes = iter(urllib.request.urlopen(board_url).read())
        board_image = PIL.Image.new('P', (1000,1000))
        board_image.putpalette(pallete)

        pixels = board_image.load()
        for i in range(4): next(board_bytes)
        for y in range(1000):
            for x in range(500):
                datum = next(board_bytes)
                color1 = datum >> 4
                color2 = datum - (color1 << 4)
                pixels[x*2    , y] = color1
                pixels[x*2 + 1, y] = color2

        self._board = board_image.convert('RGB')
        return

    def get_diff(self):
        width, height = self._target.size

        start_region = self._board.crop(box=(0,1000-height,width,1000))
        assert width, height == start_region.size

        target_pixels = self._target.load()
        actual_pixels = start_region.load()

        for i in range(width):
            for j in range(height):
                if (target_pixels[i,j] != actual_pixels[i,j] and
                    mapcolor[target_pixels[i,j]] != 'dummy'):
                    self._diff.append((i,j))
        logging.info("Different pixels counted {}".format(
            len(self._diff)
        ))
        return

    def fix_something(self):
        # randomly choose, but among the leftmost ones
        width, height = self._target.size
        (x, y) = coord = random.choice(self._diff[:25])
        y += 1000-height

        new_color = self._target.load()[coord]
        logging.info("Target pixel {} will be painted {}".format(
            (x,y) , mapcolor[new_color]
        ))

        session = requests.Session()
        session.mount('https://www.reddit.com', requests.adapters.HTTPAdapter(max_retries=5))
        session.headers["User-Agent"] = "PlacePlacer"
        auth_request = session.post(
            "https://www.reddit.com/api/login/{}".format(self._username),
            data={"user": self._username, "passwd": self._password, "api_type": "json"}
        )
        try:
           session.headers['x-modhash'] = auth_request.json()["json"]["data"]["modhash"]
        except:
            logging.error("Authentication failed for user {}".format(self._username))
            return

        # Is the target still wrong?
        while True:
            probe_request = session.get(
                "http://reddit.com/api/place/pixel.json?x={}&y={}".format(x, y),
                timeout=5
            )
            if probe_request.status_code == 200:
                data = probe_request.json()
                logging.debug("Probe response: %s" % data)
                break
            else:
                logging.warn("Probling failed with %s: %s", probe_request, probe_request.text)
                time.sleep(1)

        old_color = codemap[data["color"]]
        if new_color == old_color:
            logging.info("Target pixel was already fixed")
            return

        # Draw it!
        draw_request = session.post(
            "https://www.reddit.com/api/place/draw.json",
            data={"x": str(x), "y": str(y), "color": str(mapcode[new_color])}
        )
        logging.debug("Draw response: %s" % draw_request.json())

        if "error" not in draw_request.json():
            logging.info("Placed color!")
            self._wait = 300
        else:
            logging.info("Something went wrong, trying again later (Probably cooldown).")
            self._wait = 1

        if "wait_seconds" in draw_request.json():
            self._wait = float(draw_request.json()["wait_seconds"])
            logging.info("On cooldown, waiting {} seconds".format(self._wait))

        return

    def wait(self):
        if self._wait:
            time.sleep(self._wait)
        self._wait = None

    def cleanup(self):
        self._board = None
        self._target = None
        self._diff = []
        self._wait = None

    def maintenance(self):
        while True:
            try:
                self.update_template()
                self.load_target()
                self.get_board()
                self.get_diff()
                self.fix_something()
                self.wait()
                self.cleanup()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.warn("Something went wrong, restarting bot Cause: %s." % e)
                self.cleanup()



if __name__ == "__main__":
    fire.Fire(PlacestartMonitor)
