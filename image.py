#!/usr/bin/env python


import argparse
import numpy
import random
import time

from PIL import Image, ImageSequence

import walle


class ImageDisplay:
    def __init__(self, driver, path):
        self.driver = driver
        self.image = Image.open(path).convert('RGB')
        self.frames = []

        # Prepare frames
        orig_height, orig_width = self.image.size
        disp_height, disp_width = driver.dim()
        factor_height = orig_height // disp_height + 1
        factor_width = orig_width // disp_width + 1
        self.image = self.image.reduce((factor_height, factor_width))
                
        if self.image.is_animated:
            for frame in ImageSequence.Iterator(self.image):
                self.frames.append([[frame.get_pixel((x, y)) for x in disp_width] for y in disp_height])
        else:
            self.frames.append([[self.image.get_pixel((x, y)) for x in disp_width] for y in disp_height])

    def update(self):
        while True:
            for frame in self.frames:
                self.driver.set(frame)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('image', type=str, help='Image to display')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    image = ImageDisplay(driver, args.image)
    period = walle.PeriodFloor(0.05)
    while True:
        image.update()
        period.sleep()
