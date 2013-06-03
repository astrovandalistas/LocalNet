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
