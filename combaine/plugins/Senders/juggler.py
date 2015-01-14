import subprocess
import re
import itertools
import urllib

from _abstractsender import AbstractSender

from combaine.common.loggers import CommonLogger
from combaine.common.httpclient import AsyncHTTP
from combaine.common.configloader import parse_common_cfg

STATUSES = {0: "OK",
            3: "INFO",
            1: "WARN",
            2: "CRIT"}


def coroutine(func):
    def start(*args, **kwargs):
        g = func(*args, **kwargs)
        return g
    return start


@coroutine
def make_template_placeholders(inp_aggresults):
    """ Make from aggresults:
    '20x': <dictionary-itemiterator object at 0x27c4998>,
    '30x': <dictionary-itemiterator object at 0x27c4ba8>}
    """
    subgroups = [name for name, _ in inp_aggresults[0].values]
    out_put = dict(((_.aggname, _.values) for _ in inp_aggresults))
    try:
        for subgroup in subgroups:
            yield subgroup, dict((key, next(out_put[key])[1])
                                 for key in out_put.keys())
    except StopIteration:
        print "Stop"


class Juggler(AbstractSender):
    """
    type: juggler
    INFO: ["${50and20x}>-100", "${20x}<0"]
    WARN: ["${50and20x}>1", "${50and20x}<0"]
    CRIT: ["${50and20x}>10", "${50and20x}<0"]
    OK: ["${50and20x}>10", "${50and20x}<0"]
    """

    pattern = re.compile(r"\${([^}]*)}")

    def __init__(self, **cfg):
        self.logger = CommonLogger()
        self._INFO = cfg.get("INFO", [])
        self._WARNING = cfg.get("WARN", [])
        self._CRITICAL = cfg.get("CRIT", [])
        self.checkname = cfg["checkname"]
        self.Aggregator = cfg['Aggregator']
        self.Host = cfg['Host']
        self.Method = cfg['Method']
        self.description = cfg.get("description", "no description")
        self._OK = cfg.get("OK", [])
        self._aggs = list()
        for item in itertools.chain(self._INFO, self._WARNING, self._CRITICAL, self._OK):
            self._aggs += self.pattern.findall(item)
        try:
            self.juggler_hosts =  parse_common_cfg('combaine')["cloud_config"]['juggler_hosts']
        except KeyError:
            self.logger.error("There are no juggler hosts")
            self.juggler_hosts = []
        self._aggs = list(set(self._aggs))

    def _handling_one_expression(self, level, data, name, status):
        http_cli = AsyncHTTP()
        params = {"host": name,
                  "service": urllib.quote(self.checkname),
                  "description": urllib.quote(self.description),
                  "level": STATUSES[status],
        }

        for expression in level:
            code = expression
            for key, value in data.iteritems():
                code, n = re.subn(r"\${%s}" % key, str(value), code)
            try:
                res = eval(code)
                self.logger.info("After substitution in %s %s %s" % (name, code, res))
            except Exception:
                res = False
            if res:
                self._add_check_if_needed(name)
                extra = params.copy()
                extra['description'] = urllib.quote("%s trigger: %s" % (extra['description'], code))
                URLS = dict((juggler_host,
                            "http://%s" % juggler_host +
                            "/api/events/add_event_proxy?host_name={host}&service_name={service}&description={description}&instance_name&status={level}&do=1".format(**extra))
                            for juggler_host in self.juggler_hosts)
                map(self.logger.info, URLS.itervalues())
                http_cli.fetch(URLS)
                return True
        return False

    def send_OK(self, name):
        http_cli = AsyncHTTP()
        params = {"host": name,
                  "service": urllib.quote(self.checkname),
                  "description": urllib.quote(self.description),
                  "level": "OK",
        }
        URLS = dict((juggler_host,
                    "http://%s" % juggler_host +
                    "/api/events/add_event_proxy?host_name={host}&service_name={service}&description={description}&instance_name&status={level}&do=1".format(**params))
                    for juggler_host in self.juggler_hosts)
        http_cli.fetch(URLS)



    def _add_check_if_needed(self, host):
        http_cli = AsyncHTTP()
        params = {"host": self.Host,
                  "service": urllib.quote(self.checkname),
                  "description": urllib.quote(self.description),
                  "methods": self.Method,
                  "child": host,
                  "aggregator": self.Aggregator}

        add_check_urls = dict((juggler_host,
                                "http://%s" % juggler_host +
                                "/api/checks/set_check?host_name={host}&service_name={service}&description={description}&aggregator={aggregator}&do=1".format(**params))
                                for juggler_host in self.juggler_hosts)

        add_children = dict((juggler_host,
                                "http://%s" % juggler_host +
                                "/api/checks/add_child?host_name={host}&service_name={service}&child={child}:{service}&do=1".format(**params))
                                for juggler_host in self.juggler_hosts)

        add_methods_urls = dict((juggler_host,
                                "http://%s" % juggler_host +
                                "/api/checks/add_methods?host_name={host}&service_name={service}&methods_list={methods}&do=1".format(**params))
                                for juggler_host in self.juggler_hosts)
        
        http_cli.fetch(add_check_urls)
        http_cli.fetch(add_children)
        http_cli.fetch(add_methods_urls)

    def send(self, data):
        interest_results = filter(lambda x: x.aggname in self._aggs, data)
        for subgroup_name, subgroup_data in make_template_placeholders(interest_results):
            check_host_name = "%s-%s" % (self.Host, subgroup_name)\
                              if subgroup_name == data[0].groupname\
                              else "%s-%s-%s" % (self.Host,
                                                 data[0].groupname,
                                                 subgroup_name)
            OK = self._handling_one_expression(self._CRITICAL,
                                               subgroup_data,
                                               check_host_name, 2) or\
            self._handling_one_expression(self._WARNING,
                                          subgroup_data,
                                          check_host_name, 1) or\
            self._handling_one_expression(self._INFO,
                                          subgroup_data,
                                          check_host_name, 3) or\
            self._handling_one_expression(self._OK,
                                          subgroup_data,
                                          check_host_name, 0)
            if not OK:
                self.logger.debug("Emit OK manually")
                self.send_OK(check_host_name)
           
PLUGIN_CLASS = Juggler
