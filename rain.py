#!/usr/bin/env python

import argparse
from brian_eno_meditation import Splasher
import walle

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    splasher = Splasher(driver,
                        diffusion_half_life=0.2,
                        avg_splash_rate=5,
                        min_splash_time=0.,
                        max_splash_time=0.,
                        max_splash_area=1,
                        target_avg_brightness=0.5)
    period = walle.PeriodFloor(0.05)
    while True:
        splasher.update()
        period.sleep()
