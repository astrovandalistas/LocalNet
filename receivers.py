# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from threading import Thread
from time import time, strftime, localtime
from json import loads, dumps
import re
from Queue import Queue
from socketIO_client import SocketIO, SocketIOError, BaseNamespace
from twython import Twython
from OSC import OSCClient, OSCMessage, OSCServer, getUrlStr, OSCClientError
from serial import SerialException
from humod import Modem, actions, errors
from peewee import *

class HttpReceiver(MessageReceiverInterface):
    """A class for receiving json/xml query results and passing them to its subscribers"""
    WEB_CHECK_PERIOD = 10
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

        return self.socketConnected

    def update(self):
        if(not self.socket.connected):
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


class SmsReceiver(MessageReceiverInterface):
    """A class for receiving SMS messages and passing them to its subscribers"""

    ## decoder for sms message
    def _decodeSms(self, sms):
        out = ""
        if(sms.startswith("00")):
            for c in sms.decode('hex'):
                out += c.decode('latin-1')
        else:
            out += sms
        return out

    ## Handler for new sms messages
    def _smsHandler(self, modem, message):
        ml = message.strip('\r\t\n').split(',')
        print "reading message #"+str(ml[-1])+"#"
        smsTxt = self.modem.sms_read(int(ml[-1]))
        self.modem.sms_del(int(ml[-1]))
        smsTxt = self._decodeSms(smsTxt)
        print "received: "+smsTxt
        ## send to all subscribers
        self.sendToAllSubscribers(smsTxt)
        ## log onto local database
        self.database.create(epoch=time(),
                             dateTime=strftime("%Y/%m/%d %H:%M:%S", localtime()),
                             text=smsTxt.encode('utf-8'),
                             receiver="sms",
                             hashTags="",
                             prototypes=dumps(self.subscriberList),
                             user="")

    ## setup gsm modem
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "sms"
        self.modemReady = True
        ## setup modem for sms receiver
        mActions = [(actions.PATTERN['new sms'], self._smsHandler)]
        try:
            self.modem = Modem()
            self.modem.enable_textmode(True)
            self.modem.enable_nmi(True)
            self.modem.prober.start(mActions)
        except SerialException:
            print "No GSM modem detected, sorry"
            self.modemReady = False
            return self.modemReady
        except errors.AtCommandError:
            print "No SIM card detected, sorry"
            self.modemReady = False
            return self.modemReady
        ## return
        return self.modemReady

    def update(self):
        pass

    ## end sms receiver
    def stop(self):
        if(self.modemReady):
            self.modem.prober.stop()

