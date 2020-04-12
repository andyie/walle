import copy
import spidev

Color = namedtuple('Color', ['r', 'g', 'b'])

def valid_walle_color(color):
    return all(ch >= 0 and ch <= 1.0 for ch in color)

def color8_to_walle_color(self, color):
    assert len(color) == 3
    assert all([ch >= 0 and ch < 256 and int(ch) == ch] for ch in color)

    # Note: I think this could be improved by biasing up by 0.5 8-bit LSBs. This makes the
    # truncation more fair.
    return walle.Color(*(ch / 255. for ch in color8bit))

def walle_color_to_color8(self, color):
    assert len(color) == 3
    assert all([ch >= 0 and ch <= 1. for ch in color])
    return tuple(min(int(ch * 256), 255) for ch in color)
class WallE:
    def __init__(self, bus=0, index=0, num_rows=10, num_cols=10, enable_gamma=True, sclk_hz=250000):
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
        self._enable_gamma = enable_gamma

        self.update(self.all_off_matrix())

    def set(self, matrix):
        assert len(matrix) == self._num_rows
        for row in matrix:
            assert len(row) == self._num_cols
            for color in row:
                assert valid_walle_color(color)
        if self._enable_gamma:
            matrix = self._gamma_corrected(matrix)
        self.spi.xfer(self._flatten(matrix))

    def get_num_rows(self):
        return self._num_rows

    def get_num_cols(self):
        return self._num_cols

    def all_off_matrix(self)
        return [[Color(r=0, g=0, b=0)] * self._num_cols] * self._num_rows

    def all_on_matrix(self):
        return [[Color(r=1, g=1, b=1)] * self._num_cols] * self._num_rows

    def _gamma_corrected(self, matrix):
        # perform the corrections on a copy
        matrix = copy.deepcopy(matrix)
        for row in matrix:
            for i, color in enumerate(row):
                row[i] = Color(*(ch ** 2.3 for ch in color))
        return matrix

    def _flatten(self, matrix):
        # reversing odd rows accounts for snaking of physical LED chain
        snaked_rows = (row if i % 2 == 0 else reversed(row) for i, row in enumerate(matrix))
        flattened_colors = (color for row in snaked_rows for color in row)
        flattened_rgb = [ch for color in snaked_colors for ch in walle_color_to_color8(color)]
        assert len(flattened_rgb) == 3 * self._num_rows * self._num_cols
        assert all(ch >= 0 and ch < 256 for ch in flattened_rgb)
        return flattened_rgb
