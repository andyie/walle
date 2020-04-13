#!/usr/bin/env python

import argparse
from contextlib import contextmanager
import copy
import logging, logging.handlers
import re
import select
import socket
import spidev
import struct
import time

DEFAULT_NUM_ROWS = 10
DEFAULT_NUM_COLS = 10

DEFAULT_UDP_SERVER_PORT = 4513

log = logging.getLogger('walle')
log.setLevel('INFO')
_formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s: %(message)s")

_log_console_handler = logging.StreamHandler()
_log_console_handler.setLevel('INFO')
_log_console_handler.setFormatter(_formatter)
log.addHandler(_log_console_handler)

LOG_FILE = '/tmp/walle.log'
_log_file_handler = logging.handlers.RotatingFileHandler(LOG_FILE, mode='a', maxBytes=10*1024*1024,
                                                         backupCount=2)
_log_file_handler.setLevel('DEBUG')
_log_file_handler.setFormatter(_formatter)
log.addHandler(_log_file_handler)
log.info('initializing logging: ' + LOG_FILE)

class Profiler:
    def __init__(self, name, logger, sample_period=100):
        self._name = name
        self._logger = logger
        assert sample_period > 0
        self._sample_period = sample_period

        self._start_t = None
        self._max_t = None
        self._min_t = None
        self._num_samples = 0

    @contextmanager
    def measure(self):
        self.start()
        yield
        self.stop()

    def start(self):
        assert self._start_t is None
        self._start_t = time.perf_counter()

    def stop(self):
        assert self._start_t is not None
        interval_t = time.perf_counter() - self._start_t
        self._start_t = None

        self._min_t = min(interval_t, self._max_t or interval_t)
        self._max_t = max(interval_t, self._max_t or interval_t)
        self._num_samples += 1
        if self._num_samples >= self._sample_period:
            self._logger.info('{} time min={:.3f}s max={:.3f}s'.format(self._name, self._min_t,
                                                                       self._max_t))
            self._min_t = None
            self._max_t = None
            self._num_samples = 0

def all_off_matrix(dim):
    # expected to return a copy
    return [[(0., 0., 0.) for _ in range(dim[0])] for _ in range(dim[1])]

def all_on_matrix(dim):
    # expected to return a copy
    return [[(1., 1., 1.) for _ in range(dim[0])] for _ in range(dim[1])]

def _get_dim(matrix):
    assert len(matrix) > 0
    assert len(set(len(row) for row in matrix)) == 1
    return len(matrix), len(matrix[0])

def _pack_udp(matrix, msg_seq):
    # Verify all rows are the same size
    header = struct.pack('>I', msg_seq)
    if matrix is not None:
        num_rows, num_cols = _get_dim(matrix)
        chs = (ch for row in matrix for color in row for ch in color)
        payload = struct.pack('>II{}f'.format(3 * num_rows * num_cols), num_rows, num_cols, *chs)
        assert len(payload) == 8 + 4 * 3 * num_rows * num_cols
    else:
        payload = bytes()
    return header + payload

def _unpack_udp(data):
    if len(data) != 4 and len(data) < 12:
        raise RuntimeError('invalid packet size {}'.format(len(data)))
    header, payload = data[:4], data[4:]
    msg_seq = struct.unpack('>I', header)[0]
    if len(payload):
        if len(payload) % 4 != 0:
            raise RuntimeError('invalid packet size {}'.format(len(data)))
        num_chs = int((len(payload) - 8) / 4) # truncation will be detected by struct.unpack
        try:
            num_rows, num_cols, *chs = struct.unpack('>II{}f'.format(num_chs), payload)
        except struct.error as e:
            raise RuntimeError(str(e))
        if num_chs != 3 * num_rows * num_cols:
            raise RuntimeError('received dimensions {}x{} do not match channel count'.format(
                num_rows, num_cols, num_chs))
        if min(chs) < 0 or max(chs) > 1.0:
            raise RuntimeError('received channels contain values out of bounds')
        colors = [tuple(chs[i:i + 3]) for i in range(0, len(chs), 3)]
        matrix = [colors[i:i + num_cols] for i in range(0, len(colors), num_cols)]
    else:
        matrix = None
    return matrix, msg_seq

def create_display(target):
    if target == 'spi':
        return LocalLedDisplay()
    else:
        return UdpLedDisplay(target)

class LocalLedDisplay:
    def __init__(self, bus=0, index=0, num_rows=DEFAULT_NUM_ROWS, num_cols=DEFAULT_NUM_COLS, sclk_hz=250000):
        """
        250 KHz SPI should be sufficient to transfer 24 bits of information to 100 LEDs in ~0.01
        seconds. Some occasional glitching was observed on the real display at 1 MHz.
        """
        log.info('using spi {}:{}'.format(bus, index))
        self._spi = spidev.SpiDev()
        self._spi.open(bus, index)
        self._spi.lsbfirst = False
        self._spi.max_speed_hz = sclk_hz
        self._spi.mode = 0b00

        self._dim = (num_rows, num_cols)

        self._current_matrix = None
        self.set(all_off_matrix(self.dim()))

    def set(self, matrix):
        # note: it's important that _current_matrix becomes a copy here. store it before gamma
        # correction.
        assert _get_dim(matrix) == self._dim
        self._current_matrix = copy.deepcopy(matrix)
        self._spi.xfer(self._flatten(self._gamma_corrected(matrix)))

    def get(self):
        return self._current_matrix

    def dim(self):
        return tuple(self._dim)

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

        assert len(flattened_rgb8) == 3 * self._dim[0] * self._dim[1]
        return flattened_rgb8

