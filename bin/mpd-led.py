#!/usr/bin/python2

"""light until mpd is running."""

import os
import logging
import signal
import sys
import subprocess
import time
import traceback


class LED(object):

    """GPIO led control."""

    def __init__(self, port):
        """Initialize led gpio port as writable."""
        port = str(port)
        self._port = port
        if os.path.exists('/sys/class/gpio/gpio%s' % port):
            with open('/sys/class/gpio/unexport', 'w') as f:
                f.write(port)
        with open('/sys/class/gpio/export', 'w') as f:
            f.write(port)
        with open('/sys/class/gpio/gpio%s/direction' % port, 'w') as f:
            f.write('out')

    def on(self):
        """LED on."""
        with open('/sys/class/gpio/gpio%s/value' % self._port, 'w') as f:
            f.write('1')

    def off(self):
        """LED off."""
        with open('/sys/class/gpio/gpio%s/value' % self._port, 'w') as f:
            f.write('0')


def close_gpio(port):
    """finalize gpio port."""
    port = str(port)
    if os.path.exist('/sys/class/gpio/gpio%s' % port):
        with open('/sys/class/gpio/unexport', 'w') as f:
            f.write(port)


class App(object):

    """LED for mpd."""

    def __init__(self, port, logger=None):
        """Intialize mpd/app event."""
        self.led = LED(port)
        self.logger = logger
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)

    def exit(self, signum, frame):
        """led on when exit app."""
        self.logger.info("stop app")
        self.led.on()
        sys.exit(0)

    def run(self):
        """app mainloop."""
        while True:
            try:
                self.led.on()
                time.sleep(1)
                subprocess.check_output('mpc', shell=True)
                while True:
                    # blink when mpd status is changed(play/pause/next/prev)
                    subprocess.check_output('mpc idle', shell=True)
                    self.led.off()
                    time.sleep(0.3)
                    self.led.on()
            except subprocess.CalledProcessError:
                # blink slowly when mpd error/down
                self.led.off()
                time.sleep(1)


def main():
    """Run app mainloop."""
    logging.basicConfig(
        filename='/var/log/mpd-led.log',
        format='[%(levelname)s] %(asctime)s [%(name)s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    try:
        app = App(5, logger)
        app.run()
    except Exception, err:
        logger.critical("app exit with: %s" % str(err))
        logger.critical(traceback.format_exc())

if __name__ == '__main__':
    main()
