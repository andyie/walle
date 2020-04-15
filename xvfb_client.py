#!/usr/bin/env python

import argparse
import io
import os
from PIL import Image
import subprocess
import time
import walle

def xwd2bmp(in_file):
    convert = subprocess.Popen(['convert', 'xwd:' + in_file, 'bmp:-'],
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    bmp, _ = convert.communicate()
    if convert.poll() != 0:
        raise RuntimeError('{} failed with return code {}'.format(
            ' '.join(convert.args), convert.returncode))
    assert len(bmp) > 0
    assert type(bmp) == bytes
    return bmp

def bmp2matrix(bmp, matrix_dim):
    # resize the image if necessary. use an anti-aliasing resampling filter
    img = Image.open(io.BytesIO(bmp))
    if img.size != matrix_dim:
        img = img.resize(matrix_dim, resample=Image.LANCZOS)
    assert img.size == matrix_dim
    return [[tuple(ch / 255. for ch in img.getpixel((col, row)))
                for col in range(matrix_dim[0])]
                    for row in range(matrix_dim[1])]

class Xvfb:
    def __init__(self, logger, x_display, x_dim):
        self.logger = logger
        self.x_display = x_display
        self.x_dim = x_dim

    def __enter__(self):
        # decide on working files
        xvfb_screen = 0
        frame_buffer_path = os.path.join(
            '/tmp',
            'walle_{}x{}_xvfb_display_{}'.format(*self.x_dim, self.x_display),
            'Xvfb_screen{}'.format(xvfb_screen))
        os.makedirs(os.path.dirname(frame_buffer_path), exist_ok=True)
        self.logger.info('using X frame buffer: {}'.format(frame_buffer_path))
        if os.path.exists(frame_buffer_path):
            raise RuntimeError('X frame buffer {} already exists, is Xvfb already running?'.format(
                frame_buffer_path))

        # start the virtual X frame buffer server. -nocursor (X Server argument) avoids cursor arrow
        # artifacts. Let stderr continue to console.
        self.xvfb_proc = subprocess.Popen(['/usr/bin/Xvfb', ':{}'.format(self.x_display), '-screen',
                                           str(xvfb_screen), '{}x{}x24'.format(*self.x_dim),
                                           '-fbdir', os.path.dirname(frame_buffer_path),
                                           '-nocursor'],
                                          stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL)
        self.logger.info('started PID {}: {}'.format(self.xvfb_proc.pid,
            ' '.join(self.xvfb_proc.args)))
        time.sleep(0.5)
        if self.xvfb_proc.poll() is not None:
            raise RuntimeError('PID {} quit right away with return code {}'.format(
                self.xvfb_proc.pid, self.xvfb_proc.returncode))

        self.logger.info('set env DISPLAY to :{} to connect to this display'.format(self.x_display))

        return frame_buffer_path

    def __exit__(self, *args):
        self.logger.info('terminating PID {}'.format(self.xvfb_proc.pid))
        self.xvfb_proc.terminate()
        termination_time = time.perf_counter()
        while time.perf_counter() - termination_time < 0.5 and self.xvfb_proc.poll() is None:
            time.sleep(0.1)
        if self.xvfb_proc.poll() is None:
            self.logger.warning('escalating to killing PID {}'.format(self.xvfb_proc.pid))
            self.xvfb_proc.kill()
        else:
            self.logger.info('PID {} exited with return code {}'.format(self.xvfb_proc.pid,
                self.xvfb_proc.returncode))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    default_dim = '{}x{}'.format(walle.DEFAULT_NUM_COLS, walle.DEFAULT_NUM_ROWS)
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--x_display', type=int, default=1, help='X display number to allocate')
    parser.add_argument('--x_dim', type=str, default=default_dim, help='X display WxH dimensions')
    args = parser.parse_args()
    x_dim = tuple(int(d) for d in args.x_dim.split('x', maxsplit=1))

    driver = walle.create_display(args.target)
    with Xvfb(walle.log, args.x_display, x_dim) as frame_buffer_path:
        period = walle.PeriodFloor(0.05)
        while True:
            bmp = xwd2bmp(frame_buffer_path)
            matrix = bmp2matrix(bmp, driver.dim())
            driver.set(matrix)
            period.sleep()
