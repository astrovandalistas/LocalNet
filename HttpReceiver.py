# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from socketIO_client import SocketIO, SocketIOError, BaseNamespace
from peewee import *
from json import loads, dumps
import re
from time import time, strftime, localtime

class HttpReceiver(MessageReceiverInterface):
    """A class for receiving json/xml query results and passing them to its subscribers"""
    CONNECTION_CHECK_PERIOD = 10
    def __init__(self, others, protos, ip="127.0.0.1", port=3700, description=""):
        MessageReceiverInterface.__init__(self)
        self.localNetDescription = description
        self.serverIp = ip
        self.serverPort = port
        ## this is a dict of names to receivers
        ## like: 'sms' -> SmsReceiver_instance
        ## keys are used to match against osc requests
        self.allReceivers = others
        ## this is a dict of (ip,port) -> prototype
        ## like: (192.168.2.5, 8888) -> megavoice
        self.allPrototypes = protos
        ## this is a dict of (ip,port) -> prototype 
        ## for keeping track of prototypes that have been sent to server
        self.sentPrototypes = {}
        ## reg-exp pattern for finding hashtags in messages
        self.hashTagMatcher = re.compile(r"([#]\w+)")

    def _getLocationDict(self):
        return {
                'city':self.location['city'],
                'state':self.location['state'],
                'country':self.location['country'],
                'coordinates':self.location['coordinates']
                }
    ## server reply party !!!
    class localNetNamespace(BaseNamespace):
        pass

    def _onAddLocalNetSuccess(self, *args):
        self.addedToServer = True
        for arg in args:
            if('epoch' in arg):
                print "localNet was added to server"
                self.serverIsWaitingForMessagesSince = float(arg['epoch'])

    def _onAddPrototypeSuccess(self, *args):
        for arg in args:
            if('prototypeAddress' in arg):
                (pip,pport) = arg['prototypeAddress'].split(':')
                if((pip,int(pport)) in self.allPrototypes):
                    print self.allPrototypes[(pip,int(pport))]+" was added to server"
                    self.sentPrototypes[(pip,int(pport))] = self.allPrototypes[(pip,int(pport))]

    def _onRemovePrototypeSuccess(self, *args):
        for arg in args:
            if('prototypeAddress' in arg):
                (pip,pport) = arg['prototypeAddress'].split(':')
                if((pip,int(pport)) in self.sentPrototypes):
                    print self.sentPrototypes[(pip,int(pport))]+" was removed from server"
                    del self.sentPrototypes[(pip,int(pport))]

    def _onAddLocalNetMessageSuccess(self, *args):
        for arg in args:
            if('messageId' in arg):
                if((self.largestSentMessageId+1) == int(arg['messageId'])):
                    print "message "+str(int(arg['messageId']))+" was added to server"
                    self.largestSentMessageId += 1

    ## process message from server
    def _onAddServerMessage(self, *args):
        print "got message from server"
        for arg in args:
            mEpoch = float(arg['epoch']) if('epoch' in arg) else time()
            mText = str(arg['messageText']).decode('utf-8') if('messageText' in arg) else ""
            mPrototype = str(arg['prototype']) if('prototype' in arg) else ""
            mUser = str(arg['user']) if('user' in arg) else ""

            if(not mText is ""):
                ## send to all subscribers
                if(mPrototype is ""):
                    self.sendToAllSubscribers(mText)
                    mPrototype=self.subscriberList
                ## send to one subscriber
                else:
                    mPrototype = mPrototype.replace('[','').replace(']','').replace('u\'','').replace('\',',',')
                    mPrototype = mPrototype.split(',')
                    (ip,port) = (str(mPrototype[0]),int(mPrototype[1]))
                    if((ip,port) in self.subscriberList):
                        print "found prototype, sending to "+ip+":"+str(port)
                        self.sendToSubscriber(ip,port,mText)
                    else:
                        print "didn't find prototype at "+ip+":"+str(port)
                    mPrototype=[(ip,port)]
                ## log onto local database
                msgHashTags = []
                for ht in self.hashTagMatcher.findall(mText):
                    msgHashTags.append(str(ht))
                ## TODO: fix this: thread problem
                """
                self.database.create(epoch=mEpoch,
                                     dateTime=strftime("%Y/%m/%d %H:%M:%S", localtime(mEpoch)),
                                     text=mText.encode('utf-8'),
                                     receiver="http",
                                     hashTags=dumps(msgHashTags),
                                     prototypes=dumps(mPrototype),
                                     user=mUser)
                """

    def _sendMessage(self, msg):
        prots = []
        for (i,p) in loads(msg.prototypes):
            ## make sure it's a real prototype, not an osc repeater
            if((str(i),int(p)) in self.allPrototypes):
                ## TODO: this should send a list of ip:ports
                prots.append(self.allPrototypes[(str(i), int(p))])

        mInfo = {
                'localNetName':self.location['name'],
                'location':self._getLocationDict(),
                'dateTime':msg.dateTime,
                'epoch':msg.epoch,
                'messageId':msg.id,
                'messageText':str(msg.text).decode('utf-8'),
                'hashTags':msg.hashTags,
                'user':msg.user,
                'receiver':msg.receiver,
                'prototypes':prots
                }
        print "sending message "+str(msg.id)+":"+str(msg.text).decode('utf-8')+" to server"
        self.localNetSocket.emit('addMessage', mInfo, self._onAddLocalNetMessageSuccess)

    def _attemptConnection(self):
    	self.lastConnectionAttempt = time()
    	## try to open socket and send localnet info
        try:
            self.socket = SocketIO(self.serverIp, self.serverPort)
        except SocketIOError:
            self.socketConnected = False
            print ("couldn't connect to web server at "+
                    self.serverIp+":"+str(self.serverPort))
        else:
            self.socketConnected = True
            self.localNetSocket = self.socket.define(self.localNetNamespace, '/localNet')
            self.localNetSocket.on('addMessage', self._onAddServerMessage)

    ## setup socket communication to server
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "http"
        self.socketConnected = False
        self.addedToServer = False
        self.largestSentMessageId = -100
        self.serverIsWaitingForMessagesSince = -100
        self.lastMessagesSent = time()
        self.lastConnectionAttempt = 0

        return True

    def update(self):
        if(not self.socketConnected):
        	if(time()-self.lastConnectionAttempt > HttpReceiver.CONNECTION_CHECK_PERIOD):
        		self._attemptConnection()
        	return

        ## if local net not on web server, add to server
        if(not self.addedToServer):
            localNetInfo = {
                            'localNetName':self.location['name'],
                            'location':self._getLocationDict(),
                            'localNetDescription':self.localNetDescription,
                            'receivers':self.allReceivers.keys(),
                            'hashTags':self.allReceivers['twitter'].hashTags
                            }
            print "adding localNet to server"
            self.localNetSocket.emit('addLocalNet', localNetInfo, self._onAddLocalNetSuccess)

        ## if server is waiting for messages since an epoch
        if(self.serverIsWaitingForMessagesSince > -1):
            mQuery = self.database.select()
            mQuery = mQuery.where(self.database.epoch > self.serverIsWaitingForMessagesSince).order_by(self.database.id)
            for m in mQuery.limit(1):
                self.largestSentMessageId = m.id-1
            for m in mQuery:
                self._sendMessage(m)
            self.lastMessagesSent = time()
            self.serverIsWaitingForMessagesSince = -1

        ## check for new prototypes
        addQ = Queue()
        for p in self.allPrototypes:
            if (not p in self.sentPrototypes):
                addQ.put(p)
                print "adding "+self.allPrototypes[p]+" to server"
        while (not addQ.empty()):
            p = addQ.get()
            (pip,pport) = p
            ## send prototype info to add it to server
            pInfo = {
                    'localNetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'prototypeName':self.allPrototypes[p],
                    'prototypeAddress':pip+":"+str(pport),
                    'prototypeDescription':"hello, I'm a prototype"
                    }
            self.localNetSocket.emit('addPrototype', pInfo, self._onAddPrototypeSuccess)

        ## check for disconnected prototypes
        delQ = Queue()
        for p in self.sentPrototypes:
            if (not p in self.allPrototypes):
                delQ.put(p)
                print "removing "+self.sentPrototypes[p]+" from server"
        while (not delQ.empty()):
            p = delQ.get()
            (pip,pport) = p
            ## send prototype info to remove it from server
            pInfo = {
                    'localNetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'prototypeName':self.sentPrototypes[p],
                    'prototypeAddress':pip+":"+str(pport)
                    }
            self.localNetSocket.emit('removePrototype', pInfo, self._onRemovePrototypeSuccess)

        ## send new messages to server
        if(time()-self.lastMessagesSent > 1.0):
            mQuery = self.database.select()
            for m in mQuery.where(self.database.id > self.largestSentMessageId).order_by(self.database.id):
                self._sendMessage(m)
            self.lastMessagesSent = time()

    ## end http receiver; disconnect socket
    def stop(self):
        if(self.socketConnected):
            self.socket.disconnect()
