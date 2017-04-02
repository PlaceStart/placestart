import logging
import PIL.Image
import random
import requests.adapters
import time
import urllib.request

import fire

colormap = {
    'white': (255, 255, 255),
    'lightgray': (228, 228, 228),
    'darkgray': (136, 136, 136),
    'black': (34, 34, 34),
    'lightpink': (255, 167, 209),
    'red': (229, 0, 0),
    'orange': (229, 149, 0),
    'brown': (160, 106, 66),
    'yellow': (229, 217, 0),
    'lightgreen': (148, 224, 68),
    'green': (2, 190, 1),
    'cyan': (0, 211, 221),
    'grayblue': (0, 131, 199),
    'blue': (0, 0, 234),
    'pink': (207, 110, 228),
    'purple': (130, 0, 128),

    'dummy': (54, 199, 57)
}
mapcode = {
        (255, 255, 255): 0,
        (228, 228, 228): 1,
        (136, 136, 136): 2,
        (34, 34, 34): 3,
        (255, 167, 209): 4,
        (229, 0, 0): 5,
        (229, 149, 0): 6,
        (160, 106, 66): 7,
        (229, 217, 0): 8,
        (148, 224, 68): 9,
        (2, 190, 1): 10,
        (0, 211, 211): 11,
        (0, 131, 199): 12,
        (0, 0, 234): 13,
        (207, 110, 228): 14,
        (130, 0, 128): 15
}
mapcolor = {v: k for k, v in colormap.items()}
codemap = {v: k for k, v in mapcode.items()}

class PlacestartMonitor:
    def __init__(self, username, password, debug=False):
        logging.basicConfig(level=logging.INFO if not debug else logging.DEBUG)
        self._username = username
        self._password = password
        self._board = None
        self._target = None
        self._diff = []
        self._intent = None
        self._wait = None
    
    def update_template(self):
        template_url = "https://github.com/PlaceStart/placestart/raw/master/target.png"
        urllib.request.urlretrieve(template_url, "target.png")
        return

    def load_target(self):
        self._target = PIL.Image.open('target.png').convert('RGB')
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
        board_image.putpalette(sum(colormap.values(), ()))
        
        pixels = board_image.load()
        for i in range(4): next(board_bytes)
        for y in range(1000):
            for x in range(500):
                datum = next(board_bytes)
                color1 = datum >> 4
                color2 = datum - (color1 << 4)
                pixels[x*2    , y] = color1
                pixels[x*2 + 1, y] = color2
        
        board_image.save('board.bmp')
        
        self._board = board_image.convert('RGB')
        return
    
    def get_diff(self):
        width, height = self._target.size

        start_region = self._board.crop(box=(0,1000-height,width,1000))
        assert width, height == start_region.size
        start_region.save('actual.bmp')

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
        self._intent = None
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
            except:
                logging.warn("Something went wrong, restarting bot.")
                self.cleanup()
                


if __name__ == "__main__":
    fire.Fire(PlacestartMonitor)
