import ldap

class datastore_auth(object):
	def __init__(self, ldapserver, userdn, groupdn, binddn="", bindpass=""):
		self.ldapserver = ldapserver
		self.userdn = userdn
		self.groupdn = groupdn
		self.binddn = binddn
		self.bindpass = bindpass

	def initialize(self):
		if self._initialized:
			return True

		try:
			self.ld = ldap.initialize(self.ldapserver)
			self.ld.protocol_version = ldap.VERSION3
			self._initialized = True
		except ldap.LDAPError, e:
			self._initialized = False

		return self._initialized

	def test_credentials(self, username, userpass):
		if not self.initialize():
			return False

		dn = "uid="+username+","+self.userdn
		try:
			self.ld.simple_bind_s(dn, userpass)
			return True
		except ldap.LDAPError, e:
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
       	                        result_type, result_data = ld.result(ldap_result_id, 0)
               	                if (result_data == []):
                               	        break
                       	        else:
					if result_type == ldap.RES_SEARCH_ENTRY:
					glist.append(result_data[0][1]['cn'][0])

		return glist



ldapserver="ldap://fsserver"
userdn = "ou=usuarios,dc=centro,dc=com"
test = datastore_auth(ldapserver, userdn, groupdn, binddn="", bindpass="")



		


