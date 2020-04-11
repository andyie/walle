#!/usr/bin/python

import time
import math
import walle

if __name__ == '__main__':
    w = walle.WallE(0, 0)
    w.array.autoupdate = False
    w.array.clear()
    w.array.update()
    time.sleep(0.5)
    for led in reversed(w.array.leds):
        led.red = 1.0
        led.green = 1.0
        led.blue = 1.0
        w.array.update()
        time.sleep(0.1)
    w.array.update()
