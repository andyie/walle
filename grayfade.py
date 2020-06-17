#!/usr/bin/env python

import argparse
import colour
import math
import numpy
import random
import time
import walle

class ColorFader:
    def __init__(self, rgb0, rgb1, t):
        self._rgb_faders = [Fader(rgb0[i], rgb1[i], t) for i in range(3)]

    def get(self, now):
        return tuple(f.get(now) for f in self._rgb_faders)

    def set(self, c, t):
        for f, ch in zip(self._rgb_faders, c):
            f.set(ch, t)

    def done(self):
        return all (f.done() for f in self._rgb_faders)

    def get_color_range(self):
        v_ranges = [f.get_v_range() for f in self._rgb_faders]
        return (tuple(v_range[0] for v_range in v_ranges),
                tuple(v_range[1] for v_range in v_ranges))

class Fader:
    def __init__(self, v0, v1, t):
        self._v = v0
        self._v0 = v0
        self._v1 = v1
        self._t = t
        self._t0 = None
        self._t1 = None
        self._done = False

    def get(self, now):
        # time is initialized on first call
        if self._t0 is None:
            assert self._t1 is None
            self._t0 = now
            self._t1 = now + self._t

        if now >= self._t1:
            self._done = True

        # interpolate
        self._v = numpy.interp([now], [self._t0, self._t1], [self._v0, self._v1])[0]
        return self._v

    def set(self, v, t):
        self._v0 = self._v
        self._v1 = v
        self._t = t
        self._t0 = None
        self._t1 = None
        self._done = False

    def done(self):
        return self._done

    def get_v_range(self):
        return (self._v0, self._v1)

class RandomFader:
    def __init__(self, lo=0., hi=1., min_t=1., max_t=3.):
        """
        lo and hi choose the fade range. returned values are clamped to [0, 1], so this provides a
        way for the fader to be frequently off or on
        """
        self._lo = lo
        self._hi = hi
        self._min_t = min_t
        self._max_t = max_t
        assert self._lo <= self._hi
        self._color_fader = ColorFader((0., 0., 0.),
                                       self._random_color(),
                                       self._random_t())

    def get(self, now):
        # choose a new color if necessary
        if self._color_fader.done():
            self._color_fader.set(self._random_color(), self._random_t())

        # interpolate
        return self._color_fader.get(now)

    def _random_t(self):
        return random.uniform(self._min_t, self._max_t)

    def _random_color(self):
        def rand_v():
            return min(1., max(0., random.uniform(self._lo, self._hi)))
        return tuple([rand_v()] * 3)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    rows, cols = driver.dim()
    faders = [[RandomFader(-2.0, 1.0) for _ in range(cols)] for _ in range(rows)]
    period = walle.PeriodFloor(0.05)
    while True:
        now = time.time()
        driver.set([[color.get(now) for color in row] for row in faders])
        period.sleep()
