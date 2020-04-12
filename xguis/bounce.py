#!/usr/bin/python

"""
 This example shows having multiple balls bouncing around the screen at the
 same time. You can hit the space bar to spawn more balls.

 Sample Python/Pygame Programs
 Simpson College Computer Science
 http://programarcadegames.com/
 http://simpson.edu/computer-science/
"""

import pygame
import random

# Define some colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

BALL_SIZE = 10


class Ball:
    """
    Class to keep track of a ball's location and vector.
    """
    def __init__(self):
        self.x = 0
        self.y = 0
        self.change_x = 0
        self.change_y = 0


def make_ball(ball_size, screen_width, screen_height):
    """
    Function to make a new, random ball.
    """
    ball = Ball()
    # Starting position of the ball.
    # Take into account the ball size so we don't spawn on the edge.
    ball.x = random.randrange(ball_size, screen_width - ball_size)
    ball.y = random.randrange(ball_size, screen_height - ball_size)

    # Speed and direction of rectangle
    max_speed_dim = max(screen_width // 50, 1)
    ball.change_x = random.randrange(-max_speed_dim, max_speed_dim)
    ball.change_y = random.randrange(-max_speed_dim, max_speed_dim)

    return ball


def main():
    """
    This is our main program.
    """
    pygame.init()
    pygame.display.set_caption("Bouncing Balls")
    screen = pygame.display.set_mode((0, 0))
    clock = pygame.time.Clock()

    ball_list = []
    ball_size = screen.get_width() // 10
    ball = make_ball(ball_size, screen.get_width(), screen.get_height())
    ball_list.append(ball)

    done = False
    while not done:
        # --- Logic
        for ball in ball_list:
            # Move the ball's center
            ball.x += ball.change_x
            ball.y += ball.change_y

            # Bounce the ball if needed
            if ball.y > screen.get_height() - ball_size or ball.y < ball_size:
                ball.change_y *= -1
            if ball.x > screen.get_width() - ball_size or ball.x < ball_size:
                ball.change_x *= -1

        # --- Drawing
        # Set the screen background
        screen.fill(BLACK)

        # Draw the balls
        for ball in ball_list:
            #pygame.draw.line(screen, WHITE, [ball.x, ball.y], [ball.x, ball.y], 1)
            pygame.draw.circle(screen, WHITE, [ball.x, ball.y], ball_size)

        # --- Wrap-up
        # Limit to 60 frames per second
        clock.tick(60)

        # Go ahead and update the screen with what we've drawn.
        pygame.display.flip()

    # Close everything down
    pygame.quit()

if __name__ == "__main__":
    main()
