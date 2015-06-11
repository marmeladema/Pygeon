# twisted imports
from twisted.web.resource import Resource, NoResource
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, defer
from twisted.python import log

# system imports
import time
import sys
import jinja2
import json
import urlparse
import os

class DccState:
    WAITING = "WAITING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DOWNLOADING = "DOWNLOADING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"

class XDccFileReceive(irc.DccFileReceiveBasic):
    """Higher-level coverage for getting a file from DCC SEND.

    I allow you to change the file's name and destination directory.
    I won't overwrite an existing file unless I've been told it's okay
    to do so. If passed the resumeOffset keyword argument I will attempt to
    resume the file from that amount of bytes.

    XXX: I need to let the client know when I am finished.
    XXX: I need to decide how to keep a progress indicator updated.
    XXX: Client needs a way to tell me "Do not finish until I say so."
    XXX: I need to make sure the client understands if the file cannot be written.
    """
    
    overwrite = 0

    def set_overwrite(self, boolean):
        """May I overwrite existing files?
        """
        self.overwrite = boolean

    def connectionMade(self):
        self.factory.file.open()

    def dataReceived(self, data):
        irc.DccFileReceiveBasic.dataReceived(self, data)
        self.factory.file.write(data)

    def connectionLost(self, reason):
        """When the connection is lost, I close the file.
        """
        self.connected = 0
        self.factory.file.close()
        logmsg = ("%s closed." % (self,))
        if self.factory.file._size > 0:
            logmsg = ("%s  %d/%d bytes received"
                      % (logmsg, self.bytesReceived, self.factory.file._size))
            if self.bytesReceived == self.factory.file._size:
                self.factory.file._deferred.callback(None)
            elif self.bytesReceived < self.factory.file._size:
                logmsg = ("%s (Warning: %d bytes short)"
                          % (logmsg, self.factory.file._size - self.bytesReceived))
                self.factory.file._deferred.errback(ValueError("incomplete file"))
            else:
                logmsg = ("%s (file larger than expected)"
                          % (logmsg,))
                self.factory.file._deferred.callback(None)
        else:
            self.factory.file._deferred.callback(None)
            logmsg = ("%s  %d bytes received"
                      % (logmsg, self.bytesReceived))
        print(logmsg)

    def __str__(self):
        if not self.connected:
            return "<Unconnected DccFileReceive object at %x>" % (id(self),)
        from_ = self.transport.getPeer()
        if self.factory.user:
            from_ = "%s (%s)" % (self.factory.user, from_)

        s = ("DCC transfer of '%s' from %s" % (self.factory.file._filename, from_))
        return s

    def __repr__(self):
        s = ("<%s at %x: DCC %s>"
             % (self.__class__, id(self), self.factory.file._filename))
        return s

class XDccFileReceiveFactory(protocol.ClientFactory):
    """A factory for XDccFileReceive.

    A new protocol instance will be created each time we connect to the server.
    """

    protocol = XDccFileReceive

    def __init__(self, f, user):
        self.file = f
        self.user = user
        self.state = DccState.WAITING

class IrcBot(irc.IRCClient):
    """An IRC bot."""

    def __init__(self, nickname):
        self.nickname = nickname

    # callbacks for events

    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        for channel in self.factory.channels:
            print('Joining channel #%s' % (channel,))
            self.join(channel)

    def joined(self, channel):
        """This will get called when the bot joins the channel."""
        print('Joined channel #%s' % (channel,))
  
    # irc callbacks

    def irc_NICK(self, prefix, params):
        """Called when an IRC user changes their nickname."""
        old_nick = prefix.split('!')[0]
        new_nick = params[0]
        print("%s is now known as %s" % (old_nick, new_nick))

    # For fun, override the method that determines how a nickname is changed on
    # collisions. The default method appends an underscore.
    def alterCollidedNick(self, nickname):
        """
        Generate an altered version of a nickname that caused a collision in an
        effort to create an unused related name for subsequent registration.
        """
        return nickname + '^'

    def dccDoSend(self, user, address, port, fileName, size, data):
        user = user.split('!', 1)[0]
        print("DCC offer received from %s for %s of size %d at %s:%d" % (user, fileName, size, address, port))
        if port == 0:
            self.notice(user, "Reverse DCC unsupported")
            return
        
        if user in self.factory.dcc_sessions:
            for dcc in self.factory.dcc_sessions[user]:
                if dcc.state == DccState.WAITING:
                    dcc.file._name = fileName
                    dcc.file._filename = fileName
                    dcc.file._size = size
                    reactor.connectTCP(address, port, dcc)
                    dcc.state = DccState.CONNECTING
                    break

class IrcBotFactory(protocol.ClientFactory):
    """A factory for IrcBots.

    A new protocol instance will be created each time we connect to the server.
    """

    dcc_sessions = {}

    def __init__(self, host, port, nickname, channels):
        self.host = host
        self.port = port
        self.filename = '/dev/stdout'
        self.nickname = nickname.encode('ascii')
        self.channels = []
        for channel in channels:
            self.channels.append(channel.encode('ascii'))
        self.bot = None

    def buildProtocol(self, addr):
        self.bot = IrcBot(self.nickname)
        self.bot.factory = self
        return self.bot

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        """If we can't connect, retry in a 30 secondes"""
        print "connection failed:", reason
        #reactor.stop()

class XdccDownloader(object):
    name = 'XdccDownloader'
    nickname = 'michelmichel'

    isLeaf = True

    def __init__(self, manager, config):
        if 'nickname' in config:
            self.nickname = config['nickname'].encode('ascii')
        self.networks = {}
        for network in config['networks']:
            if 'nickname' in config['networks'][network]:
                nickname = config['networks'][network]['nickname'].encode('ascii')
            else:
                nickname = self.nickname
            
            host = config['networks'][network]['server'][0]
            port = config['networks'][network]['server'][1]
            self.networks[network.encode('ascii')] = IrcBotFactory(host, port, nickname, config['networks'][network]['channels'])
            reactor.connectTCP(host, port, self.networks[network.encode('ascii')])

    def render(self, path):
        if path == ['schemes']:
            return json.dumps(self.schemes())
        html = '<h1>Networks</h1>\n'
        for network in self.networks:
            html += '<h2>' + network + '</h2>\n'
            for channel in self.networks[network].channels:
                html += '<h3>#' + channel + '</h3>\n'
        template = jinja2.Template(open('modules/irc.html').read())
        html += template.render(irc=self)
        return html

    def schemes(self):
        return ['irc']

    def download(self, f):
        print('IRC Download: %s' % (f.url(),))
        parsed = urlparse.urlparse(f.url())
        print(parsed)
        irc = None
        if parsed.netloc in self.networks:
            irc = self.networks[parsed.netloc]
        else:
            for network in self.networks:
                if self.networks[network].host == parsed.netloc:
                    irc = self.networks[network]
        f._deferred = defer.Deferred()
        if irc:
            nick, msg = os.path.split(parsed.path)
            nick = os.path.basename(nick)
            irc.bot.msg(nick, msg)
            if nick not in irc.dcc_sessions:
                irc.dcc_sessions[nick] = []
            irc.dcc_sessions[nick].append(XDccFileReceiveFactory(f, nick))
        else:
            f._deferred.errback(ValueError("no irc connection found"))
        return f._deferred
