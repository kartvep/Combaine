#!/usr/bin/env python

import os
import random
import types
import uuid

import msgpack
import MySQLdb
#from MySQLdb.cursors import DictCursor
#from MySQLdb.cursors import Cursor
from warnings import filterwarnings

from cocaine.worker import Worker
from cocaine.logging import Logger

#Suppressing warnings
filterwarnings('ignore', category=MySQLdb.Warning)
log = Logger()


class MySqlDG(object):

    def __init__(self, **config):
        self.logger = Logger()
        self.place = None
        self.tablename = ''
        try:
            # port = config.get('local_db_port', 3306)
            unix_socket = config.get('MysqlSocket',
                                     "/var/run/mysqld/mysqld.sock")
            self.dbname = config.get('local_db_name', 'COMBAINE')
            self.db = MySQLdb.connect(unix_socket=unix_socket, user='root', )
            self.cursor = self.db.cursor()
            self.cursor.execute('CREATE DATABASE IF NOT EXISTS %s' % self.dbname)
            self.db.commit()
            self.db.select_db(self.dbname)
        except Exception as err:
            self.logger.error('Error in init MySQLdb %s' % err)
            raise Exception

    def putData(self, data, tablename):
        try:
            tablename = tablename.replace('.', '_').replace('-', '_').replace('+', '_')
            line = None
            fname = '/dev/shm/%s-%i' % ('COMBAINE', random.randint(0, 65535))
            with open(fname, 'w') as table_file:
                for line in data:
                    table_file.write('GOPA'.join([str(x) for x in line.values()]) + '\n')
                table_file.close()

                if not line:
                    self.logger.info("Data for mysql is missed")
                    os.remove(table_file.name)
                    return False

                self.logger.debug('Data written to a temporary file %s, size: %d bytes'
                                  % (table_file.name, os.lstat(table_file.name).st_size))

            if not self._preparePlace(line):
                self.logger.error('Unsupported field types. Look at preparePlace()')
                return False

            self.cursor.execute('DROP TABLE IF EXISTS %s' % tablename)
            query = "CREATE TABLE IF NOT EXISTS %(tablename)s %(struct)s ENGINE = MEMORY DATA DIRECTORY='/dev/shm/'" % {'tablename': tablename,
                                                                                                                                  'struct': self.place}
            self.cursor.execute(query)
            self.db.commit()

            query = "LOAD DATA INFILE '%(filename)s' INTO TABLE %(tablename)s FIELDS TERMINATED BY 'GOPA'" % {'filename': table_file.name,
                                                                                                              'tablename': tablename}
            self.cursor.execute(query)
            self.db.commit()
            if os.path.isfile(table_file.name):
                os.remove(table_file.name)
        except Exception as err:
            self.logger.error('Error in putData %s' % err)
            if os.path.isfile(table_file.name):
                os.remove(table_file.name)
            return False
        else:
            self.tablename = tablename
            return True

    def _preparePlace(self, example):
        ftypes = {types.IntType: "INT",
                  types.UnicodeType: "VARCHAR(200)",
                  types.StringType: "VARCHAR(200)",
                  types.FloatType: "FLOAT"}
        try:
            self.place = '( %s )' % ','.join([" %s %s" % (field_name,
                                                          ftypes[type(field_type)])
                                             for field_name, field_type in example.items()])
        except Exception as err:
            self.logger.error('Error in preparePlace() %s' % err)
            self.place = None
            return False
        else:
            return True

    def perfomCustomQuery(self, query_string):
        self.logger.debug("Execute query: %s" % query_string)
        self.cursor.execute(query_string)
        _ret = self.cursor.fetchall()
        self.db.commit()
        return _ret

    def __del__(self):
        if self.db:
            self.cursor.close()
            self.db.commit()
            self.db.close()


def put(request, response):
    raw = yield request.read()
    config, data = msgpack.unpackb(raw)
    tablename = str(uuid.uuid4()).replace("-", "")[:24]
    log.info(str(config))
    log.info("Put data into %s" % tablename)
    try:
        m = MySqlDG(**config)
        m.putData(data, tablename)
    except Exception as err:
        response.error(-100, str(err))
    else:
        response.write(tablename)
        response.close()


def drop(request, response):
    raw = yield request.read()
    config, tablename = msgpack.unpackb(raw)
    try:
        m = MySqlDG(**config)
        drop_query = "DROP TABLE IF EXISTS %s" % tablename
        log.info(drop_query)
        m.perfomCustomQuery(drop_query)
    except Exception as err:
        response.error(-100, str(err))
    else:
        response.write("ok")
        response.close()


if __name__ == "__main__":
    W = Worker()
    W.run({"put": put,
           "drop": drop})
