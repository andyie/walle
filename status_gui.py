#!/usr/bin/env python

import argparse
import pygame
import time
import walle

class StatusDisplay:
    def __init__(self, target):
        pygame.init()
        pygame.display.set_caption('{} walle status'.format(target))
        self._driver = walle.create_display(args.target)
        self._screen = pygame.display.set_mode([400, 400])
        self._cycle_profiler = walle.Profiler('status refresh', walle.log)

    def display_forever(self):
        done = False
        while not done:
            with self._cycle_profiler.measure():
                # record any exit request
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        done = True

                # update the display
                matrix = self._driver.get()
                if matrix:
                    self._display_matrix(matrix)
                else:
                    walle.log.warning('could not get display')

                time.sleep(0.05)

        pygame.quit()

    def _display_matrix(self, matrix):
        # get matrix dimensions
        num_rows = len(matrix)
        num_cols = len(matrix[0])
        assert len(set([len(row) for row in matrix])) == 1

        # start drawing the new display
        self._screen.fill((0, 0, 0))

        # draw cells
        cell_length = int(self._screen.get_width() / num_cols)
        for row in range(num_rows):
            for col in range(num_cols):
                # there is some conversion error here, but good enough for a display
                color = tuple(int(ch * 255) for ch in matrix[row][col])
                rect = (col * cell_length, row * cell_length, cell_length, cell_length)
                pygame.draw.rect(self._screen, color, rect, 0)

        # draw borders around cells
        for row in range(num_rows):
            for col in range(num_cols):
                rect = (col * cell_length, row * cell_length, cell_length, cell_length)
                pygame.draw.rect(self._screen, (50, 50, 50), rect, 1)

        # swap in the new display
        pygame.display.flip()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    status = StatusDisplay(args.target)
    status.display_forever()
