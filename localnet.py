# -*- coding: utf-8 -*-

import time
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
OSC_SERVER_PORT = 8888
MASTER_SERVER_IP = "127.0.0.1"
MASTER_SERVER_PORT = 7777
#WEB_SERVER_IP = "127.0.0.1"
WEB_SERVER_IP = "192.168.1.119"
WEB_SERVER_PORT = 3700

## init database
class Message(Model):
    epoch = FloatField()
    dateTime = CharField()
    text = BlobField()
    receiver = CharField()
    hashTags = CharField()
    prototypes = CharField()
    user = CharField()

def setup():
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
    rcvO = OscReceiver(receivers,prototypes, port=OSC_SERVER_PORT)
    receivers['osc'] = rcvO
    rcvH = HttpReceiver(receivers,prototypes, WEB_SERVER_IP, WEB_SERVER_PORT, LOCAL_NET_DESCRIPTION)
    receivers['http'] = rcvH
    mOscClient = OSCClient()
    setupDelQ = Queue()
    for (k,v) in receivers.iteritems():
        if(not v.setup(Message, mOscClient, LOCAL_NET_LOCALE)):
            ## TODO: don't remove http or twitter, should keep trying to connect
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
            mOscClient.connect((ip, int(port)))
            mOscClient.sendto(oscPingMessage, (ip, int(port)))
            mOscClient.connect((ip, int(port)))
        except OSCClientError:
            print ("no connection to "+ip+":"+str(port)
                    +", removing it from list of prototypes")
            delQ.put((ip,port))
            continue
    while (not delQ.empty()):
        (ip,port) = delQ.get()
        if((ip,port) in prototypes):
            del prototypes[(ip,port)]
def loop():
    global lastPrototypeCheck, receivers

    ## check prototype connection every 30 seconds
    if(time.time()-lastPrototypeCheck > 30):
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
    setup()
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
