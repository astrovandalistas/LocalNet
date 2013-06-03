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
        self.subscriberList.append((ip,int(port)))
    # Removes subscriber from receiver
    def removeSubscriber(self, (ip,port)):
        for (i,p) in self.subscriberList:
            if(ip == i):
                self.subscriberList.remove((i,p))
