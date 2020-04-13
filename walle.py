#!/usr/bin/env python

import argparse
import collections
import copy
import socketserver
import spidev

def all_off_matrix(dim):
    # expected to return a copy
    return [[(0., 0., 0.) for _ in range(dim[0])] for _ in range(dim[1])]

def all_on_matrix(dim):
    # expected to return a copy
    return [[(1., 1., 1.) for _ in range(dim[0])] for _ in range(dim[1])]

class LedDisplayDriver:
    def __init__(self, bus=0, index=0, num_rows=10, num_cols=10, sclk_hz=250000):
        """
        250 KHz SPI should be sufficient to transfer 24 bits of information to 100 LEDs in ~0.01
        seconds. Some occasional glitching was observed on the real display at 1 MHz.
        """
        self._spi = spidev.SpiDev()
        self._spi.open(bus, index)
        self._spi.lsbfirst = False
        self._spi.max_speed_hz = sclk_hz
        self._spi.mode = 0b00

        self._num_rows = num_rows
        self._num_cols = num_cols

        self._current_matrix = None
        self.set(self.all_off_matrix())

    def set(self, matrix):
        # note: it's important that _current_matrix becomes a copy here
        self._current_matrix = self._gamma_corrected(matrix)
        self._spi.xfer(self._flatten(self._current_matrix))

    def get(self):
        return self._current_matrix

    def dim(self):
        return (self._num_rows, self._num_cols)

    def _gamma_corrected(self, matrix):
        return [[tuple(ch ** 2.3 for ch in color) for color in row] for row in matrix]

    def _flatten(self, matrix):
        # rows are physically wired low to high, so row order must be reversed. every other row must
        # also be internally reversed to account for chain snaking.
        snaked_rows = (row if i % 2 == 0 else reversed(row)
                        for i, row in enumerate(reversed(matrix)))
        flattened_rgb = [ch for row in snaked_rows for color in row for ch in color]

        # convert to 8-bit channels, but verify ranges first
        assert all(ch >= 0 and ch <= 1.0 for ch in flattened_rgb)
        flattened_rgb8 = [min(int(ch * 256), 255) for ch in flattened_rgb]

        assert len(flattened_colors) == 3 * self._num_rows * self._num_cols
        return flattened_colors

class _UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        print('got {} bytes from {}'.format(len(self.request[0]), self.client_address))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4513, help='UDP server listen port')
    args = parser.parse_args()

    server = socketserver.UDPServer(('', args.port), _UdpHandler)
    print('Listening on :{}'.format(server.server_address[1]))
    server.serve_forever()
