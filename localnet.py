# -*- coding: utf-8 -*-

import time
from OSC import OSCClient
from receivers import TwitterReceiver, SmsReceiver, OscReceiver

def setup():
    global rcvrs, prots
    rcvrs = {}
    prots = {}
    rcvT = TwitterReceiver()
    rcvrs['twitter'] = rcvT
    #rcvS = SmsReceiver()
    #rcvrs['sms'] = rcvS
    rcvO = OscReceiver(rcvrs,prots)
    oc = OSCClient()
    for (k,v) in rcvrs.iteritems():
        v.setup(oc,"LocalLocalNet")

def loop():
    for (k,v) in rcvrs.iteritems():
        v.update()

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
        for (k,v) in rcvrs.iteritems():
            v.stop()