class OscReceiver(MessageReceiverInterface):
    """A class for receiving Osc messages and passing them to its subscribers"""
    def __init__(self, others, protos, ip="127.0.0.1", port=8888):
        MessageReceiverInterface.__init__(self)
        self.oscServerIp = ip
        self.oscServerPort = port
        self.oscMasterIp = None
        self.oscMasterPort = None
        ## this is a dict of names to receivers
        ## like: 'sms' -> SmsReceiver_instance
        ## keys are used to match against osc requests
        self.allReceivers = others
        ## to enable osc forwarding, add osc server as subscriber to all receivers
        for k in self.allReceivers:
            self.allReceivers[k].addSubscriber((self.oscServerIp,self.oscServerPort))
        ## this is a dict of (ip,port) -> prototype
        ## like: (192.168.2.5, 8888) -> megavoice
        self.allPrototypes = protos

    def _oscHandler(self, addr, tags, stuff, source):
        addrTokens = addr.lstrip('/').split('/')
        ## /LocalNet/{Add,Remove}/Type -> port-number
        if ((addrTokens[0].lower() == "localnet")
            and (addrTokens[1].lower() == "add")):
            ip = getUrlStr(source).split(":")[0]
            port = int(stuff[0])
            self.allPrototypes[(ip,port)] = addrTokens[2]
            if (addrTokens[3].lower() in self.allReceivers):
                print "adding "+ip+":"+str(port)+" to "+addrTokens[3].lower()+" receivers"
                self.allReceivers[addrTokens[3].lower()].addSubscriber((ip,port))
                ## if adding osc listener need to setup osc master
                if((addrTokens[3].lower().startswith('osc')) 
                    and (not self.oscMasterIp is None)
                    and (not self.oscMasterPort is None)):
                    print ("adding osc master")
                    try:
                        oscSubscribeMessage = OSCMessage()
                        oscSubscribeMessage.setAddress("/LocalNet/Add/"+addrTokens[2]+"/Osc")
                        oscSubscribeMessage.append(str(self.oscServerPort).encode('utf-8'), 'b')
                        self.oscClient.connect((self.oscMasterIp, int(self.oscMasterPort)))
                        self.oscClient.sendto(oscSubscribeMessage, (self.oscMasterIp, int(self.oscMasterPort)))
                        self.oscClient.connect((self.oscMasterIp, int(self.oscMasterPort)))
                    except OSCClientError:
                        print ("no connection to "+self.oscMasterIp+":"+str(self.oscMasterPort))
        elif ((addrTokens[0].lower() == "localnet")
              and (addrTokens[1].lower() == "remove")):
            ip = getUrlStr(source).split(":")[0]
            port = int(stuff[0])
            if (addrTokens[2].lower() in self.allReceivers):
                print "removing "+ip+":"+str(port)+" from "+addrTokens[2].lower()+" receivers"
                self.allReceivers[addrTokens[2].lower()].removeSubscriber((ip,port))
            ## only remove from list of prototypes when not in any receiver...
            inSomeSubscriber = False
            for k in self.allReceivers:
                inSomeSubscriber |= self.allReceivers[k].hasSubscriber((ip,port))
            if ((not inSomeSubscriber) and ((ip,port) in self.allPrototypes)):
                print("removing "+self.allPrototypes[(ip,port)]+" @ "+ip+":"+str(port)
                      +" from list of prototypes")
                del self.allPrototypes[(ip,port)]
        ## /LocalNet/ListReceivers -> port-number
        elif ((addrTokens[0].lower() == "localnet")
              and (addrTokens[1].lower().startswith("listreceiver"))):
            ip = getUrlStr(source).split(":")[0]
            port = int(stuff[0])
            ## send list of receivers to client
            msg = OSCMessage()
            msg.setAddress("/LocalNet/Receivers")
            msg.append(",".join(self.allReceivers.keys()))
            try:
                self.oscClient.connect((ip, port))
                self.oscClient.sendto(msg, (ip, port))
                self.oscClient.connect((ip, port))
            except OSCClientError:
                print ("no connection to "+ip+":"+str(port)
                       +", can't send list of receivers")
        ## /LocalNet/ListReceivers -> port-number
        elif ((addrTokens[0].lower() == "localnet")
              and (addrTokens[1].lower().startswith("listprototype"))):
            ip = getUrlStr(source).split(":")[0]
            port = int(stuff[0])
            ## send list of prototypes to client
            msg = OSCMessage()
            msg.setAddress("/LocalNet/Prototypes")
            msg.append(",".join(self.allPrototypes.values()))
            try:
                self.oscClient.connect((ip, port))
                self.oscClient.sendto(msg, (ip, port))
                self.oscClient.connect((ip, port))
            except OSCClientError:
                print ("no connection to "+ip+":"+str(port)
                       +", can't send list of prototypes")

        ## /AEffectLab/{local}/{type} -> msg
        elif (addrTokens[0].lower() == "aeffectlab"):
            oscTxt = stuff[0].decode('utf-8')
            print "forwarding "+addr+" : "+oscTxt+" to my osc subscribers"
            ## send to all subscribers
            addr = "/AEffectLab/"+addrTokens[1]+"/"+addrTokens[2]
            self.sendToAllSubscribers(oscTxt, addr)

    ## setup osc server
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "osc"
        self.oscServer = OSCServer((self.oscServerIp,self.oscServerPort))
        ## handler
        self.oscServer.addMsgHandler('default', self._oscHandler)
        ## start server
        self.oscThread = Thread( target = self.oscServer.serve_forever )
        self.oscThread.start()
        ## return
        return True

    ## setup master ip,port
    def setupMaster(self,ip,port):
        self.oscMasterIp = ip
        self.oscMasterPort = int(port)

    ## update osc server
    def update(self):
        pass

    ## end oscReceiver
    def stop(self):
        self.oscServer.close()
        self.oscThread.join()

