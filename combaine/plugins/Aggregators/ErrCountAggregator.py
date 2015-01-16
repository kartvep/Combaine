import re
import itertools

from __abstractaggregator import RawAbstractAggregator
from combaine.common.loggers import CommonLogger
from collections import defaultdict

import sys
from subprocess import Popen, PIPE

class ErrCountAggregator(RawAbstractAggregator):

    def __init__(self, **config):
        self.logger = CommonLogger()
        super(ErrCountAggregator, self).__init__()
        self.name = config['name']

        self.q_dict = {"http_host": config["request"]["http_host_field"],
                      "geturl" : "SUBSTRING_INDEX(%s, '?', 1)" % config["request"]["geturl_field"]}
        self.q_host_url = "%(http_host)s, %(geturl)s" % self.q_dict
        self.q_head = "SELECT %s, COUNT(*) from %%TABLENAME%%" % self.q_host_url
        self.q_tail = "GROUP BY %s" % self.q_host_url

        mk_q_dict = lambda x: x.update(self.q_dict) or x
        self.q_blacklist = " and ".join(["%(http_host)s != '%(i)s' and %(geturl)s != '%(i)s'" % 
                                         mk_q_dict({'i': i})
                                         for i in config["blacklist"]])
        # name of juggler event
        self.check_name = config["monitoring"]["name"] 
        # response code >= low and < high
        self.check_code = tuple(config["monitoring"]["code"]) 
        self._limits = tuple(config["limits"].pop("default"))
        self.limits = dict([ (key, tuple(val)) for key, val in config["limits"].items() ])

    def _query(self, code=None):
        '''Renders SQL queries.'''
        q = [self.q_head]
        if code or self.q_blacklist:
            q.append("WHERE")
            if code: q.append("http_status >= %s and http_status < %s" % code)
            if code and self.q_blacklist: q.append("and")
            if self.q_blacklist: q.append(self.q_blacklist)

        q.append(self.q_tail)
        q = " ".join(q)
        return self.table_regex.sub(self.dg.tablename, q)

    def aggregate(self, host_name, timeperiod):
        '''Doing the work.'''

        def send_juggler(msg):
            self.logger.debug("%s, %s:%s" % (host_name, msg.state, msg.txt))
            p = Popen(["sudo", "/usr/bin/juggler_queue_event",
                                   "--host", host_name,
                                   "-s", str(msg.state),
                                   "-n", self.check_name,
                                   "-d", msg.txt,
                                  ],
                      stderr = PIPE, stdout = PIPE)
            output = '; '.join(p.communicate()).replace('\n', '\\n')
 
            if p.returncode != 0:
                self.logger.error("send_jugler failed: %s -> %s" % (p.returncode, output))
            else:
                self.logger.info("sucessfully sent to juggler")

        class Msg:
            '''Juggler message class.
               Contains the most critical data was stored. Drops less critical records'''
            def __init__(self, state=0, txt="Ok"):
                self.state = state
                self.txt = txt
    
            def add (self, state, txt):
                if state == self.state:
                    self.txt += "; %s" % txt
                elif state > self.state:
                    self.state = state
                    self.txt = txt
            
        db = self.dg
        rekey = lambda val: ((val[0],val[1]), val[2]) 
        reqs_all = dict(map(rekey, db.perfomCustomQuery(self._query())))
        reqs_all["_TOTAL_"] = sum(reqs_all.values())
        reqs_err = dict(map(rekey, db.perfomCustomQuery(self._query(self.check_code))))
        reqs_err["_TOTAL_"] = sum(reqs_err.values())
        err_prct = ( (handler,
                      total,
                      reqs_err.get(handler, 0), 
                      round(
                             float(reqs_err.get(handler, 0)) / total * 100,
                             1)
                     ) for handler, total in reqs_all.items() )

        self.logger.debug("%s %s%%" % (host_name, 
                                     float(sum(reqs_err.values())) / sum(reqs_all.values()) * 100))

        juggler_msg = Msg(0, "Ok")

        for handler, requests, errors, percents in err_prct:
            vhost = handler[0]
            handler = "".join(handler)
            max_errs, min_reqs = self.limits.get(vhost, self._limits)

            if percents >= max_errs and requests <= min_reqs:
                #warning
                msg = "%s - %s%% (%s/%s)" % (handler, percents, errors, requests)
                juggler_msg.add(1, msg)
            elif percents >= max_errs and requests > min_reqs:
                #critical
                msg = "%s - %s%% (%s/%s)" % (handler, percents, errors, requests)
                juggler_msg.add(2, msg)

            if errors:
                # TODO
                #send to dashboard
                pass

        send_juggler(juggler_msg)

        #Just stub
        return self.name, self._pack(None, timeperiod[0])

    def _pack(self, data, time):
        '''Just stub'''
        return {'time':time, 'res':[]}

    def _unpack(self, data):
        '''Just stub'''
        return None, None
   
    def aggregate_group(self, data):
        '''Just stub'''
        raise StopIteration

PLUGIN_CLASS = ErrCountAggregator
