#!/usr/bin/env python

import argparse
import colour
import pygame
import socket
import subprocess
import time
import walle

class Scroller:
    DEFAULT_COLOR = 'white'

    def __init__(self, screen_time):
        assert screen_time > 0

        pygame.init()
        self._screen = pygame.display.set_mode((0, 0))
        walle.log.info('using screen {}x{}'.format(self._screen.get_width(),
                                                   self._screen.get_height()))
        assert self._screen.get_width() > 0
        self._shift_period = screen_time / self._screen.get_width()

        fontsize = 10
        fontname = 'anonymouspro'
        assert self._screen.get_width() == 10, 'reconsider hard-coded font size'
        fontpath = pygame.font.match_font(fontname)
        assert fontpath, 'oh no, font not found'
        self._font = pygame.font.Font(fontpath, fontsize)
        assert self._font.get_linesize() == fontsize

        self._last_shift_time = None
        self._offset = 0
        self.set_text('')

    def set_text(self, text, color=DEFAULT_COLOR, underline=False):
        self._font.set_underline(underline)
        self._text = self._font.render(text, False, walle.colour_to_8bit(colour.Color(color)))
        self._offset = min(self._offset, self._get_max_offset())

    def _get_max_offset(self):
        return self._text.get_width() + self._screen.get_width()

    def update(self):
        # do nothing if it's not time to update
        now = time.perf_counter()
        if self._last_shift_time is not None and now - self._last_shift_time < self._shift_period:
            return

        # otherwise, update the display. don't antialias the text, the font actually looks fine at
        # low-res not-antialiased. shift the text up by 1 pixel, since that leaves room for the
        # underline
        self._screen.fill((0, 0, 0))
        self._screen.blit(self._text, (self._screen.get_width() - self._offset, -1))
        pygame.display.flip()
        self._offset = (self._offset + 1) % self._get_max_offset()

        self._last_shift_time = now

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', type=str, default=None, help='Text to display')
    parser.add_argument('--text_cmd', type=str, default=None, help='Command to run to get text')
    parser.add_argument('--color', type=str, default='#ff4040', help='Color understandable by python-colour')
    parser.add_argument('--underline', action='store_true', default=False)
    parser.add_argument('--continuous', action='store_true', default=False)
    parser.add_argument('--screen_time', type=float, default=1., help='Seconds to scroll across screen')
    args = parser.parse_args()
    assert args.screen_time > 0

    text = args.text
    text_cmd = args.text_cmd
    if text and text_cmd:
        raise RuntimeError('can only specify text or text_cmd, not both')
    elif not text and not text_cmd:
        text_cmd = 'echo `hostname` `date`'

    scroller = Scroller(args.screen_time)
    period = walle.PeriodFloor(0.1)
    while True:
        if text_cmd:
            proc = subprocess.Popen(['bash', '-c', text_cmd],
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
            text, _ = proc.communicate()
        scroller.set_text(text, args.color, args.underline)
        scroller.update()
        period.sleep()
