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
		if not self._initialized_conn:
			try:
				self.db_conn = MySQLdb.connect(self.dbhost, self.dbuser, self.dbpass, self.dbname)
				self._initialized_conn = True
			except:
				self._initialized_conn = False
		return self._initialized_conn

	
	def close(self, db_conn):
		if self._initilized:
			self.db_conn.close()			
	
	def cursor_execute(self, query):
		if not self._initialized_cursor:
			if self.init_db():
				try:
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
		if self.cursor_execute("DELETE FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			self.db_conn.commit()
			return True

		self.db_conn.rollback()
		return False

	def update(self, namespace, varname, varvalue, vartype):
		succeed = False
		if not self.cursor_execute("SELECT * FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			return False
		if len(self.cursor.fetchall()) > 0 :
			# do update
			succeed = self.cursor.execute("UPDATE varvalues SET varvalue='%s', vartype='%s' WHERE namespace='%s' AND varname='%s';" % (varvalue, vartype, namespace, varname))
		else:
			# do insert
			succeed = self.cursor.execute("INSERT INTO varvalues(namespace, varname, varvalue, vartype) VALUES ('%s', '%s', '%s', '%s');" % (namespace, varname, varvalue, vartype))
			
		if succeed:
			self.db_conn.commit()
			return True
		else:
			# Rollback in case there is any error
			self.db_conn.rollback()
			return False


	def read (self, namespace, varname):
		get_data = ""
		if self.cursor.execute("SELECT varvalue, vartype FROM varvalues WHERE namespace='%s' AND varname='%s';" % (namespace, varname)):
			# get_result = (cur.fetchall())[0][0]
			# comprobar el numero de filas leidas por si no hay
			first_row =(self.cursor.fetchall())[0]
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


	def read (self, username, userpass, namespace, varname):
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

