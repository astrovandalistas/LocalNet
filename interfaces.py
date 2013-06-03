from OSC import OSCClientError
from Queue import Queue

class MessageReceiverInterface:
    """A message receiver interface"""
    # Sets up the stuff a receiver might need
    def __init__(self):
        self.subscriberList = []
    def setup(self, osc, loc):
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
    # Sends msg to all subscribers
    def _sendToAllSubscribers(self, msg):
        delQ = Queue()
        for (ip,port) in self.subscriberList:
            try:
                self.oscClient.connect((ip, port))
                self.oscClient.sendto(msg, (ip, port))
            except OSCClientError:
                print ("no connection to "+ip+":"+str(port)
                       +", removing it from osc subscribers")
                delQ.put((ip,port))
                continue
        while (not delQ.empty()):
            self.removeSubscriber(delQ.get())
