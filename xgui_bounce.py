#!/usr/bin/python

"""
 This example shows having multiple balls bouncing around the screen at the
 same time. You can hit the space bar to spawn more balls.

 Sample Python/Pygame Programs
 Simpson College Computer Science
 http://programarcadegames.com/
 http://simpson.edu/computer-science/
"""

import argparse
import math
import pygame
import random
import time

# Define some colors
WHITE = (255, 255, 255)

class Ball:
    """
    Class to keep track of a ball's location and vector.
    """
    def __init__(self, radius, screen):
        # choose a random starting position and speed. let the maximum speed in each direction be a
        # bounce every second.  second.
        self._radius = radius
        self._screen = screen
        screen_dim = (screen.get_width(), screen.get_height())
        self._limits = tuple((radius, d - radius) for d in screen_dim)
        self._pos = [random.uniform(*limits) for limits in self._limits]
        max_speed = [d for d in screen_dim]
        self._vel = [random.uniform(-m, m) for m in max_speed]
        self._color = tuple(random.choice([0, 255]) for _ in range(3))
        self._then = None

    def update(self, now):
        # update position
        if self._then is not None:
            dt = now - self._then
            for i, (p, v, limits) in enumerate(zip(self._pos, self._vel, self._limits)):
                p += v * dt
                if p < limits[0]:
                    p = limits[0] + (limits[0] - p)
                    v *= -1
                elif p >= limits[1]:
                    p = limits[1] + (limits[1] - p)
                    v *= -1
                self._pos[i] = max(limits[0], min(limits[1], p))
                self._vel[i] = v

        # draw the ball. need to truncate position to integers
        pygame.draw.circle(self._screen, self._color, [int(p) for p in self._pos], self._radius)

        self._then = now

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--num_balls', type=int, default=1)
    args = parser.parse_args()
    assert args.num_balls > 0

    pygame.init()
    pygame.display.set_caption("Bouncing Balls")
    screen = pygame.display.set_mode((0, 0))
    clock = pygame.time.Clock()
    screen_dim = (screen.get_width(), screen.get_height())
    ball_radius = screen.get_width() // 20 # let division truncate to 0
    print('Using screen {}x{} and ball radius {}'.format(*screen_dim, ball_radius))
    balls = [Ball(ball_radius, screen) for _ in range(args.num_balls)]

    done = False
    while not done:
        now = time.time()
        screen.fill((0, 0, 0))
        for ball in balls:
            ball.update(now)
        clock.tick(60)
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
