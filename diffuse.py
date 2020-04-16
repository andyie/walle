#!/usr/bin/env python

import argparse
import colour
import copy
import math
import random
import statistics
import time
import walle

class Diffuse:
    DIFFUSION_HALF_LIFE_S = 2
    MAX_SPLASH_PERIOD = 5

    def __init__(self, driver):
        self._driver = driver
        self._matrix = walle.all_off_matrix(driver.dim())

        # figure the diffusion rate from its desired half-life. note that since diffusion is color
        # quantity-conservative, it doesn't (i think?) impact the math for managing brightness decay
        # below.
        self._diffusion_rate = math.log(2.) / Diffuse.DIFFUSION_HALF_LIFE_S

        # figure the decay rate from the desired steady-state channel brightness. the issue
        # identified here is that if the decay rate is too low, the quantity of color in the display
        # will rise until the display saturates. the goal is to keep the "steady state" per-channel
        # color quantity in each pixel below some target value.
        #
        # suppose a pixel color channel is increased by x every t seconds. then it's brightness
        # after infinite time just before (note i starts from 1 not 0) the next addition is:
        #
        #    inf
        #   SIGMA (x * e^-rti)
        #    i=1
        #
        # this is a geometric series, so its sum is x / (1 - e^-rt) - x. note that this sum is
        # always finite, so the steady-state brightness always converges. the issue is that it may
        # converge to a value brighter than the display can show, causing saturation. therefore, the
        # goal is to keep this sum below some target threshold S.
        #
        #   x / (1 - e^-rt) - x < S
        #
        #   r < -ln(1 - x / (S + x)) / t
        #
        # of course, t is random. but on average, it should be the expected value of the update time
        # (one half the configured max splash delay time) times the probability that this pixel is
        # updated times the probability this channel is updated.
        #
        # note: this math gets easier if channels are simply paved over, because then their history
        # is effectively deleted
        #
        # on a 10x10 display, it turns out the average random rectangle has area 16. this can be
        # confirmed by enumerating all possible rectangles and averaging their areas:
        #
        #    10    10
        #   SIGMA SIGMA i * j * (10 - i - 1) * (10 - j - 1)
        #    i=1   j=1
        #   ----------------------------------------------- = 16
        #        10    10
        #       SIGMA SIGMA (10 - i - 1) * (10 - j - 1)
        #        i=1   j=1
        #
        # the numerater "i * j" gives the area of the rectangle, and its coefficient gives the
        # number of locations that rectangle can be installed. the denominator is just the total
        # number of rectangles. the result 16 was confirmed with a monte-carlo.
        #
        # okay, so t can be fudge-stimated with:
        #
        #   t ~= (max_delay / 2) / (16 / 100) / (1 / 3)
        #
        # the 1/3 at the end is correct only if we only set primary (one-channel) colors. in
        # practice x is 1.0, since we splash colors full-brightness. choose some relatively-low S so
        # that the display is dim most of the time. that gives it a nice dynamic range when the
        # splashes appear
        approx_t = 0.5 * Diffuse.MAX_SPLASH_PERIOD / (16. / 100) / (1. / 3)
        x = 1.0
        S = 0.05
        self._decay_rate = -math.log(1 - x / (S + x)) / approx_t
        print('decay rate: ', self._decay_rate)
        assert self._decay_rate < 0.5 # arbitrary sanity-check

        self._brightness_stats = walle.Stats('channel brightness', walle.log)

        self._last_update_time = None
        self._next_splash_time = None

    def update(self):
        now = time.perf_counter()
        if self._last_update_time is None:
            self._last_update_time = now
            self._next_splash_time = now
        elapsed = now - self._last_update_time

        self._matrix = self._decayed(self._diffused(self._matrix, elapsed), elapsed)
        assert self._matrix
        if now >= self._next_splash_time:
            self._matrix = self._splashed(self._matrix)
            self._next_splash_time = now + random.uniform(0., Diffuse.MAX_SPLASH_PERIOD)

        self._driver.set(self._matrix)
        self._brightness_stats.sample(statistics.mean(ch for row in self._matrix
                                                        for col in row for ch in col))

        self._last_update_time = now

    def _diffused(self, matrix, elapsed):
        # figure the diffusion coefficient from the elapsed time
        w = math.exp(-self._diffusion_rate * elapsed)
        assert w >= 0. and w <= 1.

        # let each pixel retain "weight" of its own color and obtain "weight"/4 from each of its
        # neighbors. this should effectively conserve the quantity of each color on the display.
        # boundary pixels are provided themselves as neighbors in boundary directions.
        #
        # the diffused channel values are clamped to 1. just in case numerical error makes them a
        # hair above 1. sometimes
        num_cols, num_rows = self._driver.dim()
        def diffused_pixel(col, row):
            p = matrix[row][col]
            neighs = [matrix[max(min(row + i, num_rows - 1), 0)][max(min(col + j, num_cols - 1), 0)]
                        for i, j in [(-1, 0), (0, 1), (1, 0), (0, -1)]]
            return tuple(min(w * p[i] + (1. - w) * sum(n[i] for n in neighs) / len(neighs), 1.)
                        for i in range(3))
        return [[diffused_pixel(col, row) for col in range(num_cols)] for row in range(num_rows)]

    def _decayed(self, matrix, elapsed):
        # figure the decay coefficient from the elapsed time
        w = math.exp(-self._decay_rate * elapsed)
        assert w >= 0. and w <= 1.

        # decay all the pixels
        num_cols, num_rows = self._driver.dim()
        return [[tuple(w * ch for ch in matrix[row][col]) for col in range(num_cols)]
                    for row in range(num_rows)]

    def _splashed(self, matrix):
        # choose random coordinates for a rectangle to splash to the display
        num_cols, num_rows = self._driver.dim()
        rows = sorted(random.sample(range(num_rows + 1), 2))
        cols = sorted(random.sample(range(num_cols + 1), 2))
        color = self._get_random_color()
        walle.log.info('splashing {} from ({}, {}) to ({}, {})'.format(color,
            rows[0], cols[0], rows[1] - 1, cols[1] - 1))

        # note: splashes below are added, but they could also just pave over the existing values.
        # this will make the display overall slightly dimmer, because existing brightness is removed
        return [[tuple(min(x + y, 1.) for x, y in zip(matrix[row][col], (0, 0, 0) if
                        (row not in range(*rows) or col not in range(*cols)) else color.rgb))
                    for col in range(num_cols)]
                        for row in range(num_rows)]

    def _get_random_color(self):
        colors = ['red', 'green', 'blue']
        return colour.Color(random.choice(colors))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    diffuse = Diffuse(driver)
    period = walle.PeriodFloor(0.05)
    while True:
        diffuse.update()
        period.sleep()
