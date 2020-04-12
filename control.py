#!/usr/bin/env python
 
import argparse
import os
from PIL import BmpImagePlugin, Image
import pygame
import time
import walle

class BmpMatrix:
    def __init__(self, bmp_file, num_rows, num_cols):
        self._bmp_file = bmp_file
        self._num_rows = num_rows
        self._num_cols = num_cols
        self._matrix = [[walle.Color(r=1, g=1, b=1)] * num_cols] * num_rows
        self._msg = 'uninitialized'
        self._last_mtime = None
        self._last_update_time = time.time()

    def _8bit_color_to_walle_color(self, color8bit):
        assert len(color8bit) == 3
        assert all([ch >= 0 and ch < 256 and int(ch) == ch] for ch in color8bit)
        return walle.Color(color8bit[0] / 255., color8bit[1] / 255., color8bit[2] / 255.)

    def _update_matrix(self):
        now = time.time()

        # no point continuing if the file doesn't exist
        if not os.path.exists(self._bmp_file):
            self._msg = 'file does not exist'
            return

        # stop if the file hasn't been modified. otherwise, update the last mtime. don't update the
        # status message, since the previous message is still relevant
        mtime = os.path.getmtime(self._bmp_file) 
        if mtime == self._last_mtime:
            return
        assert self._last_mtime is None or mtime >= self._last_mtime
        self._last_mtime = mtime

        # try to open the .bmp
        try:
            img = BmpImagePlugin.BmpImageFile(self._bmp_file)
        except SyntaxError as e:
            if not 'Not a BMP file' in str(e):
                raise
            self._msg = 'not a .bmp file'
            return

        # verify the .bmp's dimensions
        self._msg = 'up-to-date'
        if img.size != (self._num_cols, self._num_rows):
            self._msg += ' (resized from {}x{})'.format(img.size[0], img.size[1])
            img = img.resize((self._num_cols, self._num_rows), resample=Image.LANCZOS)
        
        # update the matrix
        self._matrix = [[self._8bit_color_to_walle_color(img.getpixel((col, row)))
                            for col in range(self._num_cols)]
                                for row in range(self._num_rows)]
        self._last_update_time = now

    def get_matrix(self):
        self._update_matrix()
        return self._matrix

    def get_status(self):
        return self._msg

    def get_time_since_update(self):
        return time.time() - self._last_update_time

class StatusDisplay:
    def __init__(self, window_name, screen_width, screen_height):
        pygame.init()
        pygame.display.set_caption(window_name)
        self._screen = pygame.display.set_mode([screen_width, screen_height])
        self._font = pygame.font.Font(None, 16)
        self._last_update_time = None
        self._exit_requested = False

    def update(self, matrix, matrix_status, walle_status):
        now = time.time()

        # record any exit request
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._exit_requested = True

        # get matrix dimensions
        num_rows = len(matrix)
        num_cols = len(matrix[0])
        assert len(set([len(row) for row in matrix])) == 1

        # start drawing the new display
        self._screen.fill((0, 0, 0))

        # figure cell width and ensure enough space will remain for text
        cell_length = int(self._screen.get_width() / num_cols)
        assert cell_length > 10 # sanity-check
        assert self._screen.get_height() - cell_length * num_rows >= 100

        # draw cells. let each cell own a small border as part of itself
        for row in range(num_rows):
            for col in range(num_cols):
                color = self._walle_color_to_8bit_color(matrix[row][col])
                rect = (col * cell_length, row * cell_length, cell_length, cell_length)
                pygame.draw.rect(self._screen, color, rect, 0)

        # draw borders
        for row in range(num_rows):
            for col in range(num_cols):
                rect = (col * cell_length, row * cell_length, cell_length, cell_length)
                pygame.draw.rect(self._screen, (50, 50, 50), rect, 1)

        # draw status just below the cells
        status_pad_top = int(cell_length * num_rows + self._font.get_linesize() / 2)
        status_pad_left = 10
        gui_status = None
        if self._last_update_time is not None:
            gui_status = 'GUI staleness: {:.3f}'.format(now - self._last_update_time)
        statuses = [walle_status, matrix_status, gui_status]
        for i, status in enumerate(filter(lambda s: s, statuses)):
            status = self._font.render(status, True, (255, 255, 255))
            self._screen.blit(status, (status_pad_left, status_pad_top))
            status_pad_top += self._font.get_linesize()

        # swap in the new display
        pygame.display.flip()
        self._last_update_time = now

    def _walle_color_to_8bit_color(self, color):
        assert all([ch >= 0 and ch <= 1. for ch in color])
        return tuple(int(ch * 255) for ch in color)

    def is_exit_requested(self):
        return self._exit_requested

    def __del__(self):
        pygame.quit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bmp_file', type=str)
    args = parser.parse_args()

    print('Using image file {}'.format(args.bmp_file))
    bmp_matrix = BmpMatrix(args.bmp_file, 10, 10)
    status = StatusDisplay('WallE Status', 400, 500)

    while not status.is_exit_requested():
        matrix = bmp_matrix.get_matrix()
        status.update(matrix,
                      'BMP staleness: {:.3f} ({})'.format(bmp_matrix.get_time_since_update(),
                                                          bmp_matrix.get_status()),
                      'WallE not implemented')
        time.sleep(0.05)
        
    print('Exiting...')