class TwitterReceiver(MessageReceiverInterface):
    """A class for receiving Twitter messages and passing them to its
    subscribers"""
    ## How often to check twitter (in seconds)
    TWITTER_CHECK_PERIOD = 6
    ## What to search for
    SEARCH_TERMS = ["#aeLab", "#aeffect"]

    ## setup twitter connection and internal variables
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "twitter"
        self.lastTwitterCheck = time()
        self.mTwitter = None
        self.twitterAuthenticated = False
        self.largestTweetId = 1
        self.twitterResults = None
        self.hashTags = TwitterReceiver.SEARCH_TERMS
        ## read secrets from file
        inFile = open('oauth.txt', 'r')
        self.secrets = {}
        for line in inFile:
            (k,v) = line.split()
            self.secrets[k] = v
        self._authenticateTwitter()
        ## get largest Id for tweets that came before starting the program
        self._searchTwitter()
        self._getLargestTweetId()
        self.twitterResults = None
        ## return
        return self.twitterAuthenticated

    ## check for new tweets every once in a while
    def update(self):
        if (time() - self.lastTwitterCheck > TwitterReceiver.TWITTER_CHECK_PERIOD):
            self._searchTwitter()
            if (not self.twitterResults is None):
                for tweet in self.twitterResults["statuses"]:
                    ## update largestTweetId for next searches
                    if (int(tweet['id']) > self.largestTweetId):
                        self.largestTweetId = int(tweet['id'])
                    ## print
                    print ("pushing %s from @%s" %
                           (tweet['text'], tweet['user']['screen_name']))
                    ## send to all subscribers
                    self.sendToAllSubscribers(tweet['text'])
                    ## log onto local database
                    msgHashTags = []
                    for h in self.hashTags:
                        if(h in tweet['text']):
                            msgHashTags.append(h)
                    self.database.create(epoch=time(),
                                         dateTime=strftime("%Y/%m/%d %H:%M:%S", localtime()),
                                         text=tweet['text'].encode('utf-8'),
                                         receiver="twitter",
                                         hashTags=dumps(msgHashTags),
                                         prototypes=dumps(self.subscriberList),
                                         user=tweet['user']['screen_name'])
            self.lastTwitterCheck = time()

    ## end twitterReceiver
    def stop(self):
        pass

    ## authenticate to twitter using secrets
    def _authenticateTwitter(self):
        try:
            self.mTwitter = Twython(app_key = self.secrets['CONSUMER_KEY'],
                                    app_secret = self.secrets['CONSUMER_SECRET'],
                                    oauth_token = self.secrets['ACCESS_TOKEN'],
                                    oauth_token_secret = self.secrets['ACCESS_SECRET'])
            self.twitterAuthenticated = True
        except:
            self.mTwitter = None
            self.twitterAuthenticated = False

    ## get largest Id for tweets in twitterResults
    def _getLargestTweetId(self):
        if (not self.twitterResults is None):
            for tweet in self.twitterResults["statuses"]:
                print ("Tweet %s from @%s at %s" %
                       (tweet['id'],
                        tweet['user']['screen_name'],
                        tweet['created_at']))
                print tweet['text'],"\n"
                if (int(tweet['id']) > self.largestTweetId):
                    self.largestTweetId = int(tweet['id'])

    ## query twitter
    def _searchTwitter(self):
        if ((self.twitterAuthenticated) and (not self.mTwitter is None)):
            try:
                self.twitterResults = self.mTwitter.search(q=" OR ".join(self.hashTags),
                                                           include_entities="false",
                                                           count="50",
                                                           result_type="recent",
                                                           since_id=self.largestTweetId)
            except:
                self.twitterResults = None
