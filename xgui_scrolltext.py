#!/usr/bin/env python

import argparse
import colour
import pygame
import socket
import walle

def color_to_8bit(color):
    return tuple(int(255 * ch) for ch in color.rgb)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', type=str, default=None, help='Text to display')
    parser.add_argument('--color', type=str, default='white', help='Color understandable by python-colour')
    parser.add_argument('--underline', action='store_true', default=False)
    parser.add_argument('--continuous', action='store_true', default=False)
    parser.add_argument('--screen_time', type=float, default=1., help='Seconds to scroll across screen')
    args = parser.parse_args()
    assert args.screen_time > 0

    text = args.text
    if not text:
        text = socket.gethostname()

    pygame.init()
    screen = pygame.display.set_mode((0, 0))
    screen_dim = (screen.get_width(), screen.get_height())
    walle.log.info('Using screen {}x{}'.format(*screen_dim))

    fontsize = 10
    color = colour.Color(args.color)
    anonymouspro = pygame.font.match_font('anonymouspro')
    assert anonymouspro, 'oh no, font not found'
    font = pygame.font.Font(anonymouspro, fontsize)
    font.set_underline(args.underline)
    assert font.get_linesize() == fontsize

    text_box = font.render(text, False, color_to_8bit(color))
    text_box_dim = font.size(text)

    period = walle.PeriodFloor(float(args.screen_time) / screen_dim[0])
    done = False
    while not done:
        for offset in range(-screen_dim[0], text_box_dim[0]):
            screen.fill((0, 0, 0))
            # printing at -1 makes underline row barely fit at font size 10
            screen.blit(text_box, (-offset, -1))
            pygame.display.flip()
            period.sleep()
        done = not args.continuous
