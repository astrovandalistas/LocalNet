# -*- coding: utf-8 -*-

import time, threading, string
from OSC import OSCClient, OSCMessage, OSCServer, getUrlStr, OSCClientError
from Queue import Queue

def runPrototype(prot):
    try:
        time.sleep(1)
        prot.setup()
        while True:
            ## keep it from looping faster than ~60 times per second
            loopStart = time.time()
            prot.loop()
            loopTime = time.time()-loopStart
            if (loopTime < 0.017):
                time.sleep(0.017 - loopTime)
    except KeyboardInterrupt:
        prot._cleanUpOsc()
        prot.stop()

class PrototypeInterface:
    """ prototype interface:
        all prototypes must implement setup() and loop() functions
        self.messageQ will have all messages coming in from LocalNet
        in the format (locale,type,text)
        this also implements subscribeToAll() and subscribeTo(name) """
    def removeNonAscii(self, s):
        return "".join(i for i in s if i in string.printable)
    def removeAccents(self,txt):
        ## hack! sanitize text
        txt = txt.replace("#","")
        ##
        txt = txt.replace("á","aa")
        txt = txt.replace("é","ee")
        txt = txt.replace("í","ii")
        txt = txt.replace("ó","oo")
        txt = txt.replace("ú","uu")
        txt = txt.replace("ñ","ni")
        ##
        txt = txt.replace("Á","aa")
        txt = txt.replace("É","ee")
        txt = txt.replace("Í","ii")
        txt = txt.replace("Ó","oo")
        txt = txt.replace("Ú","uu")
        txt = txt.replace("Ñ","ni")
        return txt

    def _oscHandler(self, addr, tags, stuff, source):
        addrTokens = addr.lstrip('/').split('/')
        ## list of all receivers
        if ((addrTokens[0].lower() == "localnet")
              and (addrTokens[1].lower() == "receivers")):
            for rcvr in stuff[0].split(','):
                self.allReceivers[rcvr] = rcvr
        ## actual message from AEffect Network !!
        elif (addrTokens[0].lower() == "aeffectlab"):
            self.messageQ.put((addrTokens[1],
                               addrTokens[2],
                               stuff[0].decode('utf-8')))

    def __init__(self,inport,outip,outport):
        ## administrative: names and ports
        self.messageQ = Queue()
        self.inPort = inport
        self.localNetAddress = (outip,outport)
        self.name = self.__class__.__name__.lower()
        self.allReceivers = {}
        self.subscribedReceivers = {}

        ## setup osc client
        self.oscClient = OSCClient()
        self.oscClient.connect(self.localNetAddress)

        ## setup osc receiver
        ## or this?? ifconfig | grep inet | grep -v 'inet6\|127.0.0.1'
        self.oscServer = OSCServer(("127.0.0.1",self.inPort))
        self.oscServer.addMsgHandler('default', self._oscHandler)
        self.oscThread = threading.Thread(target = self.oscServer.serve_forever)
        self.oscThread.start()

        ## request list of all receivers from localnet
        msg = OSCMessage()
        msg.setAddress("/LocalNet/ListReceivers")
        msg.append(self.inPort)
        try:
            self.oscClient.send(msg)
        except OSCClientError:
            print ("no connection to "+self.localNetAddress
                    +", can't request list of receivers")

    def _cleanUpOsc(self):
        ## disconnect from LocalNet
        for rcvr in self.subscribedReceivers.keys():
            msg = OSCMessage()
            msg.setAddress("/LocalNet/Remove/"+rcvr)
            msg.append(self.inPort)
            try:
                self.oscClient.send(msg)
            except OSCClientError:
                print ("no connection to %s, can't disconnect from receivers"
                       %(self.localNetAddress,))
        ## close osc
        self.oscServer.close()
        self.oscThread.join()

    def subscribeToAll(self):
        for rcvr in self.allReceivers.keys():
            if(not rcvr.lower().startswith('osc')):
                self.subscribeTo(rcvr)

    def subscribeTo(self,rcvr):
        msg = OSCMessage()
        msg.setAddress("/LocalNet/Add/"+self.name+"/"+rcvr)
        msg.append(self.inPort)
        try:
            self.oscClient.send(msg)
        except OSCClientError:
            print ("no connection to %s, can't subscribe to %s receiver"
                   %(self.localNetAddress,) %rcvr)
        else:
            self.subscribedReceivers[rcvr] = rcvr

    def setup(self):
        print "setup not implemented"
    def loop(self):
        print "loop not implemented"
    def stop(self):
        print "stop not implemented"

class MessageReceiverInterface:
    """A message receiver interface"""
    # Sets up the stuff a receiver might need
    def __init__(self):
        self.subscriberList = []
        self.name = ""
        self.lastMessageTime = time.time()
    def setup(self, db, osc, loc):
        print "setup not implemented"
    # Checks for new messages
    def update(self):
        print "update not implemented"
    # Clean up
    def stop(self):
        print "stop not implemented"
    # Adds a new subscriber to a receiver
    def addSubscriber(self, (ip,port)):
        if(not (ip,int(port)) in self.subscriberList):
            self.subscriberList.append((ip,int(port)))
    # Removes subscriber from receiver
    def removeSubscriber(self, (ip,port)):
        if((ip,int(port)) in self.subscriberList):
            self.subscriberList.remove((ip,int(port)))
    # Checks if it has specific subscriber
    def hasSubscriber(self, (ip,port)):
        return ((ip,port) in self.subscriberList)
    # Prepare OSC message and send it to all subscribers
    def sendToAllSubscribers(self, txt, addr=None):
        if (addr is None):
            addr = "/AEffectLab/"+self.location['name']+"/"+self.name
        ## setup osc message
        msg = OSCMessage()
        msg.setAddress(addr)
        ## Send utf-8 byte blob
        msg.append(txt.encode('utf-8'), 'b')
        ## send to subscribers
        self._sendToAllSubscribers(msg)
        ## update timer
        self.lastMessageTime = time.time()
    # Prepare OSC message to send to specific subscriber
    def sendToSubscriber(self, ip,port, txt):
        addr = "/AEffectLab/"+self.location['name']+"/"+self.name
        ## setup osc message
        msg = OSCMessage()
        msg.setAddress(addr)
        ## Send utf-8 byte blob
        msg.append(txt.encode('utf-8'), 'b')
        ## send to subscriber
        self._sendToSubscriber(msg,ip,port)
        ## update timer
        self.lastMessageTime = time.time()
    # Sends OSC msg to all subscribers
    def _sendToAllSubscribers(self, oscMsg):
        delQ = Queue()
        for (ip,port) in self.subscriberList:
            try:
                self.oscClient.connect((ip, port))
                self.oscClient.sendto(oscMsg, (ip, port))
                self.oscClient.connect((ip, port))
            except OSCClientError:
                print ("no connection to "+ip+":"+str(port)
                       +", removing it from osc subscribers")
                delQ.put((ip,port))
                continue
        while (not delQ.empty()):
            self.removeSubscriber(delQ.get())
    # Send OSC to specific subscriber
    def _sendToSubscriber(self,msg,ip,port):
        try:
            self.oscClient.connect((ip, port))
            self.oscClient.sendto(msg, (ip, port))
            self.oscClient.connect((ip, port))
        except OSCClientError:
            print ("no connection to "+ip+":"+str(port)
                    +", removing it from osc subscribers")
            self.removeSubscriber((ip,port))
