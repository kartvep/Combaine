from __abstractfetcher import AbstractFetcher
from combaine.common.loggers import CommonLogger

import time
import httplib

class Timetail(AbstractFetcher):

    def __init__(self, **config):
        self.log = CommonLogger()
        try:
            url = config['timetail_url']
            self.port = config['timetail_port'] if config.has_key('timetail_port') else 3132
            log_name = config['logname']
            self.http_get_url = "%(url)s%(log)s&time=" % { 'url' : url, 'log' : log_name }
        except Exception as err:
            self.log.error("Error in init Timetail getter %s" % err)
            raise Exception

    def getData(self, host_name, timeperiod):
        try:
            self.filter = lambda item: item['Time'] < timeperiod[1]
            req = "%s%i" % (self.http_get_url, int(time.time()) - timeperiod[0])
            self.log.debug('Get data by request: %s' % req)
            conn = httplib.HTTPConnection(host_name, self.port, timeout=1)
            conn.request("GET", req, None)
            resp = conn.getresponse()
            if resp.status == 200:
                self.log.debug("Timetail: HTTP 200 OK")
                #self.log.info("Receive %s bytes from %s" % (resp.getheader("Content-Length"), host_name))
                _ret = [line for line in resp.read().splitlines()]
                self.log.debug("Timetail has received %d line(s)" % len(_ret))
                conn.close()
                return _ret
            else:
                self.log.warning('HTTP responce code for %s is not 200 %i' % (host_name, resp.status))
                return None
        except Exception as err:
            self.log.error('Error while getting data from %s: %s' % (host_name, err))
            return None

PLUGIN_CLASS = Timetail
