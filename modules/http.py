from twisted.web import client
from twisted.internet import reactor, ssl

import os
import urlparse
import urllib

class HTTPDownloader(client.HTTPDownloader):
	def gotHeaders(self, headers):
		client.HTTPDownloader.gotHeaders(self, headers)
		print(headers)
		contentLength = headers.get("content-length", None)
		if int(self.status) == 200 and contentLength:
			print("%s: Content-Length: %s" % (self.url, contentLength,))
			self._file._size = int(contentLength[0])

	def openFile(self, partialContent):
		if partialContent:
			raise ValueError('partial download not supported')
		return self._file.open(self.fileName)

class HttpDownloader(object):
	name = "HttpDownloader"
	ports = {'http' : 80, 'https' : 443}

	def __init__(self, manager, config):
		self.manager = manager

	def schemes(self):
		return ['http', 'https']

	def download(self, f):
		print('HTTP Download: %s' % (f.url(),))
		parsed_url = urlparse.urlparse(f.url())
		if parsed_url.scheme not in self.schemes():
			raise ValueError('unknown scheme %s' % (parsed_url.scheme,))

		#f.open()
		name = urllib.unquote(os.path.basename(parsed_url.path)).decode('utf-8')
		factory = HTTPDownloader(f.url(), name)
		factory._file = f
		if ':' in parsed_url.netloc:
			host, port = parsed_url.netloc.split(':')
			port = int(port)
		else:
			host, port = parsed_url.netloc, self.ports[parsed_url.scheme]

		if parsed_url.scheme == 'https':
			reactor.connectSSL(host, port, factory, ssl.ClientContextFactory())
		else:
			reactor.connectTCP(host, port, factory)
		return factory.deferred