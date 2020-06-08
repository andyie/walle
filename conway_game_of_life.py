#!/usr/bin/env python

import argparse
import colour
from grayfade import ColorFader
import itertools
import numpy as np
import random
import time
import walle

class ConwayGameOfLife:
    def __init__(self, num_cols, num_rows):
        self._grid = np.zeros((num_rows, num_cols), dtype=bool)
        self._num_stuck_cycles = 0

    def update(self):
        # advance the rules of life
        new_grid = np.zeros(self._grid.shape, dtype=bool)
        num_rows, num_cols = self._grid.shape
        for row in range(num_rows):
            for col in range(num_cols):
                alive = self._grid[row, col]
                neighs_alive = self.get_num_neighs_alive(row, col)
                new_alive = neighs_alive == 3 or neighs_alive == 2 and alive
                new_grid[row][col] = new_alive

        # detect stuck
        if np.array_equal(new_grid, self._grid):
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

class ConwayGameOfLifeMonitor:
    def __init__(self, game, max_cycling_game_generations):
        self._game = game
        self._generations = {}
        self._max_cycling_game_generations = max_cycling_game_generations
        self._num_generations = 0
        self._generations_to_go = None

    def update(self):
        # The grid is an arbitrary 2D view of the toroidal game, so we should treat game states as
        # invariant under translations and rotations. Obtain all 4 possible 2D rotations of the
        # game, and "center" each one by justifying its upper-most, left-most set pixel (upper-most
        # is prioritized) to the upper-left corner. There's probably a clever way to choose a
        # consistent rotation for a game state versus just computing all 4, but we don't do that :).
        #
        # Note that centering/rotating the game isn't required to detect cycles--a cyclical game
        # will always eventually revisit the original position and rotation. Centering/rotating the
        # game just allows cycles to be detected earlier, which makes the game less boring.
        #
        # NOTE: This does not cover invariance to reflections....
        #
        # NOTE: Actually, just doing 1 rotation for now... it was getting slow.
        #
        # NOTE: Actually not doing the centering now, either. Problem is 1) it didn't successfuly
        # detect a simple glider, so there's a big somewhere; 2) it doesn't work anyway--aligning
        # the top-left set pixel is still ambiguous! So until I figure out an actual way to compare
        # two toruses, I'm just going to compare the grids directly.
        #grids = self._centered_rotated_grids(self._game.get_grid(), num_rots=1)
        grids = [self._game.get_grid()]
        assert len(grids) == 1

        # Condense each of the grids into single-integer bitmasks. This presumably makes storing
        # these values in a historical dict cheaper than, say, storing ndarray.data.tobytes().
        bitmasks = [self._grid_to_int(grid) for grid in grids]

        # Now see if any of these bitmasks are in the generation history. Only one should appear,
        # since if there was more than one that would mean a duplicate was added earlier. Only do
        # this if we haven't already decided to stop the game, though.
        if self._generations_to_go is None:
            try:
                past = next(past for past in (self._generations.get(b, None) for b in bitmasks)
                                if past is not None)
                period = self._num_generations - past
                self._generations_to_go = min(5 * period, self._max_cycling_game_generations)
                walle.log.info('At {} generations, detected game cycle of {} generations! Stopping '
                               'after {} more generations'.format(self._num_generations,
                                    period, self._generations_to_go))
            except StopIteration:
                # Bitmask has not been seen before; store this generation along with the current
                # generation index. Arbitrarily store the first "version" of this generation.
                # There's no point storing all the rotations, etc.
                self._generations[bitmasks[0]] = self._num_generations

        # Incrementing this first means game-stop printout below will "count" this generation.
        self._num_generations += 1

        # If we've already decided to stop the game at some point in the future, wind down the
        # clock.
        if self._generations_to_go:
            self._generations_to_go -= 1

    def is_game_done(self):
        return self._generations_to_go == 0

    def _grid_to_int(self, grid):
        assert grid.dtype == bool
        assert grid.shape == (10, 10)
        bitmask = 0
        for cell in grid.flatten():
            bitmask = (bitmask << 1) | (1 if cell else 0)
        return bitmask

    def _center_grid(self, grid):
        # Find the first occupied row, if any. If the game is blank, select the first row.
        try:
            first_row = next(i for i, row in enumerate(grid) if np.sum(row))
        except StopIteration:
            first_row = 0

        # Find the first occupied column in the first occupied row, if any. If the game is blank,
        # select the first column.
        try:
            first_col = next(i for i, col in enumerate(grid[first_row]) if col)
        except StopIteration:
            first_col = 0

        # Now rotate the grid so that the cell identified by the first row and column is upper-left
        # justified.
        return np.roll(np.roll(grid, -first_row, axis=0), -first_col, axis=1)

    def _centered_rotated_grids(self, grid, num_rots=4):
        assert 0 <= num_rots <= 4
        if num_rots == 0:
            return []
        else:
            return [grid] + self._centered_rotated_grids(np.rot90(grid), num_rots - 1)

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

    def __init__(self, driver, game_step_time, fade_time, game_update_profiler,
                 game_monitor_profiler, cell_update_profiler):
        self._driver = driver
        self._game_step_time = game_step_time
        num_rows, num_cols = driver.dim()
        dim = driver.dim()
        self._game = ConwayGameOfLife(num_rows, num_cols)
        self._game.set_grid(np.random.choice([False, True], dim))
        self._cells = [[ConwayGameOfLifeDisplay.Cell(fade_time, row, col)
                            for col in range(num_cols)] for row in range(num_rows)]
        self._num_generations = 0
        self._last_step = None
        self._game_update_profiler = game_update_profiler
        self._game_monitor_profiler = game_monitor_profiler
        self._cell_update_profiler = cell_update_profiler

        max_cycling_game_generations = int(60 / game_step_time)
        self._game_monitor = ConwayGameOfLifeMonitor(self._game, max_cycling_game_generations)

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
            with self._game_monitor_profiler.measure():
                self._game_monitor.update()
            self._last_step = now
            self._num_generations += 1

    def is_done(self):
        return self._game_monitor.is_game_done()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--game_step_time', type=float, default=1., help='Game of life step time')
    parser.add_argument('--fade_time_prop', type=float, default=1., help='Fade time proportion')
    args = parser.parse_args()

    assert args.game_step_time > 0
    assert args.fade_time_prop >= 0

    driver = walle.create_display(args.target)
    period = walle.PeriodFloor(0.01)
    fade_time = args.game_step_time * args.fade_time_prop
    profiler = walle.PeriodProfiler('display refresh', walle.log)
    game_of_life = None

    game_update_profiler = walle.IntervalProfiler('game update', walle.log, period=100)
    game_monitor_profiler = walle.IntervalProfiler('game monitor', walle.log, period=100)
    cell_update_profiler = walle.IntervalProfiler('cells display update', walle.log)

    while True:
        if game_of_life is None or game_of_life.is_done():
            walle.log.info('New game!')
            game_of_life = ConwayGameOfLifeDisplay(driver,
                                                   fade_time=fade_time,
                                                   game_step_time=args.game_step_time,
                                                   game_update_profiler=game_update_profiler,
                                                   game_monitor_profiler=game_monitor_profiler,
                                                   cell_update_profiler=cell_update_profiler)

        game_of_life.update()
        profiler.mark()
        period.sleep()
