#!/usr/bin/env python

import argparse
import math
import numpy
import random
import time
import walle

class Fader:
    def __init__(self):
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
        # the contrast looks cooler when most faders are dark
        return max(random.uniform(-2, 1), 0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    rows, cols = driver.dim()
    faders = [[Fader() for _ in range(cols)] for _ in range(rows)]
    while True:
        now = time.time()
        driver.set([[tuple(f.get(now) for _ in range(3)) for f in row] for row in faders])
        time.sleep(0.02)
