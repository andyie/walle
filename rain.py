#!/usr/bin/env python

import argparse
from brian_eno_meditation import Splasher
import random
import walle

class Rain:
    def __init__(self, driver):
        self._splasher = Splasher(driver,
                                  diffusion_half_life=0.2,
                                  avg_splash_rate=5, # just going to immediately override
                                  min_splash_time=0.,
                                  max_splash_time=0.5,
                                  max_splash_area=1,
                                  target_avg_brightness=0.5)
        self._rate_stats = walle.Stats('rain rate', walle.log)
        self._max_splash_rate = 50.
        self._min_splash_rate = 0.2
        self._splash_rate = self._min_splash_rate

    def update(self):
        # choose a new splash rate with a random-walk
        mult = random.uniform(1., 1.1)
        if random.choice([False, True]):
            # this is my attempt at making the rate balance out to 0 net change. can't just select
            # uniformly from 1/1.1 to 1.1; this will have a bias.
            mult = 1. / mult
        self._splash_rate *= mult
        self._splash_rate = min(max(self._splash_rate, self._min_splash_rate), self._max_splash_rate)
        self._splasher.set_params(self._splash_rate, 0.5) # hard-code the decay rate
        self._rate_stats.sample(self._splash_rate)
        self._splasher.update()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    rain = Rain(driver)
    period = walle.PeriodFloor(0.05)
    walle.log.info('you know god is in the rain, '
                   'how else can you explain, '
                   'how it takes away the pain?')
    while True:
        rain.update()
        period.sleep()
