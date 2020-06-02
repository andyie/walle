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
            self._num_generations = None
            self._alive = None
            self._last_alive = None
            self._color_fader = ColorFader((0., 0., 0.), (0., 0., 0.), 0)

        def update(self, now, alive, num_neighs_alive, num_generations):
            if num_generations != self._num_generations:
                self._num_generations = num_generations
                self._last_alive = self._alive
                self._alive = alive
                new_color = self._get_color(num_neighs_alive)
                if new_color != self._color_fader.get_color_range()[1]:
                    self._color_fader.set(new_color, self._fade_time)
            return self._color_fader.get(now)

        def _get_color(self, num_neighs_alive):
            red = (1., 0., 0.)
            green = (0., 1., 0.)
            blue = (0., 0., 1.)
            gray = (0.5, 0.5, 0.5)
            black = (0., 0., 0.)
            if self._alive:
                if 0 <= num_neighs_alive < 2:
                    return red
                elif 2 <= num_neighs_alive < 4:
                    return gray if self._last_alive else blue
                else:
                    return red
            else:
                return black

    def __init__(self, driver, game_step_time, fade_time, max_generations):
        self._driver = driver
        self._game_step_time = game_step_time
        self._max_generations = max_generations
        num_rows, num_cols = driver.dim()
        dim = driver.dim()
        self._game = ConwayGameOfLife(num_rows, num_cols)
        self._game.set_grid(numpy.random.choice([False, True], dim))
        self._cells = [[ConwayGameOfLifeDisplay.Cell(fade_time, row, col)
                            for col in range(num_cols)] for row in range(num_rows)]
        self._num_generations = 0
        self._last_step = None
        self._timed_out = False
        self._game_update_profiler = \
            walle.IntervalProfiler('game update', walle.log, period=100)
        self._cell_update_profiler = \
            walle.IntervalProfiler('cells display update', walle.log)

    def update(self):
        now = time.time()

        grid = self._game.get_grid()
        with self._cell_update_profiler.measure():
            matrix = [[cell.update(now, grid[row][col], self._game.get_num_neighs_alive(row, col),
                                   self._num_generations)
                        for col, cell in enumerate(cells)] for row, cells in enumerate(self._cells)]
        self._driver.set(matrix)

        if self._last_step is None or now - self._last_step >= self._game_step_time:
            with self._game_update_profiler.measure():
                self._game.update()
            self._last_step = now

            self._num_generations += 1
            if self._num_generations >= self._max_generations:
                self._timed_out = True

    def done(self):
        return self._timed_out or self._game.num_stuck_cycles() > 10

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--game_step_time', type=float, default=1., help='Game of life step time')
    parser.add_argument('--fade_time_prop', type=float, default=1., help='Fade time proportion')
    parser.add_argument('--max_generations', type=int, help='Max generations')
    args = parser.parse_args()

    assert args.game_step_time > 0
    assert args.fade_time_prop >= 0
    max_generations = args.max_generations
    if max_generations is None:
        max_generations = int(60 / args.game_step_time)
    walle.log.info('limiting games to {} generations'.format(max_generations))

    driver = walle.create_display(args.target)
    period = walle.PeriodFloor(0.01)
    fade_time = args.game_step_time * args.fade_time_prop
    profiler = walle.PeriodProfiler('display refresh', walle.log)
    game_of_life = None
    while True:
        if game_of_life is None or game_of_life.done():
            walle.log.info('New game!')
            game_of_life = ConwayGameOfLifeDisplay(driver,
                                                   fade_time=fade_time,
                                                   game_step_time=args.game_step_time,
                                                   max_generations=max_generations)

        game_of_life.update()
        profiler.mark()
        period.sleep()
