from twisted.web import client
from twisted.internet import defer

import urlparse

class FakeDownloader(object):
	name = "FakeDownloader"

	def __init__(self, manager, config):
		self.manager = manager

	def schemes(self):
		return []

	def download(self, f):
		print('Fake Download: %s' % (f.url(),))
		f.open()
		f.close()
		f._deferred = defer.Deferred()
		f._deferred.callback(None)
		return f._deferred