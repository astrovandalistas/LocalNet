# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from threading import Thread
from time import time, strftime, localtime
from json import loads, dumps
from Queue import Queue
from requests import ConnectionError
from socketIO_client import SocketIO, SocketIOError
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

    def _getLocationDict(self):
        return {
                'city':self.location['city'],
                'state':self.location['state'],
                'country':self.location['country'],
                'coordinates':self.location['coordinates']
                }
    ## server reply party !!!
    def _onAddLocalNetSuccess(*args):
        self.addedToServer = True

    def _onAddPrototypeSuccess(*args):
        for arg in args:
            if('prototypeName' in arg):
                (pname,pip,pport) = arg['prototypeName'].replace('@',':').split(':')
                if((pip,int(pport)) in self.allPrototypes):
                    self.sentPrototypes[(pip,int(pport))] = self.allPrototypes[(pip,int(pport))]

    def _onRemovePrototypeSuccess(*args):
        for arg in args:
            if('prototypeName' in arg):
                (pname,pip,pport) = arg['prototypeName'].replace('@',':').split(':')
                if((pip,int(pport)) in self.sentPrototypes):
                    del self.sentPrototypes[(pip,int(pport))]

    def _onAddMessageSuccess(*args):
        for arg in args:
            if('messageId' in arg):
                m = self.database.get(self.database.id == int(arg['messageId']))
                m.published = True
                m.save()

    ## process message request reply
    def _onCheckMessagesSuccess(*args):
        self.lastWebCheck = time()
        ## TODO: parse messages, send to prototypes

    ## setup socket communication to server
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "http"
        self.socketConnected = False
        self.addedToServer = False
        self.lastWebCheck = time()

        ## try to open socket and send localnet info
        try:
            self.socket = SocketIO(self.serverIp, self.serverPort)
        except (SocketIOError, ConnectionError) as e:
            self.socketConnected = False
            print ("couldn't connect to web server at "+
                    self.serverIp+":"+str(self.serverPort))
        else:
            self.socketConnected = True
            self.socket.on('add-localnet-success',self._onAddLocalNetSuccess)
            self.socket.on('add-prototype-success',self._onAddPrototypeSuccess)
            self.socket.on('remove-prototype-success',self._onRemovePrototypeSuccess)
            self.socket.on('add-message-success',self._onAddMessageSuccess)
            self.socket.on('check-messages-success',self._onCheckMessagesSuccess)

        return self.socketConnected

    def update(self):
        if(not self.socket.connected):
            return
        
        ## if local net not on web server, add to server
        if(not self.addedToServer):
            localNetInfo = {
                            'localnetName':self.location['name'],
                            'location':self._getLocationDict(),
                            'localnetDescription':self.localNetDescription,
                            'receivers':self.allReceivers.keys()
                            }
            self.socket.emit('add-localnet', localNetInfo)

        ## check for new prototypes
        addQ = Queue()
        for p in self.allPrototypes:
            if (not p in self.sentPrototypes):
                addQ.put(p)
        while (not addQ.empty()):
            p = addQ.get()
            (pip,pport) = p
            ## send prototype info to add it to server
            pInfo = {
                    'localnetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'prototypeName':self.allPrototypes[p]+"@"+pip+":"+str(pport),
                    'prototypeDescription':"hello, I'm a prototype"
                    }
            self.socket.emit('add-prototype', pInfo)

        ## check for disconnected prototypes
        delQ = Queue()
        for p in self.sentPrototypes:
            if (not p in self.allPrototypes):
                delQ.put(p)
        while (not delQ.empty()):
            p = delQ.get()
            (pip,pport) = p
            ## send prototype info to remove it from server
            pInfo = {
                    'localnetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'prototypeName':self.sentPrototypes[p]+"@"+pip+":"+str(pport)
                    }
            self.socket.emit('remove-prototype', pInfo)

        ## send new messages to server
        for m in self.database.select().where(self.database.published == False):
            prots = []
            for (i,p) in loads(m.prototypes):
                ## make sure it's a real prototype, not an osc repeater
                if((str(i),int(p)) in self.allPrototypes):
                    prots.append(self.allPrototypes[(str(i), int(p))])

            mInfo = {
                    'localnetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'dateTime':m.dateTime,
                    'epoch':m.epoch,
                    'messageId':m.id,
                    'messageText':str(m.text).decode('utf-8'),
                    'receiver':m.receiver,
                    'prototypes':prots,
                    'hashTag':m.hashTag                    
                    }
            self.socket.emit('add-message', mInfo)

        ## check if there are messages on server
        now = time()
        if(now - self.lastWebCheck > HttpReceiver.WEB_CHECK_PERIOD):
            rInfo = {
                    'localnetName':self.location['name'],
                    'location':self._getLocationDict(),
                    'since':self.lastWebCheck
                    }
            self.socket.emit('check-messages', rInfo)

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
                             hashTag="",
                             prototypes=dumps(self.subscriberList),
                             published=False)

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
    SEARCH_TERM = ("#aeLab")

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
                    self.database.create(epoch=time(),
                                         dateTime=strftime("%Y/%m/%d %H:%M:%S", localtime()),
                                         text=tweet['text'].encode('utf-8'),
                                         receiver="twitter",
                                         hashTag=TwitterReceiver.SEARCH_TERM,
                                         prototypes=dumps(self.subscriberList),
                                         published=False)
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
                self.twitterResults = self.mTwitter.search(q=TwitterReceiver.SEARCH_TERM,
                                                           include_entities="false",
                                                           count="50",
                                                           result_type="recent",
                                                           since_id=self.largestTweetId)
            except:
                self.twitterResults = None
