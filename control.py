#!/usr/bin/env python
 
import argparse
import os
from PIL import BmpImagePlugin, Image
import pygame
import subprocess
import sys
import tempfile
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

    def get_matrix(self):
        self._update_matrix()
        return self._matrix

    def get_status(self):
        return self._msg

    def get_bmp_latency(self):
        return time.time() - self._last_mtime

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
            gui_status = 'GUI cycle: {:.3f}'.format(now - self._last_update_time)
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

def parse_WxH(s):
    return tuple(int(d) for d in s.split('x', maxsplit=1))

def terminate_subprocs(procs):
    print('Signalling children to exit...')
    for proc in procs:
        proc.terminate()
    while any([proc.poll() is None for proc in procs]):
        time.sleep(0.1)
    for proc in procs:
        print('PID {} exited with return code {}'.format(proc.pid, proc.returncode))

def report_subproc(proc):
    print('Started PID {}: {}'.format(proc.pid, ' '.join(proc.args)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--led_display_dim', type=str, default='10x10', help='WxH dimensions of LED '
                        'display')
    parser.add_argument('--x_display', type=int, default=1, help='Display number to allocate for '
                        'virtual frame buffer')
    parser.add_argument('--x_display_dim', type=str, help='WxH dimensions to configure for virtual '
                        'virtual frame buffer. Defaults to match LED display')
    args = parser.parse_args()

    # Figure display dimensions. The X display defaults to the same size as the LED display.
    led_display_dim = parse_WxH(args.led_display_dim)
    x_display_dim = parse_WxH(args.x_display_dim or args.led_display_dim)
    print('Configuring {}x{} LED display and {}x{} X display'.format(*led_display_dim,
          *x_display_dim))
    if led_display_dim != x_display_dim:
        print('Note: X display contents will be resized and antialiased')

    procs = []
    xvfb_screen = 0
    frame_buffer_dir = os.path.join('/', 'tmp', 'walle_control')
    frame_buffer_path = os.path.join(frame_buffer_dir, 'Xvfb_screen{}'.format(xvfb_screen))
    os.makedirs(frame_buffer_dir, exist_ok=True)
    print('Using FB: ', frame_buffer_path)
    bmp_path = os.path.join(frame_buffer_dir, 'fb.bmp')
    print('Using BMP: ', bmp_path)

    # Start virtual frame buffer server. -nocursor (X Server argument) avoids cursor arrow
    # artifacts. Inhibit all I/O to prevent console spam/blocking I/O if pipes fill. Wait for the
    # frame buffer file to exist.
    procs.append(subprocess.Popen(['/usr/bin/Xvfb', ':{}'.format(args.x_display), '-screen',
                                   str(xvfb_screen), '{}x{}x24'.format(*x_display_dim), '-fbdir',
                                   frame_buffer_dir, '-nocursor'], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    report_subproc(procs[-1])

     # Wait a moment for processes to start. Then double-check they are not already exited.
    time.sleep(1)
    for proc in procs:
        if proc.poll() is not None:
            print('Uh-oh, PID {} already exited with return code {}'.format(proc.pid,proc.returncode))
            terminate_subprocs(procs)
            sys.exit(1)

    print('Waiting for virtual frame buffer {} to exist...'.format(frame_buffer_path))
    while not os.path.exists(frame_buffer_path):
        time.sleep(0.1)

    print('Ctrl-C or close GUI window to exit')
    bmp_matrix = BmpMatrix(bmp_path, *led_display_dim)
    status = StatusDisplay('WallE Status', 400, 500)
    convert_proc = None
    try:
        while not status.is_exit_requested():
            matrix = bmp_matrix.get_matrix()

            # Now that the BMP for this cycle is locked in, request a new conversion. This will run
            # in the background and hopefully be done before the next cycle.
            #
            # Only start a new conversion if the previous one is finished.
            if convert_proc is None or convert_proc.poll() is not None:
                convert_proc = subprocess.Popen(['convert', 'xwd:' + frame_buffer_path,
                                                 'bmp:' + bmp_path],
                                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL)

            status.update(matrix,
                          'BMP staleness: {:.3f} ({})'.format(bmp_matrix.get_bmp_latency(),
                                                              bmp_matrix.get_status()),
                          'WallE not implemented')

            # Delay a bit to avoid pegging the core.
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass

    terminate_subprocs(procs)
        
    print('Exiting...')
