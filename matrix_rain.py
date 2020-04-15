#!/usr/bin/env python

import argparse
import numpy
import random
import time
import walle

class MatrixRain:
    def __init__(self, num_cols, num_rows, driver):
        self._driver = driver
        walle.log.info('using screen {}x{}'.format(*driver.dim()))

        # choose the raindrop size, speed, and generation interval ranges
        dim = driver.dim()
        self._raindrop_length_range = (1, int(dim[1] * 3 / 4))
        self._raindrop_speed_range = (dim[1] / 2, dim[1] / 1.)
        self._raindrop_gen_time_range = (0.1, 0.1)

        self._raindrops = []
        self._next_raindrop_time = None

    def update(self):
        now = time.perf_counter()

        # if it's time to create some new rain, do so
        if self._next_raindrop_time is None or \
           self._next_raindrop_time <= now:
            self._raindrops.append(self._gen_raindrop())
            self._next_raindrop_time = now + random.uniform(*self._raindrop_gen_time_range)

        # generate the matrix and send it to the display
        matrix = walle.all_off_matrix(self._driver.dim())
        for raindrop in self._raindrops:
            raindrop.update(now, matrix)
        self._driver.set(matrix)

        # delete expired raindrops
        self._raindrops = [raindrop for raindrop in self._raindrops if not raindrop.is_done()]

    def _gen_raindrop(self):
        # note that we actually select from one short of the end of the length range, but whatever
        dim = self._driver.dim()
        start_row = max(random.randrange(-3 * dim[1], dim[1]), 0)
        end_row = max(min(random.randrange(0, 4 * dim[1]), dim[1]), start_row)
        return MatrixRaindrop(dim[0],
                              dim[1],
                              random.randrange(0, dim[0]),
                              start_row,
                              end_row,
                              random.randrange(*self._raindrop_length_range),
                              random.uniform(*self._raindrop_speed_range))

class MatrixRaindrop:
    """
    raindrops are the transient things that travel from top to bottom. each raindrop has these
    static properties. note that the color assignments per cell are static, which gives the raindrop
    the stationary-yet-moving classic matrix look, oh yeah.

        * random column
        * random visible length
        * random variations of the base color assigned statically to each cell in the column
        * random vertical speed
        * hard-coded fade profile (brighter on bottom, darker on top)
    
    each raindrop also has these dynamic properties:

        * current vertical position
        * color of front pixel (bright value is varied a bit to make it seem to flicker)
    """
    def __init__(self, num_cols, num_rows, col, start_row, end_row, length, speed):
        """
        the passed properties are decided by the overall matrix, the rest of the properties are
        chosen internally. it's ok   for the visible length to be longer than the screen size
        """
        assert length > 0
        self._dim = (num_cols, num_rows)
        self._col = col
        self._start_row = start_row
        self._end_row = end_row
        self._length = length
        self._speed = speed

        # assign random-ish colors to the entire column. also establish how white the head of the
        # drop will look. it looks better if drops have a range of whiteness to their heads.
        self._col_colors = [tuple([random.uniform(0.3, 1.0)] * 3) for _ in range(num_rows)]
        self._head_whiteness = random.uniform(0.0, 0.5)

        # figure the top-down per-color-channel fade profile of the raijndrop. note that all
        # elements except the last (lowest) zero out the gain for non-green channels, but the last
        # applies a head-whiteness gain. the effect here is that the head pixel in the raindrop will
        # be white-ish and brighter than the others.
        low_gain = 0.1
        med_gain = 0.7
        high_gain = 1.0
        mid_idx = self._length // 2
        self._raindrop_profile = [(0., numpy.interp([i], [0, mid_idx], [low_gain, med_gain])[0], 0.)
                                    for i in range(mid_idx)] + \
                                 [(0., med_gain, 0.) for i in range(mid_idx, self._length - 1)] + \
                                 [(self._head_whiteness, 1.0, self._head_whiteness)]
        assert len(self._raindrop_profile) == self._length

        self._start_t = None
        self._done = False

    def update(self, now, matrix):
        # establish start time if necessary
        if self._start_t is None:
            self._start_t = now
        elapsed = now - self._start_t
        assert elapsed >= 0

        # to simplify the shifting logic, prefix the raindrop with a full screen's worth of
        # zero-gain blanks. then figure the pixel offset of the head of the raindrop, clamped to the
        # new length of the raindrop.
        ext_profile = [(0, 0, 0) for _ in range(self._dim[1])] + self._raindrop_profile
        offset = min(int(self._speed * elapsed), len(ext_profile))

        # the in-view raindrop is the screen worth of pixels (if available) starting this offset
        # back from the end of the raindrop profile. on the first update, this array will be empty.
        # on the last update, this array will be a screen full, but of zero-gain pixels.
        vis_profile = ext_profile[-offset:][:self._dim[1]]

        # localize the in-view raindrop profile against the assigned column's colors
        vis_raindrop = [tuple(ch * gain for ch, gain in zip(pixel_color, pixel_profile))
                        for pixel_color, pixel_profile in zip(self._col_colors, vis_profile)]

        # install the raindrop in the matrix. installation is by saturating addition. this way
        # raindrops overlay nicely. another layer of complexity here is that the drop may only be
        # rendered for a section of the column. this makes the drop seem to come in/disappear in the
        # middle of the column. sort of a hack.
        for row, raindrop_pixel in enumerate(vis_raindrop):
            if row >= self._start_row and row < self._end_row:
                matrix[row][self._col] = \
                    tuple(min(x + y, 1.) for x, y in zip(matrix[row][self._col], raindrop_pixel))

        # the raindrop is done if its offset has reached its maximum extent
        self._done = (offset == len(ext_profile))

    def is_done(self):
        return self._done
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    matrix_rain = MatrixRain(*driver.dim(), driver)
    period = walle.PeriodFloor(0.05)
    while True:
        matrix_rain.update()
        period.sleep()
