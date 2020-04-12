#!/usr/bin/python

from collections import namedtuple
import spidev

Color = namedtuple('Color', ['r', 'g', 'b'])

class Array:
    """
    Light thingy.
    """
    class Led:
        """
        Minion.
        """
        def __init__(self, array, index):
            """
            Constructor. Lol.

            @param array The array this guy lives in.
            @param index This guy's index in the array.
            """
            self.__dict__['array'] = array
            self.__dict__['index'] = index

        def set(self, red=0, green=0, blue=0):
            """
            Set all components of the LED all at once.
            """
            self.__store('red', red)
            self.__store('green', green)
            self.__store('blue', blue)
            if self.array.autoupdate:
                self.array.update()

        def get(self):
            """
            Get all commanded components of the LED as a dict.
            """
            return {key: self.__retrieve(key) for key in ['red', 'green', 'blue']}

        def __store(self, name, val):
            """
            Stores a channel.
            """
            lookup = {'red':0, 'green':1, 'blue':2}
            assert val >= 0 and val <= 1.0
            self.array.vals[3 * self.index + lookup[name]] = val

        def __retrieve(self, name):
            """
            Retrieves a channel.
            """
            lookup = {'red':0, 'green':1, 'blue':2}
            return self.array.vals[3 * self.index + lookup[name]]

        def __getattr__(self, name):
            return self.__retrieve(name)

        def __setattr__(self, name, val):
            self.__store(name, val)
            if self.array.autoupdate:
                self.array.update()

    def __init__(self, spi, size):
        """
        Constructor. Lol.

        @param spi The initialized SPI interface, all right.
        @param size The number of LEDs.
        """
        self.spi = spi
        self.vals = [0, 0, 0] * size
        self.leds = [self.Led(self, i) for i in range(0, size)]
        self.autoupdate = True

    def clear(self):
        """
        Clears the array.
        """
        tmp = self.autoupdate
        self.autoupdate = False
        for led in self.leds:
            led.red = led.green = led.blue = 0
        self.autoupdate = tmp
        if self.autoupdate:
            self.update()

    def update(self):
        """
        Updates the array.
        """
        self.spi.xfer([min(int(val * 256), 255) for val in self.vals])

class PrettyLed:
    """
    Gamma-corrected LED wrapper for prettiness.
    """
    def __init__(self, led):
        """
        Constructor. Lol.
        """
        self.__dict__['led'] = led
        self.__dict__['red'] = 0
        self.__dict__['green'] = 0
        self.__dict__['blue'] = 0

    def set(self, red=0, green=0, blue=0):
        self.led.set(self.__gamma_correct(red),
                                 self.__gamma_correct(green),
                                 self.__gamma_correct(blue))

    def get(self):
        return {key: self.__dict__[key] for key in ['red', 'green', 'blue']}

    def __gamma_correct(self, val):
        return val ** 2.3

    def __getattr__(self, name):
        return self.__dict__[name]

    def __setattr__(self, name, val):
        self.__dict__[name] = val
        self.led.__setattr__(name, self.__gamma_correct(val))

class WallE:
    """
    God.
    """
    def __init__(self, bus, index):
        """
        Constructor. Lol.

        @param bus SPI bus.
        @param bus SPI index.
        """
        self.spi = spidev.SpiDev()
        self.spi.open(bus, index)
        self.spi.lsbfirst = False
        self.spi.max_speed_hz = 1000000
        self.spi.mode = 0b00
        self.array = Array(self.spi, 100)
