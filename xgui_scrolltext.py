#!/usr/bin/env python

import argparse
import colour
import pygame
import socket
import subprocess
import time
import walle

class Scroller:
    DEFAULT_SCREEN_TIME = 1.
    DEFAULT_COLOR = 'white'

    def __init__(self, continuous=True, screen_time=DEFAULT_SCREEN_TIME):
        assert screen_time > 0
        self._continuous = continuous

        pygame.init()
        self._screen = pygame.display.set_mode((0, 0))
        walle.log.info('using screen {}x{}'.format(self._screen.get_width(),
                                                   self._screen.get_height()))
        assert self._screen.get_width() > 0
        self._shift_period = screen_time / self._screen.get_width()

        # anonymouspro looks nice at low resolution, unlike the built-in monospace
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

        self._scroll_shift_period = walle.PeriodProfiler('scroll shift', walle.log, 100)

    def is_done(self):
        """
        note: continuous mode is never "done". also not that it really should be enough to check the
        offset against max offset, because continuous mode should maintain the invariant that the
        offset never reaches the max offset. but continuous mode is checked anyway for good measure.
        """
        return not self._continuous and self._offset == self._get_max_offset()

    def set_text(self, text, color=DEFAULT_COLOR, underline=False, force_restart=False):
        """
        the text scroll always "restarts" when the scroller is not in continuous mode (because
        otherwise part of it will almost certainly never be displayed). but in continuous mode, the
        text can be updated "in place", which is cool when only part of the text is being tweaked.
        a restart can still be forced in continuous mode, if desired.
        """
        self._font.set_underline(underline)
        self._text = self._font.render(text, False, walle.colour_to_8bit(colour.Color(color)))
        if not self._continuous or force_restart:
            self._offset = 0
        else:
            # if the new text is shorter than the old text, then the current offset may be off the
            # end. modulo is a cute trick to keep this from occurring while keeping the new offset
            # below the new max offset. it does mean that we may start midway into the new text,
            # though, which is a little odd.
            self._offset = self._offset % self._get_max_offset()

    def _get_max_offset(self):
        """
        note: at max offset, the text is shifted completely out of view. this makes it a nice
        end-stop for one-shot text
        """
        assert self._screen.get_width() >  0
        return self._text.get_width() + self._screen.get_width()

    def update(self):
        # do nothing if it's not time to update
        now = time.perf_counter()
        if self._last_shift_time is not None and now - self._last_shift_time < self._shift_period:
            return

        # update the display. don't antialias the text, the font actually looks fine at low-res
        # not-antialiased. shift the text up by 1 pixel, since that leaves room for the underline
        #
        # if the text has scrolled to max offset, it restarts at 0 if the scroller is in continuous
        # mode. otherwise it stays there.
        self._screen.fill((0, 0, 0))
        self._screen.blit(self._text, (self._screen.get_width() - self._offset, -1))
        pygame.display.flip()
        self._scroll_shift_period.mark()
        self._offset += 1
        if self._offset == self._get_max_offset() and self._continuous:
            self._offset = 0

        self._last_shift_time = now

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', type=str, default=None, help='Text to display')
    parser.add_argument('--text_cmd', type=str, default=None, help='Command to run to get text')
    parser.add_argument('--color', type=str, default='#ff4040', help='Color understandable by python-colour')
    parser.add_argument('--underline', action='store_true', default=False)
    parser.add_argument('--continuous', action='store_true', default=False)
    parser.add_argument('--screen_time', type=float, default=Scroller.DEFAULT_SCREEN_TIME,
                        help='Seconds to scroll across screen')
    args = parser.parse_args()
    assert args.screen_time > 0

    text = args.text
    text_cmd = args.text_cmd
    if text and text_cmd:
        raise RuntimeError('can only specify text or text_cmd, not both')
    elif not text and not text_cmd:
        text_cmd = 'echo `hostname` `date`'

    scroller = Scroller(True, args.screen_time)
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