class UdpLedDisplay:
    def __init__(self, host, port=DEFAULT_UDP_SERVER_PORT, num_rows=DEFAULT_NUM_ROWS,
                 num_cols=DEFAULT_NUM_COLS, timeout=0.1):
        """
        relatively long timeout gives the servers's buffers a break if they are falling behind
        """
        log.info('sending to server {}:{} with timeout {}'.format(host, port, timeout))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._host = host
        self._port = port
        self._dim = (num_rows, num_cols)
        self._timeout = timeout
        self._msg_seq = 0
        self._num_consecutive_timeouts = 0
        self._num_total_timeouts = 0

        self._set_profiler = Profiler('display update', log)

    def dim(self):
        return tuple(self._dim)

    def set(self, matrix):
        # swallow timeouts unless too many have occurred in a row
        with self._set_profiler.measure():
            try:
                self._set(matrix)
            except TimeoutError as e:
                self._num_total_timeouts += 1
                self._num_consecutive_timeouts += 1
                log.warning('timeout setting display: {}'.format(e))
                max_consecutive_timeouts = 10
                if self._num_consecutive_timeouts > max_consecutive_timeouts:
                    log.error('failing setting display after >{} timeouts in a row'.format(
                        max_consecutive_timeouts))
                    raise
            else:
                self._num_consecutive_timeouts = 0

    def _set(self, matrix):
        """
        Idea here is that after set() returns, the display has observed the update. This keeps
        semantics with direct driver set(), naturally throttles calls to set(), provides an answer
        to how to receive replies asynchronously (just don't, do it synchronously), allows the
        sender to directly bound display latency, and keeps the error-handling at the sender.
        """
        # Verify the data matches our own idea of the display dimensions.
        assert _get_dim(matrix) == self._dim

        # Send the data
        tx_msg_seq =  self._msg_seq
        self._msg_seq = (self._msg_seq + 1) % 2**32
        tx = _pack_udp(matrix, tx_msg_seq)
        self.socket.sendto(tx, (self._host, self._port))

        # Wait for the acknowledgement
        start = time.time()
        time_left = self._timeout
        acked = False
        while time_left >= 0 and not acked:
            readers, _, _ = select.select([self.socket], [], [], time_left)
            if self.socket in readers:
                rx, _ = self.socket.recvfrom(4096) # should return immediately
                try:
                    rx_matrix, rx_msg_seq = _unpack_udp(rx)
                except RuntimeError as e:
                    pass
                else:
                    # if message ID does not match, ignore this message. but if dimensions don't
                    # match, that's an error. it's overkill to verify contents.
                    if rx_msg_seq == tx_msg_seq:
                        rx_dim = _get_dim(rx_matrix)
                        if rx_dim != self._dim:
                            raise RuntimeError('Remote display has unexpected dimensions '
                                               '{}x{}'.format(*rx_dim))
                        acked = True
            time_left = self._timeout - (time.time() - start)

        # if we didn't get an ACK, throw TimeoutError
        if not acked:
            raise TimeoutError('did not receive ack for msg {}'.format(tx_msg_seq))

    def get(self):
        """
        Like set(), this interactively fetches the display and blocks until completion. See notes
        above.
        """
        raise RuntimeError('not implemented')

class _UdpLedDisplayServer:
    """
    This was originally implemented as a synchronous socketserver.UDPServer, but became concerned
    about requests backing up in OS buffers. This version only serves the most recent request in the
    RX buffers.
    """
    def __init__(self, host_port, driver):
        self._driver = driver
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(host_port)
        self._last_client = None
        self._last_msg_seq = None

    def serve_forever(self):
        while True:
            # wait for the socket to have pending data, then poll for all pending messages.
            readers, _, _ = select.select([self._socket], [], [])
            msgs = []
            while self._socket in readers:
                msgs.append(self._socket.recvfrom(4096))
                readers, _, _ = select.select([self._socket], [], [], 0)
            assert not readers

            # process messages back-to-front until a valid one is found.
            msg_found = False
            for msg in reversed(msgs):
                # if a message has already been processed, then the rest of the (earlier) messages
                # should be skipped
                data, client_addr = msg
                if msg_found:
                    log.info('{}:{} request skipped'.format(*client_addr))
                    continue

                # if unpacking the message fails, discard
                try:
                    matrix, msg_seq = _unpack_udp(data)
                except RuntimeError as e:
                    log.warning('{}:{} request malformed: {}'.format(*client_addr, e))
                    continue

                # if the dimensions are wrong, discard
                dim = _get_dim(matrix)
                if dim != driver.dim():
                    log.warning('{}:{} request has bad dimensions {}x{}'.format(
                        *client_addr, *dim))
                    continue

                # record the new client
                if self._last_client != client_addr:
                    log.info('new client {}:{}'.format(*client_addr))
                    self._last_client = client_addr
                    self._last_msg_seq = None

                # detect missing messages (for fun)
                if self._last_msg_seq is not None and msg_seq != (self._last_msg_seq + 1) % 2**32:
                    log.warning('{}:{} requests missing between {} and {}'.format(*client_addr,
                            self._last_msg_seq, msg_seq))
                self._last_msg_seq = msg_seq

                # set the new data to the display. if it times out, treat it the same as a discard
                try:
                    driver.set(matrix)
                except TimeoutError as e:
                    log.error('{}:{} request timeout setting display: {}'.format(*client_addr, e))
                    continue

                # acknowledge the request, and signal the remaining messages to be skipped
                ack = _pack_udp(self._driver.get(), msg_seq)
                self._socket.sendto(ack, client_addr)
                msg_found = True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--listen_port', type=int, default=4513, help='UDP server listen port')
    args = parser.parse_args()

    driver = create_display(args.target)
    server = _UdpLedDisplayServer(('', args.listen_port), driver)
    log.info('listening on :{}'.format(args.listen_port))
    server.serve_forever()
