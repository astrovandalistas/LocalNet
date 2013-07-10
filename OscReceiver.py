# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from peewee import *
from OSC import OSCClient, OSCMessage, OSCServer, getUrlStr, OSCClientError
from threading import Thread

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
