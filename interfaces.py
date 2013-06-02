class MessageReceiverInterface:
    """A message receiver interface"""
    # Sets up the stuff a receiver might need
    def setup(self):
        print "setup not implemented"
    # Checks for new messages
    def update(self):
        print "update not implemented"
    # Adds a new subscriber to a receiver
    def addSubscriber(self, ip):
        self.ipList.append(ip)
    # Removes subscriber from receiver
    def removeSubscriber(self, ip):
        try:
            self.ipList.remove(ip)
        except:
            pass
