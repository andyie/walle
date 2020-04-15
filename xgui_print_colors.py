#!/usr/bin/env python

import colour
import random
import walle
from xgui_scrolltext import Scroller

if __name__ == "__main__":
    scroller = Scroller(continuous=False)
    period = walle.PeriodFloor(0.01)
    while True:
        color = random.choice(list(colour.COLOR_NAME_TO_RGB.keys()))
        walle.log.info('showing {}'.format(color))
        scroller.set_text(color, color)
        while not scroller.is_done():
            scroller.update()
            period.sleep()
