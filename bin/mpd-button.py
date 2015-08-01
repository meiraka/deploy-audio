#!/usr/bin/python2

"""RotarySwitch for mpd control."""


import os
import select
import subprocess
import time
import logging
import traceback


class App(object):

    """RotarySwitch for mpd control."""

    def __init__(self, prev, play, next, logger=None):
        """Open gpio for prev/play/next button."""
        self.logger = logger if logger else logging
        self.logger.info("start app")
        self._values = {}
        self._prev = gpio_open(prev, edge='both')
        self._values[self._prev] = '1'
        self._play = gpio_open(play, edge='both')
        self._values[self._play] = '1'
        self._next = gpio_open(next, edge='both')
        self._values[self._next] = '1'

    def _is_changed(self, fo):
        """Check file data is changed."""
        fo.seek(0)
        new = fo.read().strip()
        if self._values[fo] != new:
            self._values[fo] = new
            return True
        else:
            return False

    def run(self):
        """Wait gpio value is changed."""
        epoll = select.epoll()
        epoll.register(self._prev,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._play,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._next,
                       select.EPOLLIN | select.EPOLLET)
        try:
            while True:
                try:
                    for fileno, event in epoll.poll():
                        if fileno == self._prev.fileno():
                            if self._is_changed(self._prev):
                                if self._values[self._prev] == '0':
                                    subprocess.check_output(
                                        ['/usr/bin/mpc', 'prev'])
                                    subprocess.check_output(
                                        ['/usr/bin/mpc', 'pause'])
                                time.sleep(0.2)
                        if fileno == self._play.fileno():
                            if self._is_changed(self._play):
                                cmd = ('play'
                                       if self._values[self._play] == '0'
                                       else 'pause')
                                subprocess.check_output(
                                    ['/usr/bin/mpc', cmd])
                        if fileno == self._next.fileno():
                            if self._is_changed(self._next):
                                if self._values[self._next] == '0':
                                    subprocess.check_output(
                                        ['/usr/bin/mpc', 'next'])
                                    subprocess.check_output(
                                        ['/usr/bin/mpc', 'pause'])
                                time.sleep(0.2)
                except subprocess.CalledProcessError:
                    time.sleep(1)
        finally:
            epoll.unregister(self._prev)
            epoll.unregister(self._play)
            epoll.unregister(self._next)


def gpio_open(port, mode='r', edge='none'):
    """Open gpio file."""
    if mode not in ['r']:
        raise Exception('unimplemented mode: %s' % mode)
    if edge not in ['none', 'rising', 'falling', 'both']:
        raise Exception('rtfm')
    port = str(port)
    if not os.path.exists('/sys/class/gpio/gpio%s' % port):
        with open('/sys/class/gpio/export', 'w') as f:
            f.write(port)
    if mode == 'r':
        with open('/sys/class/gpio/gpio%s/direction' % port, 'w') as f:
            f.write('in')
        with open('/sys/class/gpio/gpio%s/edge' % port, 'w') as f:
            f.write(edge)
        return open('/sys/class/gpio/gpio%s/value' % port, 'r')


if __name__ == '__main__':
    logging.basicConfig(
        filename='/var/log/mpd-button.log',
        format='[%(levelname)s] %(asctime)s [%(name)s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    try:
        sw = App(66, 67, 68, logger)
        sw.run()
    except Exception, err:
        logger.critical("app exit with: %s" % str(err))
        logger.critical(traceback.format_exc())
