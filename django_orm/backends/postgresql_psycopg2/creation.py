# -*- coding: utf-8 -*-

from django.db.backends.util import truncate_name
from django import VERSION

if VERSION[:2] > (1,3):
    from django.db.backends.postgresql_psycopg2.creation \
        import DatabaseCreation as BaseDatabaseCreation
else:
    from django.db.backends.postgresql_psycopg2.base \
        import DatabaseCreation as BaseDatabaseCreation

import logging
log = logging.getLogger(__name__)

class DatabaseCreation(BaseDatabaseCreation):
    def install_hstore_contrib(self):
        # point to test database
        self.connection.close()
        test_database_name = self._get_test_db_name()
        self.connection.settings_dict["NAME"] = test_database_name

        # Test to see if HSTORE type was already installed
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 FROM pg_type WHERE typname='hstore';")
        if cursor.fetchone():
            # skip if already exists
            return
        
        if self.connection.postgres_version >= 90100:
            cursor.execute('CREATE EXTENSION hstore;')
            cursor.execute('COMMIT;')
        else:
            raise Exception("hstore type not found in the database. "
                        "please install it from your 'contrib/hstore.sql' file")

    def create_test_db(self, *args, **kwargs):
        self.connection.pool_enabled = False
        return super(DatabaseCreation, self).create_test_db(*args, **kwargs)
    
    def _create_test_db(self, verbosity, autoclobber):
        super(DatabaseCreation, self)._create_test_db(verbosity,autoclobber)
        self.install_hstore_contrib()

    def sql_indexes_for_model(self, model, style):
        output = super(DatabaseCreation, self).sql_indexes_for_model(model, style)
        additional_indexes = getattr(model, 'additional_indexes', [])
        if not isinstance(additional_indexes, (list, tuple)):
            raise Exception("aditional_indexes must be a list or tuple")
        
        for indexitem in additional_indexes:
            if indexitem.endswith(";"):
                output.append(indexitem)
        return output

    def sql_indexes_for_field(self, model, f, style):
        kwargs = VERSION[:2] >= (1, 3) and {'connection': self.connection} or {}
        if f.db_type(**kwargs) in ('hstore', 'tsvector'):
            if not f.db_index:
                return []

            # create GIST index for hstore column
            qn = self.connection.ops.quote_name
            index_name = '%s_%s_gist' % (model._meta.db_table, f.column)
            clauses = [style.SQL_KEYWORD('CREATE INDEX'),
                style.SQL_TABLE(qn(truncate_name(index_name, self.connection.ops.max_name_length()))),
                style.SQL_KEYWORD('ON'),
                style.SQL_TABLE(qn(model._meta.db_table)),
                style.SQL_KEYWORD('USING GIST'),
                '(%s)' % style.SQL_FIELD(qn(f.column))]

            # add tablespace clause
            tablespace = f.db_tablespace or model._meta.db_tablespace
            if tablespace:
                sql = self.connection.ops.tablespace_sql(tablespace)
                if sql:
                    clauses.append(sql)

            clauses.append(';')
            return [' '.join(clauses)]

        return super(DatabaseCreation, self).sql_indexes_for_field(model, f, style)
