import ldap
import SocketServer
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

# Create class datastore_database
class datastore_database(self, host, user,passwd,dbname):
	def __init__(self,host,user,passwd,dbname):
		self.dbhost=host 
		self.dbpass=passwd
		self.dbname=dbname
		self._initialized_conn = False
		self._initialized_cursor = False 		

	def init_db(self):
		#connect
		if not self._initialized_conn:
			try:
				self.db_conn = MySQLdb.connect(self.dbhost, self.dbbuser, self.dbpass, self.dbname)
				self._initialized_conn = True
			except:
				self._initialized_conn = False
		return self._initialized_conn

	
	def close(self, db_conn):
		if self._initilized:
			self.db_conn.close()			
	
	def cursor_execute(self, query):
		if not self._initializated_cursor:
			if not self.init_db():
				try:
				#connection exists
					self.cursor= self.db_conn.cursor()
					self._initialized_cursor = True

				except:
					self._initialized_cursor = False 
		if not self._initialized_cursor:
			return False

		try:	
			self.cursor.execute(query)
			return True
		except:
			return False


	def delete(self, namespace, varname):
		
	
	def update(varvalue, vartype, namespace, varname):
		succeed = False
		if not self.cursor_execute("SELECT * FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			return False
		if len(self.cursor.fetchall()) > 0 :
			# do update
			succeed = self.cursor.execute("UPDATE varvalues SET varvalue='%s', vartype='%s' WHERE namespace='%s' AND varname='%s';" % (varvalue, vartype, namespace, varname))
		else:
			# do insert
			succeed = self.cursor.execute("INSERT INTO varvalues(namespace, varname, varvalue, vartype) VALUES ('%s', '%s', '%s', '%s');" % (namespace, varname, varvalue, vartype))
			
		if succedd:
			self.db_conn.commit()
		else:
			# Rollback in case there is any error
			self.db_conn.rollback()


	
	def test_auth(self, group_list, namespace, varname, accesslevel, filemode=False):
		auth_user = False
		if filemode:
			selectindex = 1
		else:
			selectindex = 0

		#search in database
		for g in group_list:
			# do SQL query
			if self.cursor.execute("SELECT authvar,authfile FROM auth WHERE username='%s' AND namespace='%s' AND (varname='%s' OR varname='' OR varname IS NULL);" % (g, namespace, varname)):
				# print all the first cell of all the rows
				for row in self.cursor.fetchall():
					if ( row[selectindex] >= accesslevel ):
						auth_user = True
		return auth_user




# Create class Server with exposed methods
class datastore_core_server(object):
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
			try:
				ld=ldap.initialize(self.ldapserver)
				ld.protocol_version = ldap.VERSION3	
				dn = "uid="+username+","+self.userdn
				ld.simple_bind_s(dn,userpass)
				valid_user = True
				glist = [ 'anonymous', username ]
			except ldap.LDAPError, e:
				valid_user = False	
		if valid_user:
			log_message = 'user validation successfully'
		else:
			glist = []
		
		if self.debug_mode:
			log.debug('validate_user(%s): '+log_message, username)
		# get group list
		searchScope = ldap.SCOPE_SUBTREE
		retrieveAttributes = [ 'cn' ] 
		searchFilter = "memberuid="+username
		try:
			if self.binddn and self.bindpass:
				ld.simple_bind_s(self.binddn, self.bindpass)

			ldap_result_id = ld.search(self.groupdn, searchScope, searchFilter, retrieveAttributes)
			while 1:
				result_type, result_data = ld.result(ldap_result_id, 0)
				if (result_data == []):
					break
				else:
					if result_type == ldap.RES_SEARCH_ENTRY:
						#glist.append(result_data)
						glist.append('@'+result_data[0][1]['cn'][0])
			log_message = 'search successfully'

		except ldap.LDAPError, e:
			log_message = 'search error'

		if self.debug_mode:
			log.debug('get_groups(%s): '+log_message, username)
		return glist

	def _test_auth_var(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth(username, userpass, namespace, varname, accesslevel, False)

	def _test_auth_file(self, username, userpass, namespace, varname, accesslevel):
		return self._test_auth(username, userpass, namespace, varname, accesslevel, True)

	def _test_auth(self, username, userpass, namespace, varname, accesslevel, filemode=False):
		auth_user = False
		if filemode:
			selectindex = 1
		else:
			selectindex = 0

		#search in database
		try:
			# connect
			db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)	
			cur = db.cursor() 
			for g in self._get_groups(username, userpass):
				# do SQL query
				cur.execute("SELECT authvar,authfile FROM auth WHERE username='%s' AND namespace='%s' AND (varname='%s' OR varname='' OR varname IS NULL);" % (g, namespace, varname))
				# print all the first cell of all the rows
				for row in cur.fetchall() :
					if ( row[selectindex] >= accesslevel ):
						auth_user = True
						break
			cur.close()
			db.close()
			log_message = "Successfully access to database"
		except:
			log_message = "Error accessing database"
				
		if self.debug_mode:
			log.debug('database access: '+log_message)

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

	def put_value(self, username, userpass, namespace, varname, varvalue, vartype=VARTYPE_STRING):
		put_result = False
		log_message = "put_value: not authorized"
		if not self._is_valid_data(varvalue, vartype):
			log_message = "put_value: invalid data"
		elif self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_WRITE):
			# prepare data
			if ( vartype == VARTYPE_PASSWORD ):
				varvalue = base64.b64encode(varvalue)

			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor()
				try:
					cur.execute("SELECT * FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname))
					if len(cur.fetchall()) > 0 :
						# do update
						cur.execute("UPDATE varvalues SET varvalue='%s', vartype='%s' WHERE namespace='%s' AND varname='%s';" % (varvalue, vartype, namespace, varname))
					else:
						# do insert
						cur.execute("INSERT INTO varvalues(namespace, varname, varvalue, vartype) VALUES ('%s', '%s', '%s', '%s');" % (namespace, varname, varvalue, vartype))
			
					db.commit()
				except:
					# Rollback in case there is any error
					db.rollback()

				cur.close()
				db.close()
				log_message = "successfully put_value"
				put_result = True
			except:
				log_message = "error in  put_value"

		if self.debug_mode:
			log.debug(log_message)

		return put_result	
			
	def del_value(self, username, userpass, namespace, varname):
		del_result = False
		log_message = "del_value: not authorized"
		if self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_WRITE):
			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor()
				cur.execute("DELETE FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname))
				log_message = "del_value: success"
				cur.close()
				db.close()
				del_result = True
			except:
				log_message = "del_value: error deleting value"
				
		if self.debug_mode:
			log.debug(log_message)
				
			
		return del_result

	def get_value(self, username, userpass, namespace, varname):
		log_message = "get_value: not authorized"
		get_data = ""
		if self._test_auth_var(username, userpass, namespace, varname, AUTHMODE_READ):
			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor() 
				cur.execute("SELECT varvalue, vartype FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname))
				# get_result = (cur.fetchall())[0][0]
				first_row =(cur.fetchall())[0]
				# prepare data
				if ( first_row[1] == VARTYPE_PASSWORD ):
					get_data = base64.b64decode(first_row[0])
				else:
					get_data = first_row[0]

				cur.close()
				db.close()
				log_message = "successfully get_value"
			except:
				log_message = "error in  get_value"

		if self.debug_mode:
			log.debug(log_message)

		return get_data

	def put_file(self, username, userpass, namespace, fname, arg):
		put_result = False
		log_message = "put_file: not authorized"
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path to store files
			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor()
				cur.execute("SELECT filepath FROM filepaths WHERE namespace='%s';" % (namespace))
				filepath = (cur.fetchall())[0][0]
				cur.close()
				db.close()
				# do update
				try:
					with open(filepath+"/"+os.path.basename(fname), "wb") as handle:
						handle.write(arg.data)
					handle.close()
					log_message = "file successfully write"
					put_result = True

				except:
					log_message = "error writing file"

			except:
				log_message = "error reading path"

		if self.debug_mode:
			log.debug('put_file(%s): '+log_message, fname)

		return put_result

	def del_file(self, username, userpass, namespace, fname):
		del_result = False
		log_message = "del_file: not authorized"
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path to store files
			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor()
				cur.execute("SELECT filepath FROM filepaths WHERE namespace='%s';" % (namespace))
				filepath = (cur.fetchall())[0][0]
				cur.close()
				db.close()
				# do update
				try:
					os.remove(filepath+"/"+os.path.basename(fname))
					log_message = "file successfully deleted"
					del_result = True

				except:
					log_message = "error deleting file"

			except:
				log_message = "error reading path"

		if self.debug_mode:
			log.debug('del_file(%s): '+log_message, fname)

		return del_result

	def get_file(self, username, userpass, namespace, fname):
		log_message = "get_file: not authorized"
		binary_data = xmlrpclib.Binary('')
		if self._test_auth_file(username, userpass, namespace, fname, AUTHMODE_WRITE):
			# get path where files are stored
			try:
				# connect
				db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpass, db=dbname)
				cur = db.cursor()
				cur.execute("SELECT filepath FROM filepaths WHERE namespace='%s';" % (namespace))
				filepath = (cur.fetchall())[0][0]
				cur.close()
				db.close()
				# do update
				try:

					with open(filepath+"/"+fname, "rb") as handle:
    						binary_data = xmlrpclib.Binary(handle.read())
					handle.close()
					log_message = "file successfully read"

				except:
					log_message = "error reading file"

			except:
				log_message = "error reading path"

		if self.debug_mode:
			log.debug('get_file(%s): '+log_message, fname)

		return binary_data



class datastore_plugin(datastore_core_server):

	def test_auth_var(self, username, userpass, varname, accesslevel):
		return super(datastore_plugin, self).test_auth_var(username, userpass, self.__class__.__name__, varname, accesslevel)

	def test_auth_file(self, username, userpass, namespace, varname, accesslevel):
		return super(datastore_plugin,self).test_auth_file(username, userpass, self.__class__.name__, varname, accesslevel)

	def put_value(self, username, userpass, namespace, varname, varvalue, vartype=VARTYPE_STRING):
		return super(datastore_plugin,self).put_value(username, userpass, self.__class__.name__, varname, varvalue, vartype)
	
	def del_value(self, username, userpass, namespace, varname):
		return super(datastore_plugin,self).del_value(username, userpass, self.__class__.name__, varname)

	def get_value(self, username, userpass, namespace, varname):
		return super(datastore_plugin,self).get_value(username, userpass, self.__class__.name__, varname)

	def put_file(self, username, userpass, namespace, fname, arg):
		return super(datastore_plugin,self).put_file(username, userpass, self.__class__.name__, fname, arg)

	def del_file(self, username, userpass, namespace, fname):
		return super(datastore_plugin,self).del_file(username, userpass, self.__class__.name__, fname)

	def get_file(self, username, userpass, namespace, fname):
		return super(datastore_plugin,self).get_file(username, userpass, self.__class__.name__, fname)

class datastore_server(datastore_core_server):
	def __init__(self,plugin_path=""):
		if plugin_path:
			if plugin_path not in sys.path:
				sys.path.append(plugin_path)
			for file in os.listdir(plugin_path):
				if file.endswith(".py") and not  file.startswith("_"):
					cname = os.path.splitext(file)[0]
					cmodule = importlib.import_module(cname)
					constructor = getattr(cmodule, cname)
					setattr( self, cname,constructor() )


