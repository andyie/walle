#!/usr/bin/env python

import argparse
import colour
import copy
import math
import numpy
import random
import statistics
import time
import walle

class Splasher:
    def __init__(self, num_cols, num_rows):
        # choose random coordinates for a rectangle to splash to the display.
        #
        # hack: restrict rectangle size. dirty hack, originally didn't want to restrict
        self._dim = (num_cols, num_rows)
        self._splash_cols, self._splash_rows, splash_dim = self._get_splash_zone()
        while splash_dim[0] * splash_dim[1] > 21: # allow 3x7 but not 4x6
            self._splash_cols, self._splash_rows, splash_dim = self._get_splash_zone()
        self._splash_color = self._get_random_color()
        self._total_splash_time = random.uniform(1., 10.)
        self._total_elapsed = 0

        walle.log.info('splashing {} from ({}, {}) to ({}, {}) over {:.1f} seconds'.format(
            self._splash_color, self._splash_rows[0], self._splash_cols[0],
            self._splash_rows[1] - 1, self._splash_cols[1] - 1, self._total_splash_time))

    def update(self, matrix, elapsed):
        self._total_elapsed += elapsed
        if self._total_elapsed > self._total_splash_time:
            elapsed -= (self._total_elapsed - self._total_splash_time)
            self._total_elapsed = self._total_splash_time
        assert elapsed >= 0

        ratio = elapsed / self._total_splash_time
        add = tuple(ch * ratio for ch in self._splash_color.rgb)
        for row in range(*self._splash_rows):
            for col in range(*self._splash_cols):
                matrix[row][col] = tuple(min(x + y, 1.) for x, y in zip(matrix[row][col], add))

    def is_done(self):
        return self._total_elapsed >= self._total_splash_time

    def _get_splash_zone(self):
        cols = sorted(random.sample(range(self._dim[0] + 1), 2))
        rows = sorted(random.sample(range(self._dim[1] + 1), 2))
        dim = (cols[1] - cols[0], rows[1] - rows[0])
        return cols, rows, dim

    def _get_random_color(self):
        colors = ['red', 'green', 'blue']
        return colour.Color(random.choice(colors))

class Diffuse:
    DIFFUSION_HALF_LIFE_S = 2
    AVG_SPLASH_PERIOD = 5

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
        # times the probability that this pixel is updated times the probability this channel is
        # updated.
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
        approx_t = Diffuse.AVG_SPLASH_PERIOD / (16. / 100) / (1. / 3)
        x = 1.0
        S = 0.05
        self._decay_rate = -math.log(1 - x / (S + x)) / approx_t
        assert self._decay_rate < 0.5 # arbitrary sanity-check

        self._brightness_stats = walle.Stats('channel brightness', walle.log)

        self._splashers = []
        self._last_update_time = None
        self._next_splash_time = None

    def update(self):
        now = time.perf_counter()
        if self._last_update_time is None:
            self._last_update_time = now
            self._next_splash_time = now
        elapsed = now - self._last_update_time

        self._matrix = self._diffused(self._matrix, elapsed)
        self._matrix = self._decayed(self._matrix, elapsed)
        self._matrix = self._splashed(self._matrix, elapsed)

        if now >= self._next_splash_time:
            self._splashers.append(Splasher(*self._driver.dim()))
            self._next_splash_time = now + random.expovariate(1. / Diffuse.AVG_SPLASH_PERIOD)

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

    def _splashed(self, matrix, elapsed):
        # run and garbage-collect splashers.
        new_matrix = copy.deepcopy(matrix)
        for splasher in self._splashers:
            splasher.update(new_matrix, elapsed)
        self._splashers = [splasher for splasher in self._splashers if not splasher.is_done()]
        return new_matrix

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
