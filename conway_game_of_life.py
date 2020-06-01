#!/usr/bin/env python

import argparse
import colour
from grayfade import ColorFader
import itertools
import numpy
import random
import time
import walle

class ConwayGameOfLife:
    def __init__(self, num_cols, num_rows):
        self._grid = numpy.zeros((num_rows, num_cols), dtype=bool)
        self._num_stuck_cycles = 0

    def update(self):
        # advance the rules of life
        new_grid = numpy.zeros(self._grid.shape)
        num_rows, num_cols = self._grid.shape
        for row in range(num_rows):
            for col in range(num_cols):
                alive = self._grid[row, col]
                neighs_alive = self.get_num_neighs_alive(row, col)
                new_alive = neighs_alive == 3 or neighs_alive == 2 and alive
                new_grid[row][col] = new_alive

        # detect stuck
        if numpy.array_equal(new_grid, self._grid):
            self._num_stuck_cycles += 1

        self._grid = new_grid

    def get_grid(self):
        return self._grid.copy()

    def set_grid(self, new_grid):
        assert new_grid.shape == self._grid.shape
        assert new_grid.dtype == bool
        self._grid = new_grid.copy()

    def get_num_neighs_alive(self, row, col):
        num_rows, num_cols = self._grid.shape
        offsets = [(x, y) for x, y in itertools.product((-1, 0, 1), (-1, 0, 1)) if x or y]
        assert len(offsets) == 8
        return sum([self._grid[(row + y) % num_rows][(col + x) % num_cols] for x, y in offsets])

    def num_stuck_cycles(self):
        return self._num_stuck_cycles

class ConwayGameOfLifeDisplay:
    class Cell:
        def __init__(self, fade_time, row, col):
            self._fade_time = fade_time
            self._row = row
            self._col = col
            self._current_color = (0., 0., 0.)
            self._color_fader = ColorFader(self._current_color,
                                           self._current_color,
                                           0)

        def update(self, now, alive, num_neighs_alive):
            target_color = self._get_color(alive, num_neighs_alive)
            if target_color != self._current_color:
                self._color_fader.set(target_color, self._fade_time)
                self._current_color = target_color
            return self._color_fader.get(now)

        def _get_color(self, alive, num_neighs_alive):
            red = (1., 0., 0.)
            gray = (0.5, 0.5, 0.5)
            black = (0., 0., 0.)
            if alive:
                if 0 <= num_neighs_alive < 2:
                    return red
                elif 2 <= num_neighs_alive < 4:
                    return gray
                else:
                    return red
            else:
                return black

    def __init__(self, driver, game_step_period, fade_time, max_time):
        self._driver = driver
        self._game_step_period = game_step_period
        self._max_time = max_time
        num_rows, num_cols = driver.dim()
        dim = driver.dim()
        self._game = ConwayGameOfLife(num_rows, num_cols)
        self._game.set_grid(numpy.random.choice([False, True], dim))
        self._cells = [[ConwayGameOfLifeDisplay.Cell(fade_time, row, col)
                            for col in range(num_cols)] for row in range(num_rows)]
        self._start_time = None
        self._last_step = None
        self._timed_out = False
        self._game_update_profiler = \
            walle.IntervalProfiler('game update', walle.log, period=10)
        self._cell_update_profiler = \
            walle.IntervalProfiler('cells display update', walle.log, period=100)

    def update(self):
        now = time.time()

        if self._start_time is None:
            self._start_time = now

        grid = self._game.get_grid()
        with self._cell_update_profiler.measure():
            matrix = [[cell.update(now, grid[row][col], self._game.get_num_neighs_alive(row, col))
                        for col, cell in enumerate(cells)] for row, cells in enumerate(self._cells)]
        self._driver.set(matrix)

        if self._last_step is None or now - self._last_step >= self._game_step_period:
            with self._game_update_profiler.measure():
                self._game.update()
            self._last_step = now

        if now - self._start_time > self._max_time:
            self._timed_out = True

    def done(self):
        return self._timed_out or self._game.num_stuck_cycles() > 10

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    period = walle.PeriodFloor(0.01)
    game_step_period = 1.0
    fade_time = game_step_period * 1.5 # otherwise it seems to pause...
    profiler = walle.PeriodProfiler('display refresh', walle.log, period=10)
    game_of_life = None
    while True:
        if game_of_life is None or game_of_life.done():
            walle.log.info('New game!')
            game_of_life = ConwayGameOfLifeDisplay(driver,
                                                   fade_time=fade_time,
                                                   game_step_period=game_step_period,
                                                   max_time=300.)

        game_of_life.update()
        profiler.mark()
        period.sleep()
