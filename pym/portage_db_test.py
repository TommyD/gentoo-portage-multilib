#!/usr/bin/python -O

import portage_db_template,portage_db_anydbm,portage

portage_db_template.test_database(portage_db_anydbm.database,"/var/cache/edb/dep","sys-apps",portage.auxdbkeys)

