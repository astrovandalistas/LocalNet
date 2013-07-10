# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from humod import Modem, actions, errors
from serial import SerialException
from peewee import *
from json import loads, dumps

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
