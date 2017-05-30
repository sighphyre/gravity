import sys
import json
import jwt

from twisted.internet import reactor
from twisted.python import log
from twisted.web.server import Site
from twisted.web.static import File

from autobahn.twisted.websocket import WebSocketServerFactory, \
    WebSocketServerProtocol, \
    listenWS

def decode_token(token):
    # encoded = jwt.encode({'some': 'payload'}, 'secret', algorithm='HS256')
    try:        
        return jwt.decode(token, 'secret', algorithms=['HS256'])
    except(jwt.exceptions.DecodeError):
        return None    


class UserStore:

    def __init__(self):
        self.validatedPeers = []


store = UserStore()

class BroadcastServerProtocol(WebSocketServerProtocol):

    def __init__(self, **kwargs):
        WebSocketServerProtocol.__init__(self, **kwargs)

    def onOpen(self):        
        self.factory.register(self)

    def onMessage(self, payload, isBinary):
        if not isBinary:            
            packet = json.loads(payload.decode("utf-8"))
            if "token" in packet:
                print("validating token")
                claims = decode_token(packet["token"])
                if not claims:
                    return
                print(claims)
                msg = {
                    "message" : "{} from {}".format(packet["message"], claims["username"]),
                    "origin": self.peer
                }
                # print self.peer

                self.factory.broadcast(msg)
            elif "username" in packet and "password" in packet:
                print "Got user ", packet["username"]
                credentials = {
                    "username": packet["username"]
                }
                encoded = jwt.encode(credentials, 'secret', algorithm='HS256')
                message = json.dumps({
                    "type": "token",
                    "data": encoded
                }).encode('utf8')
                store.validatedPeers.append(self.peer)
                self.sendMessage(message)

    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)


class BroadcastServerFactory(WebSocketServerFactory):

    """
    Simple broadcast server broadcasting any message it receives to all
    currently connected clients.
    """

    def __init__(self, url, userStore):
        WebSocketServerFactory.__init__(self, url)
        self.userStore = userStore
        self.clients = []
        self.tickcount = 0
        self.tick()

    def tick(self):
        self.tickcount += 1
        # self.broadcast({
        #     "message": "tick %d from server" % self.tickcount,
        #     "origin": None
        #     })
        reactor.callLater(1, self.tick)

    def register(self, client):
        if client not in self.clients:
            print("registered client {}".format(client.peer))
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            print("unregistered client {}".format(client.peer))
            self.clients.remove(client)

    def broadcast(self, msg):
        # print("broadcasting message '{}' ..".format(msg))
        for c in self.clients:
            # if(c.peer == msg["origin"]):
            #     print("Skipping this entry because it's the origin")
            #     continue
            if c.peer in self.userStore.validatedPeers:
                message = json.dumps({
                    "type": "update",
                    "data": msg["message"]
                }).encode('utf8')
                c.sendMessage(message)                
                print("message sent to {}".format(c.peer))
            else:
                print "I know this peer but I don't know who they are"


class BroadcastPreparedServerFactory(BroadcastServerFactory):

    """
    Functionally same as above, but optimized broadcast using
    prepareMessage and sendPreparedMessage.
    """

    def broadcast(self, msg, userStore):
        self.userStore = userStore
        # print("broadcasting prepared message '{}' ..".format(msg))
        preparedMsg = self.prepareMessage(msg)
        for c in self.clients:
            if c.peer in userStore.validatedPeers:
                c.sendPreparedMessage(preparedMsg)
            # print("prepared message sent to {}".format(c.peer))

if __name__ == '__main__':

    log.startLogging(sys.stdout)

    ServerFactory = BroadcastServerFactory
    # ServerFactory = BroadcastPreparedServerFactory


    factory = ServerFactory(u"ws://127.0.0.1:9000", store)
    factory.protocol = BroadcastServerProtocol
    listenWS(factory)

    webdir = File(".")
    web = Site(webdir)
    reactor.listenTCP(8080, web)

    reactor.run()
