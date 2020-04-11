#!/usr/bin/python

import math
import random
import time
import walle

class Fader:
    def __init__(self, led, initial_time):
        self._led = led
        self._begin_time = initial_time
        self._begin_val = self._choose_new_color()
        self._end_val = self._choose_new_color()
        self._fade_time = self._choose_new_fade_time()

        self._set(self._begin_val)

    def update(self, current_time):
        # choose a new target if the time has elapsed. we shouldn't have fallen
        # behind by more than a full cycle.
        elapsed = current_time - self._begin_time
        if elapsed >= self._fade_time:
            assert elapsed < 2 * self._fade_time
            elapsed -= self._fade_time
            self._begin_time += self._fade_time
            self._begin_val = self._end_val
            self._end_val = self._choose_new_color()
            self._fade_time = self._choose_new_fade_time()

        # linearly interpolate to the new value
        val = self._begin_val + (self._end_val - self._begin_val) * elapsed / self._fade_time
        self._set(val)
        
    def _choose_new_fade_time(self):
        return 3 * random.random() + 1

    def _choose_new_color(self):
        return max(random.random() * 3 - 2.0, 0)

    def _set(self, brightness):
        self._led.red = brightness
        self._led.green = brightness
        self._led.blue = brightness

if __name__ == '__main__':
    w = walle.WallE(0, 0)
    w.array.autoupdate = False

    now = time.time()
    faders = [Fader(walle.PrettyLed(led), now) for led in w.array.leds]
    while True:
        time.sleep(0.05)
        now = time.time()
        for fader in faders:
            fader.update(now)
        w.array.update()
