from interfaces import MessageReceiverInterface
import time
from twython import Twython

class SmsReceiver(MessageReceiverInterface):
    """A class for receiving SMS messages and passing them to its subscribers"""


class TwitterReceiver(MessageReceiverInterface):
    """A class for receiving Twitter messages and passing them to its
    subscribers"""
    ## How often to check twitter (in seconds)
    TWITTER_CHECK_PERIOD = 6
    ## What to search for
    SEARCH_TERM = ("#ficaadica OR #BangMTY")

    ## setup twitter connection and internal variables
    def setup(self):
        self.lastTwitterCheck = time.time();
        self.mTwitter = None
        self.twitterAuthenticated = False
        self.largestTweetId = 1
        self.twitterResults = None
        ## read secrets from file
        inFile = open('oauth.txt', 'r')
        self.secrets = {}
        for line in inFile:
            (k,v) = line.split()
            self.secrets[k] = v
        self.__authenticateTwitter()
        ## get largest Id for tweets that came before starting the program
        self.__searchTwitter()
        self.__getLargestTweetId()

    ## authenticate to twitter using secrets
    def __authenticateTwitter(self):
        try:
            self.mTwitter = Twython(twitter_token = self.secrets['CONSUMER_KEY'],
                                    twitter_secret = self.secrets['CONSUMER_SECRET'],
                                    oauth_token = self.secrets['ACCESS_TOKEN'],
                                    oauth_token_secret = self.secrets['ACCESS_SECRET'])
            self.twitterAuthenticated = True
        except:
            self.mTwitter = None
            self.twitterAuthenticated = False

    ## get largest Id for tweets in twitterResults
    def __getLargestTweetId(self):
        if (not self.twitterResults is None):
            for tweet in self.twitterResults["statuses"]:
                print ("Tweet %s from @%s at %s" %
                       (tweet['id'],
                        tweet['user']['screen_name'],
                        tweet['created_at']))
                print tweet['text'],"\n"
                if (int(tweet['id']) > self.largestTweetId):
                    self.largestTweetId = int(tweet['id'])

    ## query twitter
    def __searchTwitter(self):
        if ((self.twitterAuthenticated) and (not self.mTwitter is None)):
            try:
                self.twitterResults = self.mTwitter.search(q=TwitterReceiver.SEARCH_TERM,
                                                           include_entities="false",
                                                           count="50",
                                                           result_type="recent",
                                                           since_id=self.largestTweetId)
            except:
                self.twitterResults = None
