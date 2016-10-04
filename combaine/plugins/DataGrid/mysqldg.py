from __abstractdatagrid import AbstractDataGrid
from combaine.common.loggers import DataGridLogger

import logging
import os
import random

import MySQLdb
from MySQLdb.cursors import DictCursor
from MySQLdb.cursors import Cursor
from warnings import filterwarnings

#Suppressing warnings
filterwarnings('ignore', category = MySQLdb.Warning)

class MySqlDG(AbstractDataGrid):

    def __init__(self, **config):
        self.logger = DataGridLogger()
        self.place = None
        self.tablename = ''
        try:
            port = config['local_db_port'] if config.has_key('local_db_port') else 3306 
            unix_socket = config['MysqlSocket'] if config.has_key('MysqlSocket') else "/var/run/mysqld/mysqld.sock"
            self.dbname = config['local_db_name'] if config.has_key('local_db_name') else 'COMBAINE'
            self.db = MySQLdb.connect(unix_socket=unix_socket, user='root')
            self.cursor = self.db.cursor()
            self.cursor.execute('CREATE DATABASE IF NOT EXISTS %s' % self.dbname)
            self.db.commit()
            self.db.select_db(self.dbname)
        except Exception as err:
            self.logger.error('Error in init MySQLdb %s' % err)
            raise Exception

    def putData(self, data, tablename):
        try:
            tablename = tablename.replace('.','_').replace('-','_').replace('+','_')
            line = None
            with open('/dev/shm/%s-%i' % ('COMBAINE', random.randint(0,65535)) ,'w') as table_file:
                for line in data:
                    table_file.write('GOPA'.join([str(x) for x in line.values()])+'\n')
                table_file.close()

                if not line:
                    self.logger.warning("Data for mysql is missed")
                    os.remove(table_file.name)
                    return False
                else:
                    columns = line.keys()
                    indexes = { ('http_status',): '',
                                ('http_host',): '',
                                #('geturl',): 'geturl(10)',
                                ('http_host', 'http_status'): '',
                                #('http_host', 'http_status', 'geturl'): 'http_host, http_status, geturl(10)',
                                ('ssl_session_id',): '',
                                ('request_time',): '',
                                ('upstream_response_time',): '',
                               }

                self.logger.debug('Data written to a temporary file %s, size: %d bytes' % (table_file.name, os.lstat(table_file.name).st_size))

            if not self._preparePlace(line):
                self.logger.error('Unsupported field types. Look at preparePlace()')
                return False

            self.cursor.execute('DROP TABLE IF EXISTS %s' % tablename)
            query = "CREATE TEMPORARY TABLE IF NOT EXISTS %(tablename)s %(struct)s ENGINE = MEMORY DATA DIRECTORY='/dev/shm/'" % { 'tablename' : tablename,\
                                                                                                        'struct' : self.place }
            #query = "CREATE TABLE IF NOT EXISTS %(tablename)s %(struct)s ENGINE = MEMORY DATA DIRECTORY='/dev/shm/'" % { 'tablename' : tablename,\
            self.cursor.execute(query)
            self.db.commit()

            query = "LOAD DATA INFILE '%(filename)s' INTO TABLE %(tablename)s FIELDS TERMINATED BY 'GOPA'" % { 'filename' : table_file.name,\
                                                                                                            'tablename': tablename  }
            self.cursor.execute(query)
            self.db.commit()

            for flds, indx in indexes.items():
                add_index = True
                for fld in flds:
                    if fld not in columns:
                        add_index = False
                if add_index:
                    if not indx: indx = ', '.join(flds)
                    inm = '_'.join(flds)
                    query = 'ALTER TABLE %(tablename)s ADD INDEX %(name)s (%(index)s)' % { 'tablename': tablename, 'name': inm, 'index': indx }
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
        ftypes = { type(1) : "INT",
                   type("string")   : "VARCHAR(200)",
                   type(u"string")  : "VARCHAR(200)",
                   type(1.0)        : "FLOAT"
        }
        try:
            self.place = '( %s )' % ','.join([" %s %s" % (field_name, ftypes[type(field_type)]) for field_name, field_type in example.items()])
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

PLUGIN_CLASS = MySqlDG
