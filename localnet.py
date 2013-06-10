# -*- coding: utf-8 -*-

import time
from OSC import OSCClient
from receivers import TwitterReceiver, SmsReceiver, OscReceiver

# these will probably be command line arguments
LOCAL_NET_LOCALE = "Five42"

def setup():
    global receivers, prototypes
    receivers = {}
    prototypes = {}
    rcvT = TwitterReceiver()
    receivers['twitter'] = rcvT
    #rcvS = SmsReceiver()
    #receivers['sms'] = rcvS
    rcvO = OscReceiver(receivers,prototypes)
    oc = OSCClient()
    for (k,v) in receivers.iteritems():
        v.setup(oc,LOCAL_NET_LOCALE)

def loop():
    for (k,v) in receivers.iteritems():
        v.update()

if __name__=="__main__":
    setup()
    try:
        while(True):
            ## TODO: check prots every N seconds
            ## keep it from looping faster than ~60 times per second
            loopStart = time.time()
            loop()
            loopTime = time.time()-loopStart
            if (loopTime < 0.017):
                time.sleep(0.017 - loopTime)

    except KeyboardInterrupt :
        for (k,v) in receivers.iteritems():
            v.stop()
