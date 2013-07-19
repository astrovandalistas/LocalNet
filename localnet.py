# -*- coding: utf-8 -*-

import sys, time, getopt
from Queue import Queue
from OSC import OSCClient, OSCMessage, OSCClientError
from TwitterReceiver import TwitterReceiver
from OscReceiver import OscReceiver
from SmsReceiver import SmsReceiver
from HttpReceiver import HttpReceiver
from peewee import *

# these will probably be command line arguments or come from files
# TODO: set twitter hashtags here
LOCAL_NET_LOCALE = {
                    "name":"Five42",
                    "city":"Oakland",
                    "state":"CA",
                    "country":"USA",
                    "coordinates":[37.8044,-122.2697]
                    }
LOCAL_NET_DESCRIPTION = "This is a house on 542 Lewis. Best fireworks display this side of the bay."

## init database
class Message(Model):
    epoch = FloatField()
    dateTime = CharField()
    text = BlobField()
    receiver = CharField()
    hashTags = CharField()
    prototypes = CharField()
    user = CharField()

def setup(inIp, inPort, webServerAddress, webServerPort):
    global prototypes, mOscClient, oscPingMessage
    global lastPrototypeCheck, receivers
    receivers = {}
    prototypes = {}
    lastPrototypeCheck = time.time()
    oscPingMessage = OSCMessage()
    oscPingMessage.setAddress("/LocalNet/Ping")
    ## use empty byte blob
    oscPingMessage.append("", 'b')

    try:
        Message.create_table()
    except:
        print "tried to recreate message table, pero no pasa nada"

    print "message table has %s entries" % Message.select().count()
    """
    for m in Message.select():
        print "%s %s [%s]" % (m.time, str(m.text).decode('utf-8'), m.receiver)
    """

    ## init receivers
    rcvT = TwitterReceiver()
    receivers['twitter'] = rcvT
    rcvS = SmsReceiver()
    receivers['sms'] = rcvS
    rcvO = OscReceiver(receivers,prototypes, ip=inIp, port=inPort)
    receivers['osc'] = rcvO
    rcvH = HttpReceiver(receivers,prototypes, webServerAddress, webServerPort, LOCAL_NET_DESCRIPTION)
    receivers['http'] = rcvH
    mOscClient = OSCClient()
    setupDelQ = Queue()
    for (k,v) in receivers.iteritems():
        if(not v.setup(Message, mOscClient, LOCAL_NET_LOCALE)):
            setupDelQ.put(k)
    while (not setupDelQ.empty()):
        badReceiver = setupDelQ.get()
        del receivers[badReceiver]
    ## if using as server-osc-repeater
    if (("MASTER_SERVER_IP" in globals()) and ("MASTER_SERVER_PORT" in globals())
        and ('osc' in receivers)):
        receivers['osc'].setupMaster(MASTER_SERVER_IP, MASTER_SERVER_PORT)

def checkPrototypes():
    print "checking prots"
    global prototypes, mOscClient, oscPingMessage
    delQ = Queue()
    for (ip,port) in prototypes:
        try:
            #mOscClient.connect((ip, int(port)))
            mOscClient.sendto(oscPingMessage, (ip, int(port)))
            #mOscClient.connect((ip, int(port)))
        except OSCClientError:
            try:
                mOscClient.sendto(oscPingMessage, (ip, int(port)))
            except OSCClientError:
                print ("no connection to %s:%s, removing it from list of prototypes")%(ip,port)
                delQ.put((ip,port))
                continue
            continue
    while (not delQ.empty()):
        (ip,port) = delQ.get()
        if((ip,port) in prototypes):
            del prototypes[(ip,port)]
def loop():
    global lastPrototypeCheck, receivers

    ## check prototype connection every 30 seconds
    if(time.time()-lastPrototypeCheck > 10):
        checkPrototypes()
        lastPrototypeCheck = time.time()

    ## run update on the receivers and get most recent message time
    recentLastMessage = 0
    for (k,v) in receivers.iteritems():
        v.update()
        if(v.lastMessageTime > recentLastMessage):
            recentLastMessage = v.lastMessageTime

    ## if haven't seen a message in a while (5 minutes), dig from database
    if(time.time() - recentLastMessage > 300):
        for m in Message.select().order_by(fn.Random()).limit(1):
            receivers[m.receiver].sendToAllSubscribers(str(m.text).decode('utf-8'))

if __name__=="__main__":
    (inIp, inPort, webServerAddress, webServerPort) = ("127.0.0.1", 8888, "127.0.0.1", 3700)
    opts, args = getopt.getopt(sys.argv[1:],"i:p:w:o:",["inip=","inport=","webserver=","webserverport="])
    for opt, arg in opts:
        if(opt in ("--inip","-i")):
            inIp = str(arg)
        elif(opt in ("--inport","-p")):
            inPort = int(arg)
        elif(opt in ("--webserver","-w")):
            webServerAddress = str(arg)
        elif(opt in ("--webserverport","-o")):
            webServerPort = int(arg)

    setup(inIp, inPort, webServerAddress, webServerPort)
    try:
        while(True):
            ## keep it from looping faster than ~60 times per second
            loopStart = time.time()
            loop()
            loopTime = time.time()-loopStart
            if (loopTime < 0.017):
                time.sleep(0.017 - loopTime)

    except KeyboardInterrupt :
        for (k,v) in receivers.iteritems():
            v.stop()
