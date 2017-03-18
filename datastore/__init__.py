import SimpleXMLRPCServer
import logging
import logging.handlers
import os
import sys
import MySQLdb
import base64
import xmlrpclib
import inspect
import importlib

DATASTORE_BASEDIR = "/usr/lib/datastore"
if sys.version_info.major == 3:
	DATASTORE_BASEDIR = DATASTORE_BASEDIR+"3"
	import ldap3
	import socketserver
else:
	import ldap
	import SocketServer

PLUGINS_DIR = DATASTORE_BASEDIR + "/plugins"
# data acces mode (r/w)
AUTHMODE_NONE = 0
AUTHMODE_READ = 1
AUTHMODE_WRITE = 2

# data types
# non empty string
VARTYPE_STRING = "S"
# base64 stored text
VARTYPE_PASSWORD = "P"
# any value, including empty string
VARTYPE_ANY = "A"
# file
VARTYPE_FILE = "F"

#Datastore data types
DSTYPE_VAR = 0
DSTYPE_FILE = 1
DSTYPE_DB =2


# Set up logging
#logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
handler = logging.handlers.SysLogHandler(address = '/dev/log')
formatter = logging.Formatter('%(module)s.%(funcName)s: %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)

class datastore_auth(object):
	def __init__(self, ldapserver, userdn, groupdn, binddn="", bindpass=""):
		self.ldapserver = ldapserver
		self.userdn = userdn
		self.groupdn = groupdn
		self.binddn = binddn
		self.bindpass = bindpass

	def initialize(self):
		try:
			self.ld = ldap.initialize(self.ldapserver)
			self.ld.protocol_version = ldap.VERSION3
			retcode = True
		except:
			retcode = False

		return retcode

	def test_credentials(self, username, userpass):
		if not self.initialize():
			return False

		dn = "uid="+username+","+self.userdn
		try:
			self.ld.simple_bind_s(dn, userpass)
			return True
		except:
			return False
		
	def list_groups(self, username):
		glist = []
		if self.initialize():
			searchScope = ldap.SCOPE_SUBTREE
			retrieveAttributes = [ 'cn' ] 
			searchFilter = "memberuid="+username
			if self.binddn and self.bindpass:
				self.ld.simple_bind_s(self.binddn, self.bindpass)

			ldap_result_id = self.ld.search(self.groupdn, searchScope, searchFilter, retrieveAttributes)
			while 1:
				result_type, result_data = self.ld.result(ldap_result_id, 0)
				if (result_data == []):
					break
				else:
					if result_type == ldap.RES_SEARCH_ENTRY:
						glist.append(result_data[0][1]['cn'][0])

		return glist


# Create class datastore_database
class datastore_database(object):
	def __init__(self,host,user,passwd,dbname):
		self.dbhost=host 
		self.dbuser=user
		self.dbpass=passwd
		self.dbname=dbname
		self._initialized_conn = False
		self._initialized_cursor = False 		

	def init_db(self):
		#connect
		if self._initialized_conn:
			try:
				self.db_conn.ping(True)
				return True
			except:
				self._initialized_conn = False
		
		self._initialized_cursor = False 		
		try:
			self.db_conn = MySQLdb.connect(self.dbhost, self.dbuser, self.dbpass, self.dbname)
			self._initialized_conn = True
		except:
			self._initialized_conn = False

		return self._initialized_conn

	
	def close(self, db_conn):
		if self._initialized_conn:
			self.db_conn.close()			
	
	def cursor_execute(self, query):
		if self.init_db():
			if not self._initialized_cursor:
				try:
					self.cursor = self.db_conn.cursor()
					self._initialized_cursor = True

				except:
					return False 

			try:	
				self.cursor.execute(query)
				return True
			except:
				return False

		return False

	def delete(self, namespace, varname):
		if self.cursor_execute("DELETE FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			self.db_conn.commit()
			return True

		self.db_conn.rollback()
		return False

	def update(self, namespace, varname, varvalue, vartype=VARTYPE_STRING):
		succeed = False
		if ( vartype == VARTYPE_PASSWORD ):
			varvalue = base64.b64encode(varvalue)

		if not self.cursor_execute("SELECT * FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			return False
		if len(self.cursor.fetchall()) > 0 :
			# do update
			succeed = self.cursor_execute("UPDATE varvalues SET varvalue='%s', vartype='%s' WHERE namespace='%s' AND varname='%s';" % (varvalue, vartype, namespace, varname))
		else:
			# do insert
			succeed = self.cursor_execute("INSERT INTO varvalues(namespace, varname, varvalue, vartype) VALUES ('%s', '%s', '%s', '%s');" % (namespace, varname, varvalue, vartype))
			
		if succeed:
			self.db_conn.commit()
			return True
		else:
			# Rollback in case there is any error
			self.db_conn.rollback()
			return False


	def read(self, namespace, varname):
		if self.cursor_execute("SELECT varvalue, vartype FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			# get_result = (cur.fetchall())[0][0]
			# comprobar el numero de filas leidas por si no hay
			try:
				first_row =(self.cursor.fetchall())[0]
				# prepare data
				if ( first_row[1] == VARTYPE_PASSWORD ):
					get_data = base64.b64decode(first_row[0])
				else:
					get_data = first_row[0]
			except:
				get_data = ""
		return get_data

	def dbread(self, namespace, varname):
		if self.cursor_execute("SELECT dbhost,dbname, dbuser,dbpass FROM dbvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			# get_result = (cur.fetchall())[0][0]
			# comprobar el numero de filas leidas por si no hay
			try:
				first_row =(self.cursor.fetchall())[0]
				get_data = [first_row[0:2], base64.b64decode(first_row[3])]
			except:
				get_data = []
		return get_data

	def dbupdate(self, namespace, varname, vardata):
		succeed = False
		if not self.cursor_execute("SELECT * FROM dbvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			return False
		if len(self.cursor.fetchall()) > 0 :
			# do update
			succeed = self.cursor_execute("UPDATE dbvalues SET dbhost='%s', dbname='%s', dbuser='%s', dbpass='%s' WHERE namespace='%s' AND varname='%s';" % (vardata[0], vardata[1], vardata[2], base64.b64encode(vardata[3])))
		else:
			# do insert
			succeed = self.cursor_execute("INSERT INTO dbvalues(namespace, varname, dbhost, dbname, dbuser,dbpass) VALUES ('%s', '%s', '%s', '%s', '%s', '%s');" % (namespace, varname, vardata[0], vardata[1], vardata[2], base64.b64encode(vardata[3])))
			
		if succeed:
			self.db_conn.commit()
			return True
		else:
			# Rollback in case there is any error
			self.db_conn.rollback()
			return False


	def get_filepath(self, namespace):
		if self.cursor_execute("SELECT filepath FROM filepaths WHERE namespace='%s';" % (namespace)):
			filepath = (self.cursor.fetchall())[0][0]
		else:
			filepath = ""
		return filepath
	
	def test_auth(self, group_list, namespace, varname, accesslevel, dstype = DSTYPE_VAR):
		auth_user = False
		selectindex = dstype
		#search in database
		for g in group_list:
			# do SQL query
			if self.cursor_execute("SELECT authvar,authfile,authdb FROM auth WHERE username='%s' AND namespace='%s' AND (varname='%s' OR varname='' OR varname IS NULL);" % (g, namespace, varname)):
				# print all the first cell of all the rows
				for row in self.cursor.fetchall():
					if ( row[selectindex] >= accesslevel ):
						auth_user = True
		return auth_user


# Lets go multi-thread (Threaded mix-in) 

class AsyncXMLRPCServer(SocketServer.ThreadingMixIn,
                        SimpleXMLRPCServer.SimpleXMLRPCServer): pass

# Create class Server with exposed methods
class datastore_core_server(object):
	def __init__(self, ds_auth, ds_database, debug_mode = False):
		self.ds_auth = ds_auth
		self.ds_database = ds_database	
		self.debug_mode = debug_mode

	def _get_groups(self, username, userpass):
		valid_user = False
		log_message = 'user validation error'
		if username == 'anonymous':
			log_message = 'anonymous user is ever welcome ...'
			valid_user = True
			glist = [ username ]
			return glist
		else:
			# validate credentials in ldap ...
			if self.ds_auth.test_credentials(username, userpass):
				valid_user = True
				glist = [ 'anonymous', username ]
			else:
				valid_user = False	
		if valid_user:
			log_message = 'user validation successfully'
		else:
			glist = []
		
		if self.debug_mode:
			log.debug('validate_user(%s): '+log_message, username)
		# get group list
		log_message = 'LDAP groups found:'
		ldap_groups = self.ds_auth.list_groups(username)
		for g in ldap_groups:
			log_message = log_message + ' ' + g
			glist.append('@'+g)
			
		if self.debug_mode:
			log.debug('get_groups(%s): '+log_message, username)
		return glist

	def _test_auth_var(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth(username, userpass, namespace, varname, accesslevel, DSTYPE_VAR)

	def _test_auth_file(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth(username, userpass, namespace, varname, accesslevel, DSTYPE_FILE)

	def _test_auth_db(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth(username, userpass, namespace, varname, accesslevel, DSTYPE_DB)

	def _test_auth(self, username, userpass, namespace, varname, accesslevel, dstype=DSTYPE_VAR):
		auth_user = self.ds_database.test_auth(self._get_groups(username,userpass), namespace, varname, accesslevel, dstype)
		if auth_user:
			log_message = 'Access granted for user (%s)'
		else:
			log_message = "Access denied for user (%s)"
				
		if self.debug_mode:
			log.debug('database access: '+log_message,username)

		return auth_user

	def _is_valid_data(self, varvalue, vartype):
		if ( vartype == VARTYPE_STRING):
			if ( varvalue == '' ):
				return False
		return True

	
	def test_auth_var(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth_var(username, userpass, namespace, varname, accesslevel)

	def test_auth_file(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth_file(username, userpass, namespace, varname, accesslevel)

	def test_auth_db(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth_db(username, userpass, namespace, varname, accesslevel)

	def put_value(self, username, userpass, namespace, varname, varvalue, vartype=VARTYPE_STRING):
		put_result = False
		log_message = "put_value: not authorized"
		if not self._is_valid_data(varvalue, vartype):
			log_message = "put_value: invalid data"
		elif self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_WRITE):
			if self.ds_database.update(namespace, varname, varvalue, vartype):
				log_message = "successfully put_value"
				put_result = True
			else:
				log_message = "error in  put_value"

		if self.debug_mode:
			log.debug(log_message)

		return put_result	
			
	def put_dbcredentials(self, username, userpass, namespace, varname, vardata):
		put_result = False
		log_message = "put_dbcredentials: not authorized"
		if self._test_auth_db(username, userpass, namespace, varname, AUTHMODE_WRITE):
			if self.ds_database.dbupdate(namespace, varname, vardata):
				log_message = "successfully put_dbcredentials"
				put_result = True
			else:
				log_message = "error in  put_dbcredentials"

		if self.debug_mode:
			log.debug(log_message)

		return put_result	
			
	def del_value(self, username, userpass, namespace, varname):
		del_result = False
		log_message = "del_value: not authorized"
		if self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_WRITE):
			if self.ds_database.delete(namespace, varname):
				log_message = "del_value: success"
				del_result = True
			else:
				log_message = "del_value: error deleting value"
				
		if self.debug_mode:
			log.debug(log_message)
			
		return del_result

	def get_value(self, username, userpass, namespace, varname):
		log_message = "get_value: not authorized"
		get_data = ""
		if self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_READ):
			log_message = "get_value: authorized"
			get_data = self.ds_database.read(namespace, varname)

		if self.debug_mode:
			log.debug(log_message)

		return get_data

	def get_dbcredentials(self, username, userpass, namespace, varname):
		log_message = "get_dbcredentials: not authorized"
		get_data = ""
		if self._test_auth_db(username, userpass, namespace, varname, AUTHMODE_READ):
			log_message = "get_dbcredentials: authorized"
			get_data = self.ds_database.dbread(namespace, varname)

		if self.debug_mode:
			log.debug(log_message)

		return get_data

	def _put_file(self, fname, arg):
		# do update
		try:
			with open(fname, "wb") as handle:
				handle.write(arg.data)
			handle.close()

		except:
			return False

		return True

	def put_file(self, username, userpass, namespace, fname, arg):
		put_result = False
		log_message = "put_file: not authorized"
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path to store files
			filepath = self.ds_database.get_filepath(namespace)
			if filepath:
				if self._put_file(filepath+"/"+os.path.basename(fname), arg):
					log_message = "file successfully write"
					put_result = True
			else:
				log_message = "error reading path"
		if self.debug_mode:
			log.debug('put_file(%s): '+log_message, fname)

		return put_result

	def del_file(self, username, userpass, namespace, fname):
		del_result = False
		log_message = "del_file: not authorized"
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path to store files
			filepath = self.ds_database.get_filepath(namespace)
			if filepath:
				# do update
				try:
					os.remove(filepath+"/"+os.path.basename(fname))
					log_message = "file successfully deleted"
					del_result = True

				except:
					log_message = "error deleting file"

			else:
				log_message = "error reading path"

		if self.debug_mode:
			log.debug('del_file(%s): '+log_message, fname)

		return del_result

	def get_file(self, username, userpass, namespace, fname):
		log_message = "get_file: not authorized"
		binary_data = xmlrpclib.Binary('')
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path where files are stored
			filepath = self.ds_database.get_filepath(namespace)
			if filepath:
				# do update
				try:

					with open(filepath+"/"+fname, "rb") as handle:
    						binary_data = xmlrpclib.Binary(handle.read())
					handle.close()
					log_message = "file successfully read"

				except:
					log_message = "error reading file"

			else:
				log_message = "error reading path"

		if self.debug_mode:
			log.debug('get_file(%s): '+log_message, fname)

		return binary_data



class datastore_plugin(datastore_core_server):

	def test_auth_var(self, username, userpass, varname, accesslevel):
		return super(datastore_plugin, self).test_auth_var(username, userpass, self.__class__.__name__, varname, accesslevel)

	def test_auth_file(self, username, userpass, varname, accesslevel):
		return super(datastore_plugin,self).test_auth_file(username, userpass, self.__class__.__name__, varname, accesslevel)

	def test_auth_db(self, username, userpass, varname, accesslevel):
		return super(datastore_plugin,self).test_auth_db(username, userpass, self.__class__.__name__, varname, accesslevel)

	def put_value(self, username, userpass, varname, varvalue, vartype=VARTYPE_STRING):
		return super(datastore_plugin,self).put_value(username, userpass, self.__class__.__name__, varname, varvalue, vartype)
	
	def del_value(self, username, userpass, varname):
		return super(datastore_plugin,self).del_value(username, userpass, self.__class__.__name__, varname)

	def get_value(self, username, userpass, varname):
		return super(datastore_plugin,self).get_value(username, userpass, self.__class__.__name__, varname)

	def put_file(self, username, userpass, fname, arg):
		return super(datastore_plugin,self).put_file(username, userpass, self.__class__.__name__, fname, arg)

	def del_file(self, username, userpass, fname):
		return super(datastore_plugin,self).del_file(username, userpass, self.__class__.__name__, fname)

	def get_file(self, username, userpass, fname):
		return super(datastore_plugin,self).get_file(username, userpass, self.__class__.__name__, fname)

	def put_dbcredentials(self, username, userpass, varname, vardata):
		return super(datastore_plugin,self).put_dbcredentials(username, userpass, self.__class__.__name__, varname, vardata)

	def get_dbcredentials(self, username, userpass, varname):
		return super(datastore_plugin,self).get_dbcredentials(username, userpass, self.__class__.__name__, varname)

class datastore_server(datastore_core_server):
	def __init__(self, ds_auth, ds_database, server_name="", debug_mode = False):
		super(datastore_server,self).__init__(ds_auth, ds_database, debug_mode)
		if not server_name:
			server_name = "datastore"

		plugins_dirlist = [ PLUGINS_DIR, DATASTORE_BASEDIR+"/"+server_name+"-plugins" ]

		for plugin_path in plugins_dirlist:
			if os.path.isdir(plugin_path):
				if plugin_path not in sys.path:
					sys.path.append(plugin_path)
				for file in os.listdir(plugin_path):
					if file.endswith(".py") and not  file.startswith("_"):
						cname = os.path.splitext(file)[0]
						cmodule = importlib.import_module(cname)
						constructor = getattr(cmodule, cname)
						setattr( self, cname, constructor(ds_auth, ds_database, debug_mode) )


