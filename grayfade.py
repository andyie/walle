#!/usr/bin/env python

import argparse
import math
import numpy
import random
import time
import walle

class Fader:
    def __init__(self, lo=0., hi=1.):
        """
        lo and hi choose the fade range. returned values are clamped to [0, 1], so this provides a
        way for the fader to be frequently off or on
        """
        self._lo = lo
        self._hi = hi
        assert self._lo <= self._hi
        self._t0 = None
        self._t1 = None
        self._v0 = self._random_v()
        self._v1 = self._random_v()

    def get(self, now):
        # time is initialized on first call
        if self._t0 is None:
            assert self._t1 is None
            self._t0 = now
            self._t1 = now + self._random_t()

        # choose a new color if necessary
        if now > self._t1:
            self._t0 = self._t1
            self._t1 = self._t1 + self._random_t()
            self._v0 = self._v1
            self._v1 = self._random_v()
            assert now <= self._t1

        # interpolate
        v = numpy.interp([now], [self._t0, self._t1], [self._v0, self._v1])[0]
        return v
        
    def _random_t(self):
        return random.uniform(1, 3)

    def _random_v(self):
        return min(1., max(0., random.uniform(self._lo, self._hi)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    rows, cols = driver.dim()
    faders = [[tuple(Fader(-10.0, 1.0) for _ in range(3)) for _ in range(cols)] for _ in range(rows)]
    period = walle.PeriodFloor(0.05)
    while True:
        now = time.time()
        driver.set([[tuple(f.get(now) for f in col) for col in row] for row in faders])
        period.sleep()
