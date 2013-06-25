# -*- coding: utf-8 -*-

import time
from Queue import Queue
from OSC import OSCClient, OSCMessage, OSCClientError
from receivers import TwitterReceiver, SmsReceiver, OscReceiver
from peewee import *

# these will probably be command line arguments
LOCAL_NET_LOCALE = "Five42"
# TODO: set osc port and twitter hashtags here

def setup():
    global receivers, prototypes, mOscClient
    global lastPrototypeCheck, oscPingMessage
    receivers = {}
    prototypes = {}
    lastPrototypeCheck = time.time()
    oscPingMessage = OSCMessage()
    oscPingMessage.setAddress("/LocalNet/Ping")
    ## use empty byte blob
    oscPingMessage.append("", 'b')

    ## init database
    class Message(Model):
        time = DateTimeField()
        text = BlobField()
        receiver = CharField()

    try:
        Message.create_table()
    except:
        print "tried to recreate message table, pero no pasa nada"

    print "message table has %s entries" % Message.select().count()
    """
    for m in Message.select():
        print "%s %s" % (m.time, str(m.text).decode('utf-8'))
    """

    ## init receivers
    rcvT = TwitterReceiver()
    receivers['twitter'] = rcvT
    rcvS = SmsReceiver()
    receivers['sms'] = rcvS
    rcvO = OscReceiver(receivers,prototypes)
    mOscClient = OSCClient()
    setupDelQ = Queue()
    for (k,v) in receivers.iteritems():
        if(not v.setup(Message, mOscClient, LOCAL_NET_LOCALE)):
            setupDelQ.put(k)
    while (not setupDelQ.empty()):
        badReceiver = setupDelQ.get()
        del receivers[badReceiver]

def loop():
    for (k,v) in receivers.iteritems():
        v.update()

def checkPrototypes():
    print "checking prots"
    delQ = Queue()
    for (ip,port) in prototypes:
        try:
            mOscClient.connect((ip, int(port)))
            mOscClient.sendto(oscPingMessage, (ip, int(port)))
        except OSCClientError:
            print ("no connection to "+ip+":"+str(port)
                    +", removing it from list of prototypes")
            delQ.put((ip,port))
            continue
    while (not delQ.empty()):
        (ip,port) = delQ.get()
        if((ip,port) in prototypes):
            del prototypes[(ip,port)]

if __name__=="__main__":
    setup()
    try:
        while(True):
            ## check prototype connection every 30 seconds
            if(time.time()-lastPrototypeCheck > 30):
                checkPrototypes()
                lastPrototypeCheck = time.time()

            ## keep it from looping faster than ~60 times per second
            loopStart = time.time()
            loop()
            loopTime = time.time()-loopStart
            if (loopTime < 0.017):
                time.sleep(0.017 - loopTime)

    except KeyboardInterrupt :
        for (k,v) in receivers.iteritems():
            v.stop()
