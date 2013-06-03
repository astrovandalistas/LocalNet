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
    # Adds a new subscriber to a receiver
    def addSubscriber(self, ip):
        self.subscriberList.append(ip)
    # Removes subscriber from receiver
    def removeSubscriber(self, ip):
        try:
            self.subscriberList.remove(ip)
        except:
            pass
