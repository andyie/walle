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

class Stats:
    def __init__(self, name, logger, period=100):
        assert period > 0
        self._name = name
        self._logger = logger
        self._period = period

        self._max = None
        self._min = None
        self._sum = None
        self._num= 0

    def sample(self, val):
        self._min = min(val, self._max or val)
        self._max = max(val, self._max or val)
        self._sum = val + (self._sum or 0)
        self._num += 1
        if self._num >= self._period:
            self._logger.info('{} min={:.3f}s avg={:.3f}s max={:.3f}s num={}'.format(
                self._name, self._min, self._sum / self._num, self._max, self._num))
            self._min = None
            self._max = None
            self._sum = None
            self._num = 0

class Profiler:
    def __init__(self, name, logger):
        self._stats = Stats(name + ' time', logger)
        self._t0 = None

    @contextmanager
    def measure(self):
        self.start()
        yield
        self.stop()

    def start(self):
        assert self._t0 is None
        self._t0 = time.perf_counter()

    def stop(self):
        assert self._t0 is not None
        t = time.perf_counter() - self._t0
        self._t0 = None
        self._stats.sample(t)

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
    def __init__(self, bus=0, index=0, num_rows=DEFAULT_NUM_ROWS, num_cols=DEFAULT_NUM_COLS, sclk_hz=500000):
        """
        note: for reference, 100 LEDs can be physically updated in ~0.01 seconds at ~250 khz. note
        that occasional glitching was observed on the real display at 1 mhz.
        """
        log.info('using spi {}:{} at {} khz'.format(bus, index, sclk_hz / 1e3))
        self._spi = spidev.SpiDev()
        self._spi.open(bus, index)
        self._spi.lsbfirst = False
        self._spi.max_speed_hz = sclk_hz
        self._spi.mode = 0b00

        self._spi_xfer_profiler = Profiler('spi xfer', log)

        self._dim = (num_rows, num_cols)

        self._current_matrix = None
        self.set(all_off_matrix(self.dim()))

    def set(self, matrix):
        # note: it's important that _current_matrix becomes a copy here. store it before gamma
        # correction.
        assert _get_dim(matrix) == self._dim
        self._current_matrix = copy.deepcopy(matrix)
        with self._spi_xfer_profiler.measure():
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
                 num_cols=DEFAULT_NUM_COLS, synchronous=False, timeout=0.1):
        """
        relatively long timeout gives the servers's buffers a break if they are falling behind
        """
        log.info('using server {}:{}'.format(host, port))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._host = host
        self._port = port
        self._dim = (num_rows, num_cols)
        self._synchronous = synchronous
        self._timeout = timeout
        self._msg_seq = 0
        self._num_total_timeouts = 0

        self._request_profiler = Profiler('display request', log)

    def dim(self):
        return tuple(self._dim)

    def set(self, matrix):
        self._request(matrix, self._synchronous)

    def get(self):
        return self._request(None, True)

    def _request(self, matrix, wait_for_ack):
        with self._request_profiler.measure():
            try:
                ack_matrix = self._request_impl(matrix, wait_for_ack)
                return ack_matrix
            except TimeoutError as e:
                self._num_total_timeouts += 1
                log.warning('timeout requesting display: {}'.format(e))

        return None

    def _request_impl(self, matrix, wait_for_ack):
        # sanity-check the matrix (if any) has expected dimensions
        assert matrix is None or _get_dim(matrix) == self._dim

        # send the data
        tx_msg_seq =  self._msg_seq
        self._msg_seq = (self._msg_seq + 1) % 2**32
        tx = _pack_udp(matrix, tx_msg_seq)
        self.socket.sendto(tx, (self._host, self._port))

        # wait for acknowledgement if requested. otherwise, flush the socket RX queue just to be
        # polite to the OS buffers
        if wait_for_ack:
            start_t = time.time()
            time_left = self._timeout
            while time_left >= 0:
                readers, _, _ = select.select([self.socket], [], [], time_left)
                if self.socket in readers:
                    rx, _ = self.socket.recvfrom(4096) # should return immediately
                    try:
                        # the request is considered acknowledged if the sequence numbers match. don't
                        # bother verifying dimensions or contents, this may not apply (e.g., if this is
                        # query-only)
                        rx_matrix, rx_msg_seq = _unpack_udp(rx)
                        if rx_msg_seq == tx_msg_seq:
                            return rx_matrix
                    except RuntimeError as e:
                        pass
                time_left = self._timeout - (time.time() - start_t)

            # no acknowledgement in time
            raise TimeoutError('ack timeout for msg {}'.format(tx_msg_seq))
        else:
            num_flushed = 0
            while num_flushed < 10:
                readers, _, _ = select.select([self.socket], [], [], 0)
                if not readers:
                    break
                self.socket.recvfrom(4096) # should return immediately
                num_flushed += 1
            return None

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
        self._last_update_client = None
        self._last_update_msg_seq = None
        self._select_profiler = Profiler('select wait', log)
        self._request_profiler = Profiler('request handling', log)

    def _parse_request_data(self, data):
        # parse the request and validate the matrix, if present
        matrix, msg_seq = _unpack_udp(data)
        if matrix:
            dim = _get_dim(matrix)
            if dim != self._driver.dim():
                raise RuntimeError('incorrect dimensions {}x{}'.format(*dim))
        return (matrix, msg_seq)

    def _process_requests(self):
        # parse all pending requests, keeping track of the last one that actually requests a display
        # update
        requests = []
        num_recv = 0
        last_update_request = None
        while num_recv < 10:
            # break out if there are no more pending messages
            readers, _, _ = select.select([self._socket], [], [], 0)
            if not readers:
                break

            # receive and parse the pending message
            (data, client_addr) = self._socket.recvfrom(4096)
            num_recv += 1
            try:
                matrix, msg_seq = self._parse_request_data(data)
                request = (client_addr, matrix, msg_seq)
                requests.append(request)
                if matrix:
                    last_update_request = request
            except RuntimeError as e:
                log.warning('{}:{} request malformed: {}'.format(*client_addr, e))

        # acknowledge all requests, but only actuate the last update request as an optimization
        for request in requests:
            client_addr, matrix, msg_seq = request

            # perform processing for requests containing a matrix
            if matrix:
                # record any new client sending display updates. I guess this could cause some spam
                # if there are lots of client changes...
                if self._last_update_client != client_addr:
                    log.info('new update client {}:{}'.format(*client_addr))
                    self._last_update_client = client_addr
                    self._last_update_msg_seq = None

                # detect missing messages (for fun)
                if self._last_update_msg_seq is not None and \
                   msg_seq != (self._last_update_msg_seq + 1) % 2**32:
                    log.warning('{}:{} requests missing between {} and {}'.format(*client_addr,
                            self._last_update_msg_seq, msg_seq))
                self._last_update_msg_seq = msg_seq

                # if this request is the freshest update request in the queue, actuate it.
                # otherwise, log that the message was skipped
                if request is last_update_request:
                    try:
                        self._driver.set(matrix)
                    except TimeoutError as e:
                        # TODO: can delete this timeout after we make set() asynchronous
                        # also, note that we will acknowledge this request even though it timed
                        # out, which is weird
                        log.error('{}:{} request timeout setting display: {}'.format(*client_addr, e))
                else:
                    log.warning('{}:{} request skipped'.format(*client_addr))

            # all valid requests are acknowledged
            ack = _pack_udp(self._driver.get(), msg_seq)
            self._socket.sendto(ack, client_addr)

    def serve_forever(self):
        while True:
            # wait for the socket to have pending data, then process the pending requests
            with self._select_profiler.measure():
                readers, _, _ = select.select([self._socket], [], [])
            with self._request_profiler.measure():
                self._process_requests()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--listen_port', type=int, default=4513, help='UDP server listen port')
    args = parser.parse_args()

    driver = create_display(args.target)
    server = _UdpLedDisplayServer(('', args.listen_port), driver)
    log.info('listening on :{}'.format(args.listen_port))
    server.serve_forever()
